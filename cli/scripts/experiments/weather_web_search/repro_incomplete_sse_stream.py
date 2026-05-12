from __future__ import annotations

import argparse
import json
import threading
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from openai import OpenAI

from cli.agent_cli.providers.adapters.openai_responses import OpenAIResponsesSession


def _sse_event(event_type: str, payload: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"


FIXTURES: dict[str, str] = {
    "incomplete_message": _sse_event(
        "response.output_item.done",
        {
            "type": "response.output_item.done",
            "item": {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "我查一下北京明天的天气。",
                    }
                ],
            },
        },
    ),
    "completed_message": "".join(
        [
            _sse_event(
                "response.output_item.done",
                {
                    "type": "response.output_item.done",
                    "item": {
                        "id": "msg_1",
                        "type": "message",
                        "role": "assistant",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "北京明天晴到多云，10°C 到 25°C。",
                            }
                        ],
                    },
                },
            ),
            _sse_event(
                "response.completed",
                {
                    "type": "response.completed",
                    "response": {
                        "id": "resp_1",
                        "output": [
                            {
                                "id": "msg_1",
                                "type": "message",
                                "role": "assistant",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": "北京明天晴到多云，10°C 到 25°C。",
                                    }
                                ],
                            }
                        ],
                        "output_text": "北京明天晴到多云，10°C 到 25°C。",
                        "status": "completed",
                    },
                },
            ),
        ]
    ),
}


@dataclass
class RunSummary:
    fixture: str
    response_id: str | None
    output_text: str
    response_item_types: list[str]
    answered: bool
    has_final_message: bool
    provider_native_continuation_pending: bool
    turn_event_types: list[str]
    turn_event_item_types: list[str]


class _FixtureHandler(BaseHTTPRequestHandler):
    body_text = ""

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > 0:
            _ = self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(self.body_text.encode("utf-8"))
        self.wfile.flush()

    def log_message(self, fmt: str, *args: object) -> None:
        del fmt, args


def _run_fixture(fixture_name: str) -> RunSummary:
    body_text = FIXTURES[fixture_name]
    handler = type("FixtureHandler", (_FixtureHandler,), {"body_text": body_text})
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    turn_events: list[dict[str, Any]] = []
    try:
        port = int(server.server_address[1])
        client = OpenAI(
            api_key="sk-test",
            base_url=f"http://127.0.0.1:{port}/v1",
            max_retries=0,
        )
        session = OpenAIResponsesSession(
            client=client,
            model="gpt-5.4",
            instructions="system",
            tool_specs=[],
        )
        result = session.send(
            input_items=[{"role": "user", "content": "北京明天天气怎么样？"}],
            allow_tools=False,
            turn_event_callback=lambda event: turn_events.append(dict(event)),
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)
    return RunSummary(
        fixture=fixture_name,
        response_id=result.response_id,
        output_text=str(result.output_text or ""),
        response_item_types=[str(item.item_type or "").strip() for item in list(result.response_items or [])],
        answered=bool((result.trace or {}).get("answered")),
        has_final_message=bool((result.trace or {}).get("has_final_message")),
        provider_native_continuation_pending=bool((result.trace or {}).get("provider_native_continuation_pending")),
        turn_event_types=[str(event.get("type") or "").strip() for event in turn_events],
        turn_event_item_types=[
            str((dict(event.get("item") or {})).get("type") or "").strip()
            for event in turn_events
            if isinstance(event, dict)
        ],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Reproduce AgentHub incomplete SSE handling.")
    parser.add_argument(
        "--fixture",
        choices=sorted(FIXTURES),
        default="incomplete_message",
        help="Fixture body served by the local SSE server.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = _run_fixture(str(args.fixture))
    print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import sys
from typing import Any, Callable, Sequence, TextIO

from cli.agent_cli.models import CommandExecutionResult, ToolEvent

JsonDict = dict[str, Any]


def parse_cli_args(argv: Sequence[str] | None, *, stderr: TextIO | None = None) -> tuple[set[str], set[str]] | None:
    parser = argparse.ArgumentParser(
        prog="agenthub mcp",
        description="Run AgentHub MCP server over stdio.",
    )
    subparsers = parser.add_subparsers(dest="subcommand")
    serve_parser = subparsers.add_parser("serve", help="run MCP server over stdio")
    serve_parser.add_argument("--allow-tool", action="append", default=[])
    serve_parser.add_argument("--deny-tool", action="append", default=[])
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.subcommand != "serve":
        parser.print_usage(file=stderr or sys.stderr)
        return None

    allow_list = {str(item).strip() for item in list(args.allow_tool or []) if str(item).strip()}
    deny_list = {str(item).strip() for item in list(args.deny_tool or []) if str(item).strip()}
    return allow_list, deny_list


def coerce_int(value: Any, *, default: int, minimum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(default)
    if minimum is not None:
        parsed = max(minimum, parsed)
    return parsed


def optional_int(value: Any, *, minimum: int | None = None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"invalid integer value: {value!r}") from None
    if minimum is not None and parsed < minimum:
        raise ValueError(f"integer must be >= {minimum}")
    return parsed


def tool_event_to_dict(event: ToolEvent) -> JsonDict:
    to_dict = getattr(event, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, dict):
            return dict(payload)
    return {
        "name": str(getattr(event, "name", "") or ""),
        "ok": bool(getattr(event, "ok", False)),
        "summary": str(getattr(event, "summary", "") or ""),
        "payload": dict(getattr(event, "payload", {}) or {}),
    }


def command_result_to_mcp_payload(
    result: CommandExecutionResult,
    *,
    tool_event_to_dict_fn: Callable[[ToolEvent], JsonDict] | None = None,
) -> JsonDict:
    to_dict = tool_event_to_dict_fn or tool_event_to_dict
    events = [item for item in list(result.tool_events or []) if isinstance(item, ToolEvent)]
    ok = all(bool(event.ok) for event in events) if events else True
    text = str(result.assistant_text or "").strip()
    if not text:
        summaries = [str(event.summary or "").strip() for event in events if str(event.summary or "").strip()]
        text = "\n".join(summaries).strip()
    if not text:
        text = "ok" if ok else "failed"
    return {
        "content": [{"type": "text", "text": text}],
        "isError": not ok,
        "structuredContent": {
            "assistant_text": str(result.assistant_text or ""),
            "tool_events": [to_dict(event) for event in events],
            "item_events": [dict(item) for item in list(result.item_events or []) if isinstance(item, dict)],
            "turn_events": [dict(item) for item in list(result.turn_events or []) if isinstance(item, dict)],
        },
    }


def result_response(request_id: Any, result: JsonDict) -> JsonDict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result,
    }


def error_response(request_id: Any, *, code: int, message: str, data: JsonDict | None = None) -> JsonDict:
    payload: JsonDict = {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": int(code),
            "message": str(message),
        },
    }
    if data:
        payload["error"]["data"] = dict(data)
    return payload

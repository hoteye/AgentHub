from __future__ import annotations

import argparse
import json
import os
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from cli.agent_cli.core.turn_engine import TurnEngine
from cli.agent_cli.models import AgentIntent, ToolEvent
from cli.agent_cli.providers.adapters.openai_responses import OpenAIResponsesSession
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.openai_client import build_openai_client
from cli.agent_cli.providers.openai_planner_tool_helpers_runtime import (
    resume_native_tool_followup,
)

try:
    from cli.scripts.previous_response_id_rejection_live_harness_analysis_helpers import (
        analyze_observed_requests,
    )
    from cli.scripts.previous_response_id_rejection_live_harness_model_helpers import (
        DEFAULT_EXPECTED_OUTPUT,
        DEFAULT_PROMPT,
        _default_out_dir,
    )
    from cli.scripts.previous_response_id_rejection_live_harness_proxy_helpers import (
        create_previous_response_id_proxy_server,
    )
except ModuleNotFoundError:  # pragma: no cover - direct helper import
    from previous_response_id_rejection_live_harness_analysis_helpers import (  # type: ignore[no-redef]
        analyze_observed_requests,
    )
    from previous_response_id_rejection_live_harness_model_helpers import (  # type: ignore[no-redef]
        DEFAULT_EXPECTED_OUTPUT,
        DEFAULT_PROMPT,
        _default_out_dir,
    )
    from previous_response_id_rejection_live_harness_proxy_helpers import (  # type: ignore[no-redef]
        create_previous_response_id_proxy_server,
    )


def _load_api_key(auth_json: Path, key_name: str) -> str:
    env_value = str(os.getenv(key_name, "") or "").strip()
    if env_value:
        return env_value
    payload = json.loads(auth_json.read_text(encoding="utf-8"))
    value = str(payload.get(key_name, "") or "").strip()
    if value:
        return value
    raise SystemExit(f"missing API key `{key_name}` in env or {auth_json}")


def _provider_config(*, api_key: str, base_url: str, model: str, effort: str) -> ProviderConfig:
    return ProviderConfig(
        model=model,
        api_key=api_key,
        provider_name="openai",
        planner_kind="openai_responses",
        wire_api="responses",
        base_url=base_url,
        reasoning_effort=effort,
        source="previous_response_id_live_harness",
        interaction_profile="codex_openai",
        raw_provider={"wire_api": "responses"},
        raw_model={"supports_tools": True, "supports_reasoning": True},
    )


def _tool_spec() -> dict[str, Any]:
    return {
        "type": "function",
        "name": "lookup_constant",
        "description": "Return a known constant for the live harness.",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
            },
            "required": ["key"],
            "additionalProperties": False,
        },
        "strict": True,
    }


def _unexpected_terminal_handler(*args: Any, **kwargs: Any) -> AgentIntent:
    del args, kwargs
    raise RuntimeError("unexpected_terminal_handler_invocation")


class _PlannerStub:
    def _command_for_function_call(self, name: str, arguments: dict[str, Any]) -> str | None:
        if str(name or "").strip() != "lookup_constant":
            return None
        key = str(arguments.get("key") or "").strip() or "alpha"
        return f"/lookup_constant {key}"


def _tool_executor(command_text: str) -> tuple[str, list[ToolEvent]]:
    key = str(command_text or "").strip().split(" ", 1)[-1].strip() or "alpha"
    value = DEFAULT_EXPECTED_OUTPUT if key == "alpha" else DEFAULT_EXPECTED_OUTPUT
    return (
        value,
        [
            ToolEvent(
                name="lookup_constant",
                ok=True,
                summary=value,
                payload={
                    "function_call_output": value,
                    "function_call_output_model_visible": True,
                    "key": key,
                },
            )
        ],
    )


def run_previous_response_id_rejection_harness(args: argparse.Namespace) -> dict[str, Any]:
    out_dir = (
        Path(str(args.out_dir or "")).expanduser().resolve()
        if str(args.out_dir or "").strip()
        else _default_out_dir()
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    proxy_dir = out_dir / "proxy_capture"
    auth_json = Path(str(args.auth_json or "")).expanduser().resolve()
    api_key = _load_api_key(auth_json, str(args.api_key_name or "OPENAI_API_KEY"))
    proxy_server = create_previous_response_id_proxy_server(
        host="127.0.0.1",
        port=0,
        upstream_base_url=str(args.base_url or "").strip(),
        out_dir=proxy_dir,
        upstream_timeout_seconds=float(args.upstream_timeout_seconds or 180.0),
    )
    proxy_thread = threading.Thread(target=proxy_server.serve_forever, daemon=True)
    proxy_thread.start()
    proxy_host, proxy_port = proxy_server.server_address
    proxy_base_url = f"http://{proxy_host}:{proxy_port}"
    config = _provider_config(
        api_key=api_key,
        base_url=proxy_base_url,
        model=str(args.model or "").strip(),
        effort=str(args.effort or "").strip(),
    )
    client = build_openai_client(config)
    session = OpenAIResponsesSession(
        client=client,
        model=config.model,
        instructions=(
            "You are a strict live-harness assistant. "
            "When the user explicitly tells you to use a tool first, do that. "
            "When a function_call_output is available, trust it and answer with exactly its text only."
        ),
        tool_specs=[_tool_spec()],
        provider_name=config.provider_name,
        base_url=config.base_url,
        reasoning_effort=config.reasoning_effort,
        reference_parity=False,
    )
    planner = _PlannerStub()
    turn_event_sink = lambda _event: None

    def _followup_handler(
        user_text: str,
        executed_events: list[ToolEvent],
        executed_item_events: list[dict[str, Any]] | None = None,
        previous_response_id: str | None = None,
        continuation_input_items: list[dict[str, Any]] | None = None,
        initial_send_error: Exception | None = None,
    ) -> AgentIntent:
        if not continuation_input_items:
            raise RuntimeError("missing continuation_input_items for previous_response_id harness")
        return resume_native_tool_followup(
            planner=planner,
            session=session,
            user_text=user_text,
            tool_executor=_tool_executor,
            executed_events=executed_events,
            executed_item_events=executed_item_events,
            previous_response_id=previous_response_id,
            continuation_input_items=continuation_input_items,
            initial_send_error=initial_send_error,
            terminal_handler=_unexpected_terminal_handler,
            turn_event_callback=turn_event_sink,
        )

    engine = TurnEngine(
        session,
        tool_executor=_tool_executor,
        command_builder=planner._command_for_function_call,
        followup_handler=_followup_handler,
        terminal_handler=_unexpected_terminal_handler,
        turn_event_callback=turn_event_sink,
    )
    started_at = time.perf_counter()
    try:
        intent = engine.run(
            user_text=str(args.prompt or DEFAULT_PROMPT),
            initial_input=[{"role": "user", "content": str(args.prompt or DEFAULT_PROMPT)}],
        )
    finally:
        proxy_server.shutdown()
        proxy_server.server_close()
        proxy_thread.join(timeout=5.0)
    wall_ms = int((time.perf_counter() - started_at) * 1000)
    request_analysis = analyze_observed_requests(list(proxy_server.observed_requests))
    expected_output = str(args.expected_output or DEFAULT_EXPECTED_OUTPUT).strip()
    final_answer = str(intent.assistant_text or "").strip()
    summary = {
        "out_dir": str(out_dir),
        "proxy_base_url": proxy_base_url,
        "upstream_base_url": str(args.base_url or "").strip(),
        "model": config.model,
        "effort": config.reasoning_effort,
        "prompt": str(args.prompt or DEFAULT_PROMPT),
        "expected_output": expected_output,
        "final_answer": final_answer,
        "final_answer_contains_expected_output": expected_output in final_answer,
        "session_incremental_continuation_enabled": bool(session.uses_incremental_continuation()),
        "session_previous_response_id_disabled_reason": str(
            getattr(session, "_previous_response_id_disabled_reason", "") or ""
        ),
        "intent_timings": dict(intent.timings or {}),
        "wall_ms": wall_ms,
        "requests": [asdict(item) for item in list(proxy_server.observed_requests)],
        "request_analysis": request_analysis,
    }
    summary["verdict"] = (
        "pass"
        if request_analysis["verdict"] == "pass"
        and not summary["session_incremental_continuation_enabled"]
        and summary["session_previous_response_id_disabled_reason"] == "previous_response_id_unsupported"
        and summary["final_answer_contains_expected_output"]
        else "fail"
    )
    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary

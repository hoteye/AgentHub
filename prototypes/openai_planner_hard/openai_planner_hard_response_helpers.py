from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.providers.planner_postprocessing import sanitize_final_answer_text
from cli.agent_cli.providers.tool_calls import tool_result_payload as _tool_result_payload_impl


def response_function_calls(response: Any) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for item in list(getattr(response, "output", []) or []):
        if str(getattr(item, "type", "")).strip() != "function_call":
            continue
        arguments_raw = str(getattr(item, "arguments", "") or "{}")
        try:
            arguments = json.loads(arguments_raw)
        except json.JSONDecodeError:
            arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        calls.append(
            {
                "call_id": str(getattr(item, "call_id", "") or "").strip(),
                "name": str(getattr(item, "name", "") or "").strip(),
                "arguments": arguments,
            }
        )
    return [item for item in calls if item["call_id"] and item["name"]]


def response_output_text(
    response: Any,
    *,
    extract_responses_output_text_fn: Callable[[Any], str],
) -> str:
    return sanitize_final_answer_text(extract_responses_output_text_fn(response))


def tool_output_item(
    call_id: str,
    command_text: str | None,
    assistant_text: str,
    events: list[ToolEvent],
    *,
    tool_result_payload_fn: Callable[
        [str | None, str, list[ToolEvent]], dict[str, Any]
    ] = _tool_result_payload_impl,
) -> dict[str, Any]:
    return {
        "type": "function_call_output",
        "call_id": call_id,
        "output": json.dumps(
            tool_result_payload_fn(command_text, assistant_text, events),
            ensure_ascii=False,
        ),
    }

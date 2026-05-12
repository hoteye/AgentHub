from __future__ import annotations

import errno
import json
from collections.abc import Callable
from typing import Any, TextIO

from cli.agent_cli import approval_control_protocol_runtime
from cli.agent_cli.approval_continuation_projection_runtime import continuation_fields
from cli.agent_cli.models import (
    CommandExecutionResult,
    PromptResponse,
    default_response_items,
    response_items_with_tool_outputs,
)
from cli.agent_cli.models_response_items import response_items_phase_text
from cli.agent_cli.runtime_core.command_handlers_approval_helpers_runtime import (
    execute_approval_control_response,
)


def prompt_response_to_dict(
    response: Any,
    *,
    canonical_turn_events_fn: Callable[..., list[dict[str, Any]]],
    tool_event_to_dict_fn: Callable[[Any], dict[str, Any]],
    activity_event_to_dict_fn: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    base_response_items = list(
        response.response_items
        or default_response_items(
            commentary_text=str(response.commentary_text or ""),
            assistant_text=str(response.assistant_text or ""),
        )
    )
    turn_events = [
        dict(item) for item in list(response.turn_events or []) if isinstance(item, dict)
    ]
    has_tool_history = bool(response.tool_events) or any(
        str((event.get("item") or {}).get("type") or "").strip()
        in {
            "command_execution",
            "mcp_tool_call",
            "function_call",
            "function_call_output",
            "custom_tool_call",
            "custom_tool_call_output",
            "shell_call",
            "shell_call_output",
            "local_shell_call",
            "local_shell_call_output",
        }
        for event in turn_events
        if isinstance(event, dict) and isinstance(event.get("item"), dict)
    )
    response_items = list(
        response_items_with_tool_outputs(
            base_response_items,
            turn_events,
            list(response.tool_events or []),
        )
        if has_tool_history
        else [
            item.to_dict() if hasattr(item, "to_dict") else dict(item)
            for item in base_response_items
        ]
    )
    commentary_text = str(response.commentary_text or "").strip() or response_items_phase_text(
        response_items,
        phase="commentary",
    )
    payload = {
        "user_text": response.user_text,
        "assistant_text": response.assistant_text,
        "command_display_text": str(getattr(response, "command_display_text", "") or ""),
        "commentary_text": commentary_text,
        "protocol_diagnostics": dict(response.protocol_diagnostics or {}),
        "response_items": [
            item.to_dict() if hasattr(item, "to_dict") else dict(item) for item in response_items
        ],
        "attachments": [item.to_dict() for item in response.attachments],
        "handled_as_command": response.handled_as_command,
        "status": dict(response.status or {}),
        "timings": dict(response.timings or {}),
        "tool_events": [tool_event_to_dict_fn(item) for item in response.tool_events],
        "activity_events": [activity_event_to_dict_fn(item) for item in response.activity_events],
        "turn_events": canonical_turn_events_fn(response, response_items=response_items),
    }
    payload.update(continuation_fields(tool_events=list(response.tool_events or [])))
    control_requests = approval_control_protocol_runtime.control_requests_for_tool_events(
        list(response.tool_events or [])
    )
    if control_requests:
        payload["control_requests"] = control_requests
    return payload


def _prompt_response_from_command_result(
    result: CommandExecutionResult,
    *,
    user_text: str = "",
) -> PromptResponse:
    return PromptResponse(
        user_text=user_text,
        assistant_text=str(result.assistant_text or ""),
        tool_events=list(result.tool_events or []),
        handled_as_command=True,
        turn_events=[
            dict(item) for item in list(result.turn_events or []) if isinstance(item, dict)
        ],
        command_display_text=str(result.command_display_text or ""),
    )


def _is_control_response_request(request: Any) -> bool:
    return (
        isinstance(request, dict)
        and str(request.get("type") or "").strip()
        == approval_control_protocol_runtime.CONTROL_RESPONSE_TYPE
    )


def run_serve_loop(
    runner: Any,
    *,
    input_stream: TextIO,
    output_stream: TextIO,
    emit_json_line_fn: Callable[[TextIO, dict[str, Any]], None],
    request_id_for_payload_fn: Callable[[Any], str | None],
    resolve_serve_prompt_fn: Callable[[Any], str],
    execute_prompt_fn: Callable[..., Any],
    prompt_response_to_dict_fn: Callable[[Any], dict[str, Any]],
    exit_code_for_response_fn: Callable[[Any], int],
) -> int:
    def _client_output_closed(exc: BaseException) -> bool:
        if isinstance(exc, BrokenPipeError):
            return True
        return isinstance(exc, OSError) and getattr(exc, "errno", None) == errno.EPIPE

    for raw_line in input_stream:
        line = raw_line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            emit_json_line_fn(
                output_stream,
                {
                    "type": "error",
                    "error": "invalid_json",
                    "message": str(exc),
                },
            )
            continue

        request_id = request_id_for_payload_fn(request)
        if request_id is None:
            request_id = approval_control_protocol_runtime.request_id_from_control_response(request)
        if _is_control_response_request(request):
            try:
                decision_result = execute_approval_control_response(
                    runner,
                    request,
                    decided_by="headless",
                )
                response = _prompt_response_from_command_result(decision_result)
            except ValueError as exc:
                payload = {
                    "type": "error",
                    "error": "invalid_control_response",
                    "message": str(exc),
                }
                if request_id is not None:
                    payload["id"] = request_id
                try:
                    emit_json_line_fn(output_stream, payload)
                except BaseException as exc:
                    if _client_output_closed(exc):
                        return 0
                    raise
                continue
            payload = {
                "type": "response",
                "response": prompt_response_to_dict_fn(response),
                "exit_code": exit_code_for_response_fn(response),
            }
            if request_id is not None:
                payload["id"] = request_id
            try:
                emit_json_line_fn(output_stream, payload)
            except BaseException as exc:
                if _client_output_closed(exc):
                    return 0
                raise
            continue
        try:
            prompt = resolve_serve_prompt_fn(request)
        except ValueError as exc:
            payload = {
                "type": "error",
                "error": "invalid_request",
                "message": str(exc),
            }
            if request_id is not None:
                payload["id"] = request_id
            try:
                emit_json_line_fn(output_stream, payload)
            except BaseException as exc:
                if _client_output_closed(exc):
                    return 0
                raise
            continue

        stream = bool(request.get("stream"))
        try:
            response = execute_prompt_fn(
                runner,
                prompt,
                output_stream=output_stream,
                jsonl=stream,
                request_id=request_id,
            )
        except BaseException as exc:
            if _client_output_closed(exc):
                return 0
            raise
        for control_request in approval_control_protocol_runtime.control_requests_for_tool_events(
            list(getattr(response, "tool_events", []) or [])
        ):
            try:
                emit_json_line_fn(output_stream, control_request)
            except BaseException as exc:
                if _client_output_closed(exc):
                    return 0
                raise
        if stream:
            continue
        payload = {
            "type": "response",
            "response": prompt_response_to_dict_fn(response),
            "exit_code": exit_code_for_response_fn(response),
        }
        if request_id is not None:
            payload["id"] = request_id
        try:
            emit_json_line_fn(output_stream, payload)
        except BaseException as exc:
            if _client_output_closed(exc):
                return 0
            raise
    return 0

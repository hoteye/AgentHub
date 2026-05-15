from __future__ import annotations

import json
from typing import Any

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.runtime_core import (
    command_handlers_structured_helpers_runtime as _structured_helpers,
)
from cli.agent_cli.runtime_core.command_usage import _command_usage_text
from cli.agent_cli.runtime_core.request_user_input_contract_runtime import (
    normalize_request_user_input_questions,
    normalize_request_user_input_response,
)

_explicit_function_output_item_events = _structured_helpers._explicit_function_output_item_events
_next_item_index = _structured_helpers._next_item_index
_with_provider_call_id = _structured_helpers._with_provider_call_id
approval_request_text = _structured_helpers.approval_request_text
bool_option = _structured_helpers.bool_option
call_structured = _structured_helpers.call_structured
compact_arguments = _structured_helpers.compact_arguments
decode_raw_text_arg = _structured_helpers.decode_raw_text_arg
error_event = _structured_helpers.error_event
error_result = _structured_helpers.error_result
int_option = _structured_helpers.int_option
parse_json_tool_arg = _structured_helpers.parse_json_tool_arg
single_event_result = _structured_helpers.single_event_result
switch_disabled_result = _structured_helpers.switch_disabled_result
text_only_result = _structured_helpers.text_only_result


def handle_update_plan_command(runtime: Any, *, arg_text: str) -> CommandExecutionResult:
    if not arg_text:
        return text_only_result(
            _command_usage_text("update_plan") or "Usage: /update_plan '{\"plan\": [...]}'"
        )
    try:
        payload = parse_json_tool_arg(arg_text)
    except ValueError as exc:
        return error_result(
            error_event(
                "update_plan",
                "update_plan parse failed",
                error=str(exc),
                function_call_output=str(exc),
                function_call_output_model_visible=True,
            ),
        )
    mode = str(getattr(runtime, "collaboration_mode", "default") or "default").strip().lower()
    if mode == "plan":
        return error_result(
            error_event(
                "update_plan",
                "update_plan unavailable",
                error="update_plan is a TODO/checklist tool and is not allowed in Plan mode",
                function_call_output="update_plan is a TODO/checklist tool and is not allowed in Plan mode",
                function_call_output_model_visible=True,
            ),
            arguments=payload,
        )
    plan_items = payload.get("plan")
    if not isinstance(plan_items, list):
        return error_result(
            error_event(
                "update_plan",
                "update_plan parse failed",
                error="failed to parse function arguments: expected plan to be an array",
                function_call_output="failed to parse function arguments: expected plan to be an array",
                function_call_output_model_visible=True,
            ),
            arguments=payload,
        )
    normalized_plan: list[dict[str, str]] = []
    in_progress_count = 0
    for item in plan_items:
        if not isinstance(item, dict):
            return error_result(
                error_event(
                    "update_plan",
                    "update_plan parse failed",
                    error="failed to parse function arguments: expected plan entries to be objects",
                    function_call_output="failed to parse function arguments: expected plan entries to be objects",
                    function_call_output_model_visible=True,
                ),
                arguments=payload,
            )
        step = str(item.get("step") or "").strip()
        status = str(item.get("status") or "").strip()
        if not step or status not in {"pending", "in_progress", "completed"}:
            return error_result(
                error_event(
                    "update_plan",
                    "update_plan parse failed",
                    error="failed to parse function arguments: invalid plan step or status",
                    function_call_output="failed to parse function arguments: invalid plan step or status",
                    function_call_output_model_visible=True,
                ),
                arguments=payload,
            )
        if status == "in_progress":
            in_progress_count += 1
        normalized_plan.append({"step": step, "status": status})
    if in_progress_count > 1:
        return error_result(
            error_event(
                "update_plan",
                "update_plan invalid",
                error="failed to parse function arguments: at most one step can be in_progress",
                function_call_output="failed to parse function arguments: at most one step can be in_progress",
                function_call_output_model_visible=True,
            ),
            arguments=payload,
        )
    normalized_payload: dict[str, Any] = {"plan": normalized_plan}
    explanation = str(payload.get("explanation") or "").strip()
    if explanation:
        normalized_payload["explanation"] = explanation
    runtime.latest_task_plan = dict(normalized_payload)
    event_payload = _with_provider_call_id(
        {
            **normalized_payload,
            "function_call_output": "Plan updated",
            "function_call_output_model_visible": True,
        }
    )
    return single_event_result(
        "Plan updated",
        ToolEvent(
            name="update_plan",
            ok=True,
            summary="Plan updated",
            payload=event_payload,
        ),
        arguments=normalized_payload,
    )


def handle_request_user_input_command(runtime: Any, *, arg_text: str) -> CommandExecutionResult:
    if not arg_text:
        return text_only_result(
            _command_usage_text("request_user_input")
            or "Usage: /request_user_input '{\"questions\": [...]}'"
        )
    try:
        payload = parse_json_tool_arg(arg_text)
    except ValueError as exc:
        return error_result(
            error_event("request_user_input", "request_user_input parse failed", error=str(exc)),
        )
    questions = payload.get("questions")
    try:
        normalized_questions = normalize_request_user_input_questions(questions)
    except ValueError as exc:
        return error_result(
            error_event(
                "request_user_input",
                "request_user_input parse failed",
                error=str(exc),
            ),
        )
    mode = str(getattr(runtime, "collaboration_mode", "default") or "default").strip().lower()
    default_mode_enabled = bool(getattr(runtime, "default_mode_request_user_input", False))
    if not (mode == "plan" or (default_mode_enabled and mode == "default")):
        mode_name = (
            "Plan"
            if mode == "plan"
            else ("Default" if mode == "default" else mode.replace("_", " ").title())
        )
        return error_result(
            error_event(
                "request_user_input",
                "request_user_input unavailable",
                error=f"request_user_input is unavailable in {mode_name} mode",
                function_call_output=f"request_user_input is unavailable in {mode_name} mode",
                function_call_output_model_visible=True,
            ),
            arguments={"questions": normalized_questions},
        )
    handler = getattr(runtime, "request_user_input_handler", None)
    if not callable(handler):
        return error_result(
            error_event(
                "request_user_input",
                "request_user_input cancelled",
                error="request_user_input was cancelled before receiving a response",
                function_call_output="request_user_input was cancelled before receiving a response",
                function_call_output_model_visible=True,
            ),
            arguments={"questions": normalized_questions},
        )
    response = handler({"questions": normalized_questions})
    if not isinstance(response, dict):
        return error_result(
            error_event(
                "request_user_input",
                "request_user_input cancelled",
                error="request_user_input was cancelled before receiving a response",
                function_call_output="request_user_input was cancelled before receiving a response",
                function_call_output_model_visible=True,
            ),
            arguments={"questions": normalized_questions},
        )
    normalized_response = normalize_request_user_input_response(
        response,
        question_ids={str(item.get("id") or "").strip() for item in normalized_questions},
    )
    event_payload = _with_provider_call_id(
        {
            "questions": normalized_questions,
            "response": normalized_response,
            "function_call_output": normalized_response,
            "function_call_output_model_visible": True,
        }
    )
    return single_event_result(
        json.dumps(normalized_response, ensure_ascii=False),
        ToolEvent(
            name="request_user_input",
            ok=True,
            summary="request_user_input completed",
            payload=event_payload,
        ),
        arguments={"questions": normalized_questions},
    )

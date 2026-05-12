from __future__ import annotations

import json
import shlex
from typing import Any, Dict, List

from cli.agent_cli import approval_contract_runtime
from cli.agent_cli.models import (
    CommandExecutionResult,
    FunctionCallOutputPayload,
    ToolEvent,
    generic_tool_call_item_events,
    shell_tool_call_item_events,
    tool_event_is_soft_failure,
    tool_event_result_text,
)
from cli.agent_cli.runtime_core.command_usage import _command_usage_text
from cli.agent_cli.runtime_core.request_user_input_contract_runtime import (
    normalize_request_user_input_questions,
    normalize_request_user_input_response,
)
from cli.agent_cli.runtime_core.tool_call_context_runtime import (
    current_provider_tool_call_id,
)


def decode_raw_text_arg(arg_text: str) -> str:
    raw = str(arg_text or "").strip()
    if not raw:
        return ""
    if raw[0] in {"'", '"'}:
        try:
            tokens = shlex.split(raw, posix=True)
        except ValueError:
            return raw
        if len(tokens) == 1:
            return tokens[0]
    return raw


def error_event(name: str, summary: str, *, error: str, **payload: Any) -> ToolEvent:
    provider_call_id = current_provider_tool_call_id()
    return ToolEvent(
        name=name,
        ok=False,
        summary=summary,
        payload={
            "ok": False,
            "error": error,
            **({"provider_call_id": provider_call_id} if provider_call_id else {}),
            **payload,
        },
    )


def _with_provider_call_id(payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized_payload = dict(payload or {})
    provider_call_id = current_provider_tool_call_id()
    if provider_call_id:
        normalized_payload.setdefault("provider_call_id", provider_call_id)
    return normalized_payload


def compact_arguments(payload: Dict[str, Any]) -> Dict[str, Any]:
    compact: Dict[str, Any] = {}
    for key, value in dict(payload or {}).items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        compact[key] = value
    return compact


def _next_item_index(item_events: List[Dict[str, Any]]) -> int:
    next_index = 0
    for raw_event in list(item_events or []):
        if not isinstance(raw_event, dict):
            continue
        item = raw_event.get("item")
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "").strip()
        if not item_id.startswith("item_"):
            continue
        try:
            next_index = max(next_index, int(item_id.split("_", 1)[1]) + 1)
        except (TypeError, ValueError):
            continue
    return next_index


def _explicit_function_output_item_events(event: ToolEvent, *, item_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    payload = dict(event.payload or {})
    if not bool(payload.get("function_call_output_model_visible")):
        return []
    explicit_output = payload.get("function_call_output")
    if explicit_output is None:
        return []
    call_id = str(payload.get("provider_call_id") or payload.get("call_id") or "").strip()
    if not call_id:
        return []
    for raw_event in list(item_events or []):
        if not isinstance(raw_event, dict):
            continue
        item = raw_event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() not in {"function_call_output", "custom_tool_call_output"}:
            continue
        if str(item.get("call_id") or "").strip() == call_id:
            return []
    output_payload = FunctionCallOutputPayload.from_output(explicit_output, success=bool(event.ok))
    output_item_type = (
        "custom_tool_call_output"
        if str(payload.get("provider_tool_type") or "").strip().lower() == "custom_tool_call"
        else "function_call_output"
    )
    item: Dict[str, Any] = {
        "id": f"item_{_next_item_index(item_events)}",
        "type": output_item_type,
        "call_id": call_id,
        "output": output_payload.wire_value(),
    }
    if output_payload.success is not None:
        item["success"] = output_payload.success
    return [{"type": "item.completed", "item": item}]


def single_event_result(
    prefix: str,
    event: ToolEvent,
    *,
    arguments: Dict[str, Any] | None = None,
    tool_name: str | None = None,
    prefer_result_text: bool = False,
) -> CommandExecutionResult:
    resolved_tool_name = str(tool_name or event.name or "").strip()
    normalized_arguments = compact_arguments(arguments or {})
    if resolved_tool_name.startswith("shell") or resolved_tool_name in {"exec_command", "write_stdin"}:
        item_events = shell_tool_call_item_events(
            event,
            command=str(normalized_arguments.get("command") or (event.payload or {}).get("command") or "").strip() or None,
        )
    else:
        item_events = generic_tool_call_item_events(
            tool_name=resolved_tool_name,
            arguments=normalized_arguments or None,
            ok=bool(event.ok),
            summary=str(event.summary or ""),
            structured_content=dict(event.payload or {}),
        )
        item_events.extend(_explicit_function_output_item_events(event, item_events=item_events))
    assistant_text = str(prefix or "")
    if prefer_result_text and (event.ok or tool_event_is_soft_failure(event)):
        assistant_text = str(tool_event_result_text(event) or assistant_text)
    return CommandExecutionResult(
        assistant_text=assistant_text,
        tool_events=[event],
        item_events=item_events,
    )


def error_result(
    event: ToolEvent,
    *,
    arguments: Dict[str, Any] | None = None,
    tool_name: str | None = None,
) -> CommandExecutionResult:
    message = str((event.payload or {}).get("error") or event.summary or "").strip() or "tool failed"
    return single_event_result(message, event, arguments=arguments, tool_name=tool_name)


def call_structured(target: Any, method_name: str, *args: Any, **kwargs: Any) -> CommandExecutionResult | None:
    method = getattr(target, method_name, None)
    if not callable(method):
        return None
    result = method(*args, **kwargs)
    return result if isinstance(result, CommandExecutionResult) else None


def text_only_result(text: str) -> CommandExecutionResult:
    return CommandExecutionResult(
        assistant_text=str(text or ""),
        tool_events=[],
        item_events=[],
    )


def switch_disabled_result(exc: Exception) -> tuple[str, list[ToolEvent]]:
    return (str(exc) or "provider switch disabled", [])


def parse_json_tool_arg(arg_text: str) -> Dict[str, Any]:
    decoded = decode_raw_text_arg(arg_text)
    try:
        payload = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise ValueError(f"failed to parse function arguments: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("failed to parse function arguments: expected object")
    return dict(payload)


def int_option(value: Any, *, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"invalid integer value: {value}") from None


def bool_option(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean value: {value}")


def approval_request_text(prefix: str, event: ToolEvent) -> str:
    payload = event.payload or {}
    approval_id = str(payload.get("approval_id") or "").strip()
    if not approval_id:
        return prefix
    commands = approval_contract_runtime.approval_option_commands(
        approval_id,
        payload.get("available_decisions"),
    )
    if not commands:
        commands = [f"/approve {approval_id}", f"/reject {approval_id}"]
    return (
        f"{prefix}\n\n"
        f"approval_id={approval_id}\n"
        + "\n".join(commands)
    )


def handle_update_plan_command(runtime: Any, *, arg_text: str) -> CommandExecutionResult:
    if not arg_text:
        return text_only_result(_command_usage_text("update_plan") or "Usage: /update_plan '{\"plan\": [...]}'")
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
    normalized_plan: List[Dict[str, str]] = []
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
    normalized_payload: Dict[str, Any] = {"plan": normalized_plan}
    explanation = str(payload.get("explanation") or "").strip()
    if explanation:
        normalized_payload["explanation"] = explanation
    setattr(runtime, "latest_task_plan", dict(normalized_payload))
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
            _command_usage_text("request_user_input") or "Usage: /request_user_input '{\"questions\": [...]}'"
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
        mode_name = "Plan" if mode == "plan" else ("Default" if mode == "default" else mode.replace("_", " ").title())
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

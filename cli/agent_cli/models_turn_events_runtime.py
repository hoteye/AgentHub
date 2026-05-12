from __future__ import annotations

from typing import Any

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.models_event_runtime import tool_event_payload_result_text
from cli.agent_cli.models_turn_events_normalization_helpers_runtime import (
    canonical_plugin_tool_structured_content,
    normalized_plan_payload,
    normalized_plugin_observability_from_payload,
    plan_payload_from_todo_list_item,
    plugin_result_validation_error,
    todo_list_items_from_plan_payload,
    todo_list_turn_event_from_plan_payload,
    todo_list_turn_item_from_plan_payload,
)
from cli.agent_cli.models_turn_events_projection_helpers_runtime import (
    canonical_command_execution_item_from_provider_shell_payload,
    native_web_search_turn_item_from_response_item,
    plugin_observability_from_turn_item,
    response_item_to_turn_item,
)
from cli.agent_cli.models_turn_events_pure_helpers_runtime import (
    command_execution_metadata_from_payload,
    derived_arguments_from_payload,
    normalized_text,
)
from cli.agent_cli.web_search_argument_projection_runtime import (
    looks_like_web_search_result_payload as _looks_like_web_search_result_payload_shared,
    normalized_web_search_mcp_call_arguments as _normalized_web_search_mcp_call_arguments_shared,
)


def generic_tool_call_item_events(
    *,
    tool_name: str,
    arguments: Any,
    ok: bool,
    summary: str,
    structured_content: dict[str, Any] | None,
    error_message: str,
    item_id: str,
    server: str,
) -> list[dict[str, Any]]:
    payload = dict(structured_content or {})
    normalized_tool_name = str(tool_name or "").strip()
    if normalized_tool_name == "update_plan":
        return [todo_list_turn_event_from_plan_payload(payload, item_id=item_id, event_type="item.started")]
    soft_failure = (not bool(ok)) and (payload.get("result_success") is False) and (not str(payload.get("error") or "").strip())
    plugin_observability = normalized_plugin_observability_from_payload(payload, tool_name=normalized_tool_name)
    validation_error = plugin_result_validation_error(
        payload,
        summary=str(summary or ""),
        tool_name=normalized_tool_name,
    )
    result_text = tool_event_payload_result_text(payload, summary=str(summary or ""))
    result = None
    error = None
    if validation_error:
        error = {"message": validation_error}
    elif ok or soft_failure:
        result = {
            "content": ([{"type": "text", "text": result_text}] if result_text else []),
            "structured_content": canonical_plugin_tool_structured_content(
                payload,
                tool_name=normalized_tool_name,
                status="completed",
                summary=str(summary or ""),
            ),
        }
    else:
        resolved_error = str(error_message or payload.get("error") or summary or f"{tool_name} failed").strip()
        error = {"message": resolved_error}
    item = {
        "id": item_id,
        "type": "mcp_tool_call",
        "server": str((plugin_observability or {}).get("server_name") or "").strip() or str(server or "local"),
        "tool": normalized_tool_name,
        "arguments": arguments,
        "result": result,
        "error": error,
        "status": "completed" if ((ok or soft_failure) and not validation_error) else "failed",
    }
    call_id = normalized_text(payload.get("provider_call_id") or payload.get("call_id"))
    if call_id:
        item["call_id"] = call_id
    if plugin_observability is not None:
        item["plugin_observability"] = plugin_observability
    return [
        {"type": "item.started", "item": {**item, "result": None, "error": None, "status": "in_progress"}},
        {"type": "item.completed", "item": item},
    ]


def shell_tool_event_to_turn_items(
    *,
    tool_event: ToolEvent,
    item_id: str,
    reference_wrapped_shell_command_fn: Any,
    shell_aggregated_output_fn: Any,
    shell_exit_code_fn: Any,
    shell_status_fn: Any,
) -> list[dict[str, Any]]:
    payload = dict(tool_event.payload or {})
    raw_command = str(payload.get("command") or tool_event.summary or tool_event.name or "").strip()
    command = reference_wrapped_shell_command_fn(payload, raw_command)
    aggregated_output = shell_aggregated_output_fn(payload)
    exit_code = shell_exit_code_fn(payload)
    status = shell_status_fn(tool_event)
    suppress_output_update = bool(payload.get("suppress_output_update"))
    call_id = str(payload.get("provider_call_id") or payload.get("call_id") or "").strip()
    resolved_item_id = call_id or str(item_id or "")
    command_item: dict[str, Any] = {
        "id": resolved_item_id,
        "type": "command_execution",
        "command": command,
        "aggregated_output": "",
        "exit_code": None,
        "status": "in_progress",
    }
    if call_id:
        command_item["call_id"] = call_id
    command_item.update(command_execution_metadata_from_payload(payload))
    events: list[dict[str, Any]] = [
        {
            "type": "item.started",
            "item": dict(command_item),
        }
    ]
    if aggregated_output and not suppress_output_update:
        events.append(
            {
                "type": "item.updated",
                "item": {
                    **command_item,
                    "aggregated_output": aggregated_output,
                },
            }
        )
    events.append(
        {
            "type": "item.completed",
            "item": {
                **command_item,
                "aggregated_output": aggregated_output,
                "exit_code": exit_code,
                "status": status,
            },
        }
    )
    return events


def generic_tool_event_to_turn_items(
    *,
    tool_event: ToolEvent,
    item_id: str,
    tool_event_is_soft_failure_fn: Any,
    tool_event_result_text_fn: Any,
    generic_tool_error_message_fn: Any,
) -> list[dict[str, Any]]:
    payload = dict(tool_event.payload or {})
    normalized_tool_name = str(tool_event.name or "").strip()
    plugin_observability = normalized_plugin_observability_from_payload(payload, tool_name=normalized_tool_name)
    validation_error = plugin_result_validation_error(
        payload,
        summary=str(tool_event.summary or ""),
        tool_name=normalized_tool_name,
    )
    arguments: Any = payload.get("function_call_arguments")
    if arguments is None:
        arguments = payload.get("arguments")
    if arguments is None and "args" in payload:
        arguments = payload.get("args")
    derived_arguments = derived_arguments_from_payload(normalized_tool_name, payload)
    if normalized_tool_name == "web_search" and _looks_like_web_search_result_payload_shared(arguments):
        arguments = _normalized_web_search_mcp_call_arguments_shared(
            {
                "tool": "web_search",
                "arguments": arguments,
                "result": {"structured_content": arguments} if isinstance(arguments, dict) else {},
            }
        )
    elif _looks_like_web_search_result_payload_shared(arguments) and derived_arguments is not None:
        arguments = derived_arguments
    if arguments is None:
        arguments = derived_arguments
    soft_failure = tool_event_is_soft_failure_fn(tool_event)
    result_text = tool_event_result_text_fn(tool_event)
    result = None
    error = None
    if validation_error:
        error = {"message": validation_error}
    elif tool_event.ok or soft_failure:
        result = {
            "content": ([{"type": "text", "text": result_text}] if result_text else []),
            "structured_content": canonical_plugin_tool_structured_content(
                payload,
                tool_name=normalized_tool_name,
                status="completed",
                summary=str(tool_event.summary or ""),
            ),
        }
    else:
        error = {"message": generic_tool_error_message_fn(tool_event)}
    item = {
        "id": item_id,
        "type": "mcp_tool_call",
        "server": str((plugin_observability or {}).get("server_name") or "local"),
        "tool": normalized_tool_name,
        "arguments": arguments,
        "result": result,
        "error": error,
        "status": "completed" if ((tool_event.ok or soft_failure) and not validation_error) else "failed",
    }
    call_id = normalized_text(payload.get("provider_call_id") or payload.get("call_id"))
    if call_id:
        item["call_id"] = call_id
    if plugin_observability is not None:
        item["plugin_observability"] = plugin_observability
    started_item = {**item, "result": None, "error": None, "status": "in_progress"}
    if normalized_tool_name == "web_search":
        started_item["search_phase"] = "search_dispatched"
        item["search_phase"] = "search_results_received"
    return [
        {"type": "item.started", "item": started_item},
        {"type": "item.completed", "item": item},
    ]


__all__ = [
    "canonical_command_execution_item_from_provider_shell_payload",
    "canonical_plugin_tool_structured_content",
    "generic_tool_call_item_events",
    "generic_tool_event_to_turn_items",
    "native_web_search_turn_item_from_response_item",
    "normalized_plan_payload",
    "normalized_plugin_observability_from_payload",
    "plan_payload_from_todo_list_item",
    "plugin_observability_from_turn_item",
    "plugin_result_validation_error",
    "response_item_to_turn_item",
    "shell_tool_event_to_turn_items",
    "todo_list_items_from_plan_payload",
    "todo_list_turn_event_from_plan_payload",
    "todo_list_turn_item_from_plan_payload",
]

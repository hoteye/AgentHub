from __future__ import annotations

import json
from typing import Any, Dict, List

from cli.agent_cli import (
    models_response_projection_normalization_helpers_runtime as normalization_service,
)
from cli.agent_cli.models import FunctionCallOutputPayload, ResponseInputItem
from cli.agent_cli.models_turn_events import _turn_event_content_text, plan_payload_from_todo_list_item
from cli.agent_cli.models_turn_events_runtime import plugin_observability_from_turn_item


def command_execution_output_text(item: Dict[str, Any]) -> str:
    sections: list[str] = []
    duration_ms = item.get("duration_ms")
    if duration_ms is not None:
        try:
            sections.append(f"Wall time: {float(duration_ms) / 1000:.4f} seconds")
        except (TypeError, ValueError):
            pass
    exit_code = item.get("exit_code")
    if exit_code is not None:
        sections.append(f"Process exited with code {exit_code}")
    else:
        process_id = str(item.get("process_id") or "").strip()
        if process_id:
            sections.append(f"Process running with session ID {process_id}")
    sections.append("Output:")
    sections.append(str(item.get("aggregated_output") or ""))
    return "\n".join(sections)


def _serialized_call_arguments(arguments_value: Any) -> str:
    try:
        return json.dumps(arguments_value or {}, ensure_ascii=False)
    except TypeError:
        return "{}"


def _turn_item_result_structured_content(item: Dict[str, Any]) -> Dict[str, Any]:
    result = item.get("result")
    if not isinstance(result, dict):
        return {}
    structured_content = result.get("structured_content")
    if not isinstance(structured_content, dict):
        return {}
    return dict(structured_content)


def _apply_patch_arguments_look_structured(arguments_value: Any) -> bool:
    if not isinstance(arguments_value, dict):
        return False
    operation = str(arguments_value.get("operation") or "").strip().lower()
    if operation in {"file_write", "file_edit"}:
        return True
    for key in ("file_path", "content", "old_string", "new_string"):
        if arguments_value.get(key) not in (None, ""):
            return True
    return bool(arguments_value.get("replace_all"))


def _normalized_apply_patch_replay_arguments(
    arguments_value: Any,
    *,
    request_kind: str,
) -> Any:
    if not isinstance(arguments_value, dict):
        return arguments_value
    normalized_request_kind = str(request_kind or "").strip().lower()
    operation = str(arguments_value.get("operation") or "").strip().lower()
    if not normalized_request_kind:
        if operation == "file_write" or (
            "content" in arguments_value and not any(key in arguments_value for key in ("old_string", "new_string"))
        ):
            normalized_request_kind = "structured_write"
        elif operation == "file_edit" or any(key in arguments_value for key in ("old_string", "new_string", "replace_all")):
            normalized_request_kind = "structured_edit"
    if normalized_request_kind == "structured_write":
        normalized = {
            "file_path": arguments_value.get("file_path"),
            "content": arguments_value.get("content"),
        }
        return {
            key: value
            for key, value in normalized.items()
            if value not in (None, "")
        }
    if normalized_request_kind == "structured_edit":
        normalized = {
            "file_path": arguments_value.get("file_path"),
            "old_string": arguments_value.get("old_string"),
            "new_string": arguments_value.get("new_string"),
        }
        if arguments_value.get("replace_all"):
            normalized["replace_all"] = True
        return {
            key: value
            for key, value in normalized.items()
            if value not in (None, "")
        }
    return arguments_value


def _apply_patch_turn_item_projection(
    item: Dict[str, Any],
    arguments_value: Any,
) -> tuple[str, str, Any]:
    structured_content = _turn_item_result_structured_content(item)
    provider_tool_type = str(
        item.get("provider_tool_type")
        or structured_content.get("provider_tool_type")
        or ""
    ).strip().lower()
    request_kind = str(
        item.get("request_kind")
        or structured_content.get("request_kind")
        or ""
    ).strip().lower()
    name = str(
        item.get("function_call_name")
        or structured_content.get("function_call_name")
        or item.get("tool")
        or "apply_patch"
    ).strip() or "apply_patch"
    replay_arguments = item.get("function_call_arguments")
    if replay_arguments is None:
        replay_arguments = structured_content.get("function_call_arguments")
    if replay_arguments is None:
        replay_arguments = arguments_value
    replay_arguments = _normalized_apply_patch_replay_arguments(
        replay_arguments,
        request_kind=request_kind,
    )
    if provider_tool_type in {"function_call", "custom_tool_call"}:
        return provider_tool_type, name, replay_arguments
    if request_kind in {"structured_write", "structured_edit"}:
        return "function_call", name, replay_arguments
    if _apply_patch_arguments_look_structured(replay_arguments):
        return "function_call", name, replay_arguments
    return "custom_tool_call", name, replay_arguments


def _project_tool_history_call_item(item: Dict[str, Any]) -> Dict[str, Any] | None:
    call_id = str(item.get("call_id") or item.get("tool_call_id") or item.get("id") or "").strip()
    if not call_id:
        return None
    item_type = str(item.get("type") or "").strip().lower()
    if item_type == "command_execution":
        name = str(item.get("function_call_name") or "").strip() or "exec_command"
        arguments_value = item.get("function_call_arguments")
        if arguments_value is None:
            arguments_value = {"cmd": str(item.get("command") or "").strip()}
        output_item_type = "function_call"
    elif item_type == "todo_list":
        name = "update_plan"
        arguments_value = plan_payload_from_todo_list_item(item)
        output_item_type = "function_call"
    else:
        name = str(item.get("tool") or "").strip()
        arguments_value = normalization_service.normalized_mcp_call_arguments(item)
        output_item_type = "function_call"
        if name == "apply_patch":
            output_item_type, name, arguments_value = _apply_patch_turn_item_projection(item, arguments_value)
    extra = {
        "name": name,
        "call_id": call_id,
    }
    provider_item_id = str(item.get("provider_item_id") or "").strip()
    if provider_item_id and not normalization_service.is_synthetic_tool_item_id(provider_item_id):
        extra["id"] = provider_item_id
    plugin_observability = plugin_observability_from_turn_item(item)
    if plugin_observability is not None:
        extra["plugin_observability"] = plugin_observability
    if output_item_type == "custom_tool_call":
        argument_map = arguments_value if isinstance(arguments_value, dict) else {}
        extra["input"] = str(argument_map.get("patch") or argument_map.get("input") or "").strip()
    else:
        extra["arguments"] = _serialized_call_arguments(arguments_value)
    return ResponseInputItem(
        item_type=output_item_type,
        extra=extra,
    ).to_dict()


def tool_output_input_items_from_turn_events_projection(
    turn_events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen_call_ids: set[str] = set()
    for raw_event in list(turn_events or []):
        if not isinstance(raw_event, dict):
            continue
        if str(raw_event.get("type") or "").strip() != "item.completed":
            continue
        item = raw_event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip().lower()
        if normalization_service.is_tool_call_output_item_type(item_type):
            call_id = str(item.get("call_id") or item.get("id") or "").strip()
            if not call_id or call_id in seen_call_ids:
                continue
            seen_call_ids.add(call_id)
            items.append(ResponseInputItem.from_dict(item).to_dict())
            continue
        if not normalization_service.is_turn_event_tool_history_item_type(item_type):
            continue
        call_id = str(item.get("call_id") or item.get("tool_call_id") or item.get("id") or "").strip()
        if not call_id or call_id in seen_call_ids:
            continue
        seen_call_ids.add(call_id)

        output_value: Any
        success: bool | None
        if item_type == "command_execution":
            output_value = command_execution_output_text(item)
            status = str(item.get("status") or "").strip().lower()
            exit_code = item.get("exit_code")
            success = status in {"completed", "running", "in_progress"} and (exit_code in {None, 0})
        elif item_type == "todo_list":
            output_value = "Plan updated"
            success = True
        else:
            result = dict(item.get("result") or {}) if isinstance(item.get("result"), dict) else {}
            error = dict(item.get("error") or {}) if isinstance(item.get("error"), dict) else {}
            structured = result.get("structured_content")
            content_text = _turn_event_content_text(result.get("content")).strip()
            error_message = str(error.get("message") or "").strip()
            tool_name = str(item.get("tool") or "").strip()
            prefer_text_output = normalization_service.is_text_first_tool(tool_name)
            if prefer_text_output and content_text:
                output_value = content_text
            elif prefer_text_output and error_message:
                output_value = error_message
            elif structured is not None:
                output_value = structured
            elif content_text:
                output_value = content_text
            elif error_message:
                output_value = {"error": error_message}
            else:
                output_value = {
                    "tool": tool_name,
                    "status": str(item.get("status") or "").strip(),
                }
            success = not error_message and str(item.get("status") or "").strip().lower() == "completed"

        payload = FunctionCallOutputPayload.from_output(output_value, success=success)
        extra = {
            "call_id": call_id,
            "output": payload.wire_value(),
            "success": payload.success,
        }
        plugin_observability = plugin_observability_from_turn_item(item)
        if plugin_observability is not None:
            extra["plugin_observability"] = plugin_observability
        items.append(
            ResponseInputItem(
                item_type="function_call_output",
                extra=extra,
            ).to_dict()
        )
    return items


def function_call_input_items_from_turn_events_projection(
    turn_events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen_call_ids: set[str] = set()
    for raw_event in list(turn_events or []):
        if not isinstance(raw_event, dict):
            continue
        if str(raw_event.get("type") or "").strip() not in {"item.started", "item.completed"}:
            continue
        item = raw_event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip().lower()
        if normalization_service.is_tool_call_input_item_type(item_type):
            call_id = str(item.get("call_id") or item.get("id") or "").strip()
            if call_id and call_id not in seen_call_ids:
                seen_call_ids.add(call_id)
                items.append(
                    normalization_service.sanitize_tool_input_item(
                        ResponseInputItem.from_dict(item).to_dict()
                    )
                )
            continue
        if not normalization_service.is_turn_event_tool_history_item_type(item_type):
            continue
        projected_item = _project_tool_history_call_item(item)
        if projected_item is None:
            continue
        call_id = str(projected_item.get("call_id") or projected_item.get("tool_call_id") or "").strip()
        if call_id in seen_call_ids:
            continue
        seen_call_ids.add(call_id)
        items.append(projected_item)
    return items


def provider_tool_call_input_items_from_turn_events(
    turn_events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen_call_ids: set[str] = set()
    for raw_event in list(turn_events or []):
        if not isinstance(raw_event, dict):
            continue
        if str(raw_event.get("type") or "").strip() not in {"item.started", "item.completed"}:
            continue
        item = raw_event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip().lower()
        if not normalization_service.is_tool_call_input_item_type(item_type):
            continue
        call_id = str(item.get("call_id") or item.get("id") or "").strip()
        if not call_id or call_id in seen_call_ids:
            continue
        seen_call_ids.add(call_id)
        items.append(normalization_service.sanitize_tool_input_item(ResponseInputItem.from_dict(item).to_dict()))
    return items


def projected_structured_call_items_from_turn_events(
    turn_events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen_call_ids: set[str] = set()
    for raw_event in list(turn_events or []):
        if not isinstance(raw_event, dict):
            continue
        if str(raw_event.get("type") or "").strip() not in {"item.started", "item.completed"}:
            continue
        item = raw_event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip().lower()
        if not normalization_service.is_turn_event_tool_history_item_type(item_type):
            continue
        projected_item = _project_tool_history_call_item(item)
        if projected_item is None:
            continue
        call_id = str(projected_item.get("call_id") or projected_item.get("tool_call_id") or "").strip()
        if call_id in seen_call_ids:
            continue
        seen_call_ids.add(call_id)
        items.append(projected_item)
    return items

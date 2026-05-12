from __future__ import annotations

from typing import Any

from cli.agent_cli.models import ResponseInputItem
from cli.agent_cli.models_turn_events_pure_helpers_runtime import (
    command_execution_metadata_from_payload,
    reasoning_summary_text_from_extra,
    shell_command_text_from_action,
    shell_output_aggregated_text,
    shell_output_exit_code,
)
from cli.agent_cli.web_search_argument_projection_runtime import (
    derived_web_search_arguments_from_payload as _derived_web_search_arguments_from_payload_shared,
)


def plugin_observability_from_turn_item(item: dict[str, Any] | None) -> dict[str, Any] | None:
    payload = dict(item or {})
    direct = payload.get("plugin_observability")
    if isinstance(direct, dict):
        return dict(direct)
    result = payload.get("result")
    if isinstance(result, dict):
        structured_content = result.get("structured_content")
        if isinstance(structured_content, dict):
            nested = structured_content.get("plugin_observability")
            if isinstance(nested, dict):
                return dict(nested)
    return None


def canonical_command_execution_item_from_provider_shell_payload(
    payload: dict[str, Any] | None,
    *,
    item_id: str,
) -> dict[str, Any] | None:
    raw = dict(payload or {})
    item_type = str(raw.get("type") or "").strip().lower()
    if item_type not in {"shell_call", "local_shell_call", "shell_call_output", "local_shell_call_output"}:
        return None
    call_id = str(raw.get("call_id") or raw.get("id") or item_id).strip() or str(item_id or "")
    command_text = shell_command_text_from_action(raw.get("action")) or str(raw.get("command") or "").strip()
    status = str(raw.get("status") or "").strip() or "completed"
    event_item: dict[str, Any] = {
        "id": call_id or str(item_id or ""),
        "type": "command_execution",
        "status": status,
        "aggregated_output": "",
        "exit_code": None,
    }
    if call_id:
        event_item["call_id"] = call_id
    if command_text:
        event_item["command"] = command_text
    output = raw.get("output")
    aggregated_output = shell_output_aggregated_text(output)
    if aggregated_output:
        event_item["aggregated_output"] = aggregated_output
    exit_code = shell_output_exit_code(output)
    if exit_code is not None:
        event_item["exit_code"] = exit_code
    event_item.update(command_execution_metadata_from_payload(raw))
    return event_item


def native_web_search_turn_item_from_response_item(
    item: ResponseInputItem,
    *,
    item_id: str,
    search_phase: str | None = None,
) -> dict[str, Any]:
    extra = dict(getattr(item, "extra", {}) or {})
    event_item: dict[str, Any] = {
        "id": str(extra.get("id") or item_id),
        "type": "web_search_call",
        **{key: value for key, value in extra.items() if key != "id"},
    }
    query_text = str(_derived_web_search_arguments_from_payload_shared(event_item).get("query") or "").strip()
    if query_text and not str(event_item.get("query") or "").strip():
        event_item["query"] = query_text
    if not str(event_item.get("status") or "").strip():
        event_item["status"] = "completed"
    resolved_search_phase = str(search_phase or "").strip() or "search_results_received"
    event_item["search_phase"] = resolved_search_phase
    return event_item


def response_item_to_turn_item(
    item: ResponseInputItem,
    *,
    item_id: str,
    turn_event_content_text_fn: Any,
    turn_event_content_types_fn: Any,
) -> dict[str, Any] | None:
    item_type = str(getattr(item, "item_type", "") or "").strip().lower()
    role = str(getattr(item, "role", "") or "").strip().lower()
    content = getattr(item, "content", None)
    text = turn_event_content_text_fn(content).strip()
    content_types = turn_event_content_types_fn(content)
    if item_type == "reasoning" or "reasoning" in content_types:
        extra = dict(getattr(item, "extra", {}) or {})
        if not text:
            text = reasoning_summary_text_from_extra(extra)
        if not text:
            return None
        event_item: dict[str, Any] = {"id": item_id, "type": "reasoning", "text": text}
        for key in ("status", "summary", "encrypted_content"):
            value = extra.get(key)
            if value not in (None, ""):
                event_item[key] = value
        provider_item_id = str(extra.get("id") or "").strip()
        if provider_item_id:
            event_item["provider_item_id"] = provider_item_id
        return event_item
    if item_type == "web_search_call":
        return native_web_search_turn_item_from_response_item(item, item_id=item_id)
    if item_type in {"shell_call", "local_shell_call", "shell_call_output", "local_shell_call_output"}:
        extra = dict(getattr(item, "extra", {}) or {})
        return canonical_command_execution_item_from_provider_shell_payload(
            {"type": item_type, **extra},
            item_id=item_id,
        )
    if item_type in {"function_call", "custom_tool_call", "shell_call", "local_shell_call"}:
        return {
            "id": str((getattr(item, "extra", {}) or {}).get("id") or item_id),
            "type": item_type,
            **{key: value for key, value in dict(getattr(item, "extra", {}) or {}).items() if key not in {"id"}},
        }
    if item_type in {"function_call_output", "custom_tool_call_output", "shell_call_output", "local_shell_call_output"}:
        return {
            "id": str((getattr(item, "extra", {}) or {}).get("id") or item_id),
            "type": item_type,
            **{key: value for key, value in dict(getattr(item, "extra", {}) or {}).items() if key not in {"id"}},
        }
    if role == "assistant" or item_type == "message":
        if not text:
            return None
        event_item = {"id": item_id, "type": "agent_message", "text": text}
        phase = str((getattr(item, "extra", {}) or {}).get("phase") or "").strip().lower()
        if phase:
            event_item["phase"] = phase
        return event_item
    return None


__all__ = [
    "canonical_command_execution_item_from_provider_shell_payload",
    "native_web_search_turn_item_from_response_item",
    "plugin_observability_from_turn_item",
    "response_item_to_turn_item",
]

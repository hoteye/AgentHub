from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli.models import ResponseInputItem
from cli.agent_cli.providers.adapters.openai_responses_output import (
    _provider_tool_call_from_payload,
    _stream_item_to_dict,
)

_PARTIAL_TOOL_CALL_ITEM_TYPES = {
    "function_call",
    "custom_tool_call",
    "shell_call",
    "local_shell_call",
}


def followup_item_signature(item: Dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    return (
        str(item.get("type") or "").strip().lower(),
        str(item.get("id") or "").strip(),
        str(item.get("call_id") or "").strip(),
        str(item.get("name") or "").strip(),
        str(item.get("status") or "").strip().lower(),
        repr(
            item.get("arguments")
            if "arguments" in item
            else item.get("input")
            if "input" in item
            else item.get("action")
            if "action" in item
            else item.get("content")
        ),
    )


def native_web_search_state_key(event: Any) -> str:
    output_index = getattr(event, "output_index", None)
    if output_index is None:
        return ""
    raw_item = _stream_item_to_dict(getattr(event, "item", None))
    item_type = str((raw_item or {}).get("type") or "").strip().lower() or "unknown"
    key_parts = [str(output_index), item_type]
    if item_type == "web_search_call":
        action = (raw_item or {}).get("action")
        query_text = ""
        if isinstance(action, dict):
            query_text = str(action.get("query") or "").strip()
            if not query_text:
                queries = action.get("queries")
                if isinstance(queries, list):
                    for entry in queries:
                        text = str(entry or "").strip()
                        if text:
                            query_text = text
                            break
        if query_text:
            key_parts.append(query_text)
    return ":".join(key_parts)


def remember_native_web_search_item_id(state: Dict[str, Any], *, event: Any, item_id: str) -> None:
    state_key = native_web_search_state_key(event)
    if not state_key:
        return
    state.setdefault("native_web_search_item_ids", {})[state_key] = str(item_id)


def remember_native_web_search_pending_item(state: Dict[str, Any], *, event: Any) -> None:
    state_key = native_web_search_state_key(event)
    if not state_key:
        return
    raw_item = _stream_item_to_dict(getattr(event, "item", None))
    if str((raw_item or {}).get("type") or "").strip() != "web_search_call":
        return
    normalized = dict(raw_item)
    remembered_id = str((state.get("native_web_search_item_ids") or {}).get(state_key) or "").strip()
    if remembered_id and not str(normalized.get("id") or "").strip():
        normalized["id"] = remembered_id
    if not str(normalized.get("status") or "").strip():
        normalized["status"] = "in_progress"
    state.setdefault("pending_native_web_search_items", {})[state_key] = normalized


def drop_pending_native_web_search_item(state: Dict[str, Any], *, event: Any) -> None:
    state_key = native_web_search_state_key(event)
    if not state_key:
        return
    pending = state.get("pending_native_web_search_items")
    if isinstance(pending, dict):
        pending.pop(state_key, None)


def hydrate_native_web_search_done_item_id(state: Dict[str, Any], *, event: Any) -> None:
    raw_item = getattr(event, "item", None)
    state_key = native_web_search_state_key(event)
    if not state_key:
        return
    remembered_id = str((state.get("native_web_search_item_ids") or {}).get(state_key) or "").strip()
    if not remembered_id:
        return
    raw_payload = _stream_item_to_dict(raw_item)
    if str((raw_payload or {}).get("type") or "").strip() != "web_search_call":
        return
    if str((raw_payload or {}).get("id") or "").strip():
        return
    if isinstance(raw_item, dict):
        raw_item["id"] = remembered_id
        return
    try:
        setattr(raw_item, "id", remembered_id)
    except Exception:
        return


def recover_pending_native_web_search_items(
    *,
    state: Dict[str, Any],
    response_items: List[ResponseInputItem],
    followup_items: List[Dict[str, Any]],
) -> None:
    pending = state.get("pending_native_web_search_items")
    if not isinstance(pending, dict) or not pending:
        return
    existing_followup_ids = {
        str(item.get("id") or "").strip()
        for item in list(followup_items or [])
        if isinstance(item, dict)
    }
    existing_followup_signatures = {
        followup_item_signature(item)
        for item in list(followup_items or [])
        if isinstance(item, dict)
    }
    for raw_item in list(pending.values()):
        if not isinstance(raw_item, dict):
            continue
        normalized = dict(raw_item)
        if not str(normalized.get("status") or "").strip():
            normalized["status"] = "in_progress"
        item_id = str(normalized.get("id") or "").strip()
        signature = followup_item_signature(normalized)
        if item_id and item_id in existing_followup_ids:
            continue
        if signature in existing_followup_signatures:
            continue
        response_items.append(ResponseInputItem.from_dict(normalized))
        followup_items.append(normalized)
        if item_id:
            existing_followup_ids.add(item_id)
        existing_followup_signatures.add(signature)


def recover_pending_tool_call_items(
    *,
    state: Dict[str, Any],
    response_items: List[ResponseInputItem],
    tool_calls: List[Any],
    followup_items: List[Dict[str, Any]],
) -> None:
    pending = state.get("pending_tool_call_items")
    if not isinstance(pending, dict) or not pending:
        return
    ready_keys = state.get("pending_tool_call_ready_keys")
    if not isinstance(ready_keys, set):
        ready_keys = set()
    argument_buffers = state.get("pending_function_call_arguments")
    if not isinstance(argument_buffers, dict):
        argument_buffers = {}
    custom_input_buffers = state.get("pending_custom_tool_call_inputs")
    if not isinstance(custom_input_buffers, dict):
        custom_input_buffers = {}
    existing_tool_call_ids = {
        str(getattr(call, "call_id", "") or "").strip()
        for call in list(tool_calls or [])
    }
    existing_followup_ids = {
        str(item.get("id") or "").strip()
        for item in list(followup_items or [])
        if isinstance(item, dict)
    }
    existing_followup_call_ids = {
        str(item.get("call_id") or "").strip()
        for item in list(followup_items or [])
        if isinstance(item, dict)
    }
    existing_followup_signatures = {
        followup_item_signature(item)
        for item in list(followup_items or [])
        if isinstance(item, dict)
    }
    for key in sorted(pending):
        raw_item = pending.get(key)
        if not isinstance(raw_item, dict):
            continue
        normalized = dict(raw_item)
        raw_type = str(normalized.get("type") or "").strip()
        if raw_type not in _PARTIAL_TOOL_CALL_ITEM_TYPES:
            continue
        if raw_type == "function_call" and key in argument_buffers and "arguments" not in normalized:
            normalized["arguments"] = argument_buffers[key]
        if raw_type == "custom_tool_call" and key in custom_input_buffers and "input" not in normalized:
            normalized["input"] = custom_input_buffers[key]
        if not str(normalized.get("status") or "").strip():
            normalized["status"] = "in_progress"
        item_id = str(normalized.get("id") or "").strip()
        call_id = str(normalized.get("call_id") or "").strip()
        signature = followup_item_signature(normalized)
        if item_id and item_id in existing_followup_ids:
            continue
        if call_id and call_id in existing_followup_call_ids:
            continue
        if signature in existing_followup_signatures:
            continue
        ready_for_execution = False
        if key in ready_keys and call_id:
            provider_call = _provider_tool_call_from_payload(normalized)
            if provider_call is not None and call_id not in existing_tool_call_ids:
                tool_calls.append(provider_call)
                existing_tool_call_ids.add(call_id)
                ready_for_execution = True
        if not ready_for_execution:
            response_items.append(ResponseInputItem.from_dict(normalized))
        followup_items.append(normalized)
        if item_id:
            existing_followup_ids.add(item_id)
        if call_id:
            existing_followup_call_ids.add(call_id)
        existing_followup_signatures.add(signature)


def recover_pending_message_items(
    *,
    state: Dict[str, Any],
    response_items: List[ResponseInputItem],
    followup_items: List[Dict[str, Any]],
) -> None:
    message_buffers = state.get("message_buffers")
    if not isinstance(message_buffers, dict) or not message_buffers:
        return
    provider_item_ids = state.get("message_provider_item_ids")
    if not isinstance(provider_item_ids, dict):
        provider_item_ids = {}
    message_item_phases = state.get("message_item_phases")
    if not isinstance(message_item_phases, dict):
        message_item_phases = {}
    existing_followup_ids = {
        str(item.get("id") or "").strip()
        for item in list(followup_items or [])
        if isinstance(item, dict)
    }
    existing_message_keys = {
        (
            str(item.get("role") or "").strip().lower(),
            str(item.get("phase") or "").strip().lower(),
            str(item.get("content") or "").strip(),
        )
        for item in list(followup_items or [])
        if isinstance(item, dict) and str(item.get("type") or "").strip() == "message"
    }
    for buffer_key in sorted(message_buffers):
        text = str(message_buffers.get(buffer_key) or "").strip()
        if not text:
            continue
        phase = str(message_item_phases.get(buffer_key) or "").strip().lower()
        provider_item_id = str(provider_item_ids.get(buffer_key) or "").strip()
        normalized = {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": text}],
        }
        if phase:
            normalized["phase"] = phase
        dedupe_key = ("assistant", phase, text)
        if provider_item_id:
            if provider_item_id in existing_followup_ids:
                continue
            normalized["id"] = provider_item_id
        elif dedupe_key in existing_message_keys:
            continue
        response_items.append(ResponseInputItem.from_dict(normalized))
        followup_items.append(normalized)
        if provider_item_id:
            existing_followup_ids.add(provider_item_id)
        existing_message_keys.add(dedupe_key)

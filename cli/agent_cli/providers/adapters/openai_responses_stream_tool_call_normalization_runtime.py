from __future__ import annotations

from typing import Any

from cli.agent_cli.providers.adapters.openai_responses_stream_event_pure_helpers_runtime import (
    PARTIAL_TOOL_CALL_ITEM_TYPES,
    pending_tool_call_key,
)


def resolve_pending_tool_call_key(
    state: dict[str, Any],
    event: Any,
    *,
    raw_item: dict[str, Any] | None = None,
    item_id: str = "",
    item_type: str = "",
) -> str:
    provider_item_id = str(item_id or (raw_item or {}).get("id") or "").strip()
    by_provider_id = state.setdefault("pending_tool_call_keys_by_provider_id", {})
    if provider_item_id:
        remembered = str(by_provider_id.get(provider_item_id) or "").strip()
        if remembered:
            return remembered
    output_index = getattr(event, "output_index", None)
    by_output_index = state.setdefault("pending_tool_call_keys_by_output_index", {})
    if output_index is not None:
        remembered = str(by_output_index.get(str(output_index)) or "").strip()
        if remembered:
            if provider_item_id:
                by_provider_id[provider_item_id] = remembered
            return remembered
    key = pending_tool_call_key(
        event,
        raw_item=raw_item,
        item_id=provider_item_id,
        item_type=item_type,
    )
    if not key:
        return ""
    if output_index is not None:
        by_output_index[str(output_index)] = key
    if provider_item_id:
        by_provider_id[provider_item_id] = key
    return key


def remember_pending_tool_call_item(
    state: dict[str, Any],
    event: Any,
    *,
    raw_item: dict[str, Any],
    item_id: str = "",
    item_type: str = "",
) -> str:
    normalized_type = str(item_type or raw_item.get("type") or "").strip()
    if normalized_type not in PARTIAL_TOOL_CALL_ITEM_TYPES:
        return ""
    key = resolve_pending_tool_call_key(
        state,
        event,
        raw_item=raw_item,
        item_id=item_id,
        item_type=normalized_type,
    )
    if not key:
        return ""
    pending_items = state.setdefault("pending_tool_call_items", {})
    pending = dict(pending_items.get(key) or {})
    pending.update(raw_item)
    provider_item_id = str(item_id or raw_item.get("id") or "").strip()
    if provider_item_id:
        pending["id"] = provider_item_id
    if (
        normalized_type in {"function_call", "custom_tool_call"}
        and not str(pending.get("status") or "").strip()
    ):
        pending["status"] = "in_progress"
    if normalized_type == "function_call":
        buffered_arguments = state.setdefault("pending_function_call_arguments", {}).get(key)
        if buffered_arguments is not None and "arguments" not in raw_item:
            pending["arguments"] = buffered_arguments
    elif normalized_type == "custom_tool_call":
        buffered_input = state.setdefault("pending_custom_tool_call_inputs", {}).get(key)
        if buffered_input is not None and "input" not in raw_item:
            pending["input"] = buffered_input
    pending_items[key] = pending
    return key


def drop_pending_tool_call_item(
    state: dict[str, Any], event: Any, *, raw_item: dict[str, Any]
) -> None:
    normalized_type = str(raw_item.get("type") or "").strip()
    if normalized_type not in PARTIAL_TOOL_CALL_ITEM_TYPES:
        return
    key = resolve_pending_tool_call_key(state, event, raw_item=raw_item, item_type=normalized_type)
    if not key:
        return
    pending_items = state.get("pending_tool_call_items")
    if isinstance(pending_items, dict):
        pending_items.pop(key, None)
    for mapping_name in (
        "pending_tool_call_keys_by_output_index",
        "pending_tool_call_keys_by_provider_id",
    ):
        mapping = state.get(mapping_name)
        if not isinstance(mapping, dict):
            continue
        for mapping_key, mapping_value in list(mapping.items()):
            if str(mapping_value or "").strip() == key:
                mapping.pop(mapping_key, None)
    argument_buffers = state.get("pending_function_call_arguments")
    if isinstance(argument_buffers, dict):
        argument_buffers.pop(key, None)
    custom_inputs = state.get("pending_custom_tool_call_inputs")
    if isinstance(custom_inputs, dict):
        custom_inputs.pop(key, None)
    ready_keys = state.get("pending_tool_call_ready_keys")
    if isinstance(ready_keys, set):
        ready_keys.discard(key)


def response_function_call_arguments_delta(event: Any, *, state: dict[str, Any]) -> bool:
    delta = str(getattr(event, "delta", "") or "")
    if not delta:
        return True
    item_id = str(getattr(event, "item_id", "") or "").strip()
    key = resolve_pending_tool_call_key(
        state,
        event,
        item_id=item_id,
        item_type="function_call",
    )
    if not key:
        return True
    buffers = state.setdefault("pending_function_call_arguments", {})
    buffers[key] = str(buffers.get(key) or "") + delta
    remember_pending_tool_call_item(
        state,
        event,
        raw_item={
            "type": "function_call",
            "arguments": buffers[key],
            "status": "in_progress",
        },
        item_id=item_id,
        item_type="function_call",
    )
    return True


def response_function_call_arguments_done(event: Any, *, state: dict[str, Any]) -> bool:
    item_id = str(getattr(event, "item_id", "") or "").strip()
    arguments = str(getattr(event, "arguments", "") or "")
    name = str(getattr(event, "name", "") or "").strip()
    key = resolve_pending_tool_call_key(
        state,
        event,
        item_id=item_id,
        item_type="function_call",
    )
    if not key:
        return True
    state.setdefault("pending_function_call_arguments", {})[key] = arguments
    remember_pending_tool_call_item(
        state,
        event,
        raw_item={
            "type": "function_call",
            "arguments": arguments,
            "name": name,
            "status": "in_progress",
        },
        item_id=item_id,
        item_type="function_call",
    )
    state.setdefault("pending_tool_call_ready_keys", set()).add(key)
    return True


def response_custom_tool_call_input_delta(event: Any, *, state: dict[str, Any]) -> bool:
    delta = str(getattr(event, "delta", "") or "")
    if not delta:
        return True
    item_id = str(getattr(event, "item_id", "") or "").strip()
    key = resolve_pending_tool_call_key(
        state,
        event,
        item_id=item_id,
        item_type="custom_tool_call",
    )
    if not key:
        return True
    buffers = state.setdefault("pending_custom_tool_call_inputs", {})
    buffers[key] = str(buffers.get(key) or "") + delta
    remember_pending_tool_call_item(
        state,
        event,
        raw_item={
            "type": "custom_tool_call",
            "input": buffers[key],
            "status": "in_progress",
        },
        item_id=item_id,
        item_type="custom_tool_call",
    )
    return True


def response_custom_tool_call_input_done(event: Any, *, state: dict[str, Any]) -> bool:
    item_id = str(getattr(event, "item_id", "") or "").strip()
    tool_input = str(getattr(event, "input", "") or "")
    key = resolve_pending_tool_call_key(
        state,
        event,
        item_id=item_id,
        item_type="custom_tool_call",
    )
    if not key:
        return True
    state.setdefault("pending_custom_tool_call_inputs", {})[key] = tool_input
    remember_pending_tool_call_item(
        state,
        event,
        raw_item={
            "type": "custom_tool_call",
            "input": tool_input,
            "status": "in_progress",
        },
        item_id=item_id,
        item_type="custom_tool_call",
    )
    state.setdefault("pending_tool_call_ready_keys", set()).add(key)
    return True


__all__ = [
    "PARTIAL_TOOL_CALL_ITEM_TYPES",
    "drop_pending_tool_call_item",
    "remember_pending_tool_call_item",
    "resolve_pending_tool_call_key",
    "response_custom_tool_call_input_delta",
    "response_custom_tool_call_input_done",
    "response_function_call_arguments_delta",
    "response_function_call_arguments_done",
]

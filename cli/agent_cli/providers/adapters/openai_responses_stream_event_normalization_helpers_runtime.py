from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.providers.adapters.openai_responses_output import (
    _stream_item_to_dict,
    _summarize_output_item,
)
from cli.agent_cli.providers.adapters.openai_responses_stream import (
    emit_live_message_update,
    emit_live_reasoning_update,
    log_buffer_progress,
)
from cli.agent_cli.providers.adapters.openai_responses_stream_event_pure_helpers_runtime import (
    PARTIAL_TOOL_CALL_ITEM_TYPES,
    message_buffer_key,
    pending_tool_call_key,
    reasoning_buffer_key,
)


def ensure_buffer_item_id(
    state: dict[str, Any],
    *,
    buffer_key: str,
    item_ids_state_key: str,
) -> str:
    item_ids = state.setdefault(item_ids_state_key, {})
    remembered = str(item_ids.get(buffer_key) or "").strip()
    if remembered:
        return remembered
    item_id = f"stream_item_{state['next_message_index']}"
    state["next_message_index"] += 1
    item_ids[buffer_key] = item_id
    return item_id


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
    if normalized_type in {"function_call", "custom_tool_call"} and not str(pending.get("status") or "").strip():
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


def drop_pending_tool_call_item(state: dict[str, Any], event: Any, *, raw_item: dict[str, Any]) -> None:
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


def response_output_item_added(
    event: Any,
    *,
    state: dict[str, Any],
    timeline_debug_enabled_fn: Callable[[], bool],
    log_timeline_fn: Callable[..., None],
) -> bool:
    raw_item = _stream_item_to_dict(getattr(event, "item", None))
    if not raw_item:
        return True
    if timeline_debug_enabled_fn():
        log_timeline_fn(
            "responses.stream.output_item.added",
            item=_summarize_output_item(raw_item),
        )
        log_timeline_fn(
            "responses.stream.output_item.added_raw",
            item=raw_item,
        )
    raw_type = str(raw_item.get("type") or "").strip()
    if raw_type in {"message", "output_message"}:
        buffer_key = message_buffer_key(event)
        raw_id = str(raw_item.get("id") or "").strip()
        if raw_id:
            state["message_item_ids"][buffer_key] = raw_id
            state["message_provider_item_ids"][buffer_key] = raw_id
        phase = str(raw_item.get("phase") or "").strip().lower()
        if phase:
            state["message_item_phases"][buffer_key] = phase
    elif raw_type == "reasoning":
        buffer_key = reasoning_buffer_key(event)
        raw_id = str(raw_item.get("id") or "").strip()
        if raw_id:
            state["reasoning_item_ids"][buffer_key] = raw_id
    elif raw_type in PARTIAL_TOOL_CALL_ITEM_TYPES:
        remember_pending_tool_call_item(
            state,
            event,
            raw_item=raw_item,
            item_type=raw_type,
        )
    return True


def response_output_text_event(
    event: Any,
    *,
    state: dict[str, Any],
    turn_event_callback: Callable[[dict[str, Any]], None],
) -> bool:
    delta = str(getattr(event, "delta", "") or "")
    if not delta:
        return True
    state["output_text_parts"].append(delta)
    buffer_key = message_buffer_key(event)
    ensure_buffer_item_id(
        state,
        buffer_key=buffer_key,
        item_ids_state_key="message_item_ids",
    )
    state["message_buffers"][buffer_key] = state["message_buffers"].get(buffer_key, "") + delta
    log_buffer_progress(
        buffer_key=buffer_key,
        text_buffers=state["message_buffers"],
        item_ids=state["message_item_ids"],
        item_type="agent_message",
    )
    emit_live_message_update(
        buffer_key=buffer_key,
        message_buffers=state["message_buffers"],
        message_item_ids=state["message_item_ids"],
        message_item_phases=state["message_item_phases"],
        last_emitted_message_texts=state["last_emitted_message_texts"],
        turn_event_callback=turn_event_callback,
    )
    return True


def response_output_text_done(
    event: Any,
    *,
    state: dict[str, Any],
    turn_event_callback: Callable[[dict[str, Any]], None],
) -> bool:
    buffer_key = message_buffer_key(event)
    ensure_buffer_item_id(
        state,
        buffer_key=buffer_key,
        item_ids_state_key="message_item_ids",
    )
    if not str(state["message_buffers"].get(buffer_key) or "").strip():
        state["message_buffers"][buffer_key] = str(getattr(event, "text", "") or getattr(event, "refusal", "") or "")
    log_buffer_progress(
        buffer_key=buffer_key,
        text_buffers=state["message_buffers"],
        item_ids=state["message_item_ids"],
        item_type="agent_message",
    )
    emit_live_message_update(
        buffer_key=buffer_key,
        message_buffers=state["message_buffers"],
        message_item_ids=state["message_item_ids"],
        message_item_phases=state["message_item_phases"],
        last_emitted_message_texts=state["last_emitted_message_texts"],
        turn_event_callback=turn_event_callback,
    )
    return True


def response_reasoning_summary_delta(
    event: Any,
    *,
    state: dict[str, Any],
    turn_event_callback: Callable[[dict[str, Any]], None],
) -> bool:
    delta = str(getattr(event, "delta", "") or "")
    if not delta:
        return True
    buffer_key = reasoning_buffer_key(event)
    ensure_buffer_item_id(
        state,
        buffer_key=buffer_key,
        item_ids_state_key="reasoning_item_ids",
    )
    state["reasoning_buffers"][buffer_key] = state["reasoning_buffers"].get(buffer_key, "") + delta
    log_buffer_progress(
        buffer_key=buffer_key,
        text_buffers=state["reasoning_buffers"],
        item_ids=state["reasoning_item_ids"],
        item_type="reasoning",
    )
    emit_live_reasoning_update(
        buffer_key=buffer_key,
        reasoning_buffers=state["reasoning_buffers"],
        reasoning_item_ids=state["reasoning_item_ids"],
        last_emitted_reasoning_texts=state["last_emitted_reasoning_texts"],
        turn_event_callback=turn_event_callback,
    )
    return True


def response_reasoning_summary_done(
    event: Any,
    *,
    state: dict[str, Any],
    turn_event_callback: Callable[[dict[str, Any]], None],
) -> bool:
    buffer_key = reasoning_buffer_key(event)
    ensure_buffer_item_id(
        state,
        buffer_key=buffer_key,
        item_ids_state_key="reasoning_item_ids",
    )
    if not str(state["reasoning_buffers"].get(buffer_key) or "").strip():
        state["reasoning_buffers"][buffer_key] = str(getattr(event, "text", "") or "")
    log_buffer_progress(
        buffer_key=buffer_key,
        text_buffers=state["reasoning_buffers"],
        item_ids=state["reasoning_item_ids"],
        item_type="reasoning",
    )
    emit_live_reasoning_update(
        buffer_key=buffer_key,
        reasoning_buffers=state["reasoning_buffers"],
        reasoning_item_ids=state["reasoning_item_ids"],
        last_emitted_reasoning_texts=state["last_emitted_reasoning_texts"],
        turn_event_callback=turn_event_callback,
    )
    return True


__all__ = [
    "PARTIAL_TOOL_CALL_ITEM_TYPES",
    "drop_pending_tool_call_item",
    "ensure_buffer_item_id",
    "remember_pending_tool_call_item",
    "resolve_pending_tool_call_key",
    "response_custom_tool_call_input_delta",
    "response_custom_tool_call_input_done",
    "response_function_call_arguments_delta",
    "response_function_call_arguments_done",
    "response_output_item_added",
    "response_output_text_done",
    "response_output_text_event",
    "response_reasoning_summary_delta",
    "response_reasoning_summary_done",
]

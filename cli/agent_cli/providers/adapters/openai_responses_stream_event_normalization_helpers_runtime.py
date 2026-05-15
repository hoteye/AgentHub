from __future__ import annotations

from collections.abc import Callable
from typing import Any

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
    message_buffer_key,
    reasoning_buffer_key,
)
from cli.agent_cli.providers.adapters.openai_responses_stream_tool_call_normalization_runtime import (
    PARTIAL_TOOL_CALL_ITEM_TYPES,
    drop_pending_tool_call_item,
    remember_pending_tool_call_item,
    resolve_pending_tool_call_key,
    response_custom_tool_call_input_delta,
    response_custom_tool_call_input_done,
    response_function_call_arguments_delta,
    response_function_call_arguments_done,
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
        state["message_buffers"][buffer_key] = str(
            getattr(event, "text", "") or getattr(event, "refusal", "") or ""
        )
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

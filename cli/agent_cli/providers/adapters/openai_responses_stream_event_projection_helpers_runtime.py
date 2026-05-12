from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.models import ResponseInputItem, response_item_text
from cli.agent_cli.providers.adapters.openai_responses_output import (
    _provider_tool_call_from_payload,
    _response_output_payload_to_followup_item,
    _response_output_payload_to_response_input_item,
    _stream_item_to_dict,
    _summarize_output_item,
)
from cli.agent_cli.providers.adapters.openai_responses_stream import (
    flush_message_buffer,
    flush_reasoning_buffer,
)
from cli.agent_cli.providers.adapters.openai_responses_stream_event_normalization_helpers_runtime import (
    drop_pending_tool_call_item,
)
from cli.agent_cli.providers.adapters.openai_responses_stream_event_pure_helpers_runtime import (
    PARTIAL_TOOL_CALL_ITEM_TYPES,
    message_buffer_key,
    resolved_output_item_id,
)


def response_output_item_done(
    event: Any,
    *,
    state: dict[str, Any],
    response_item_turn_event_fn: Callable[[ResponseInputItem, str], dict[str, Any] | None],
    turn_event_callback: Callable[[dict[str, Any]], None],
    timeline_debug_enabled_fn: Callable[[], bool],
    log_timeline_fn: Callable[..., None],
) -> bool:
    raw_item = _stream_item_to_dict(getattr(event, "item", None))
    if not raw_item:
        return True
    if timeline_debug_enabled_fn():
        log_timeline_fn(
            "responses.stream.output_item.done",
            item=_summarize_output_item(raw_item),
        )
        log_timeline_fn(
            "responses.stream.output_item.raw",
            item=raw_item,
        )
    raw_type = str(raw_item.get("type") or "").strip()
    drop_pending_tool_call_item(state, event, raw_item=raw_item)
    if raw_type in PARTIAL_TOOL_CALL_ITEM_TYPES:
        flush_pending_buffers(state=state, turn_event_callback=turn_event_callback)
        provider_call = _provider_tool_call_from_payload(raw_item)
        if provider_call is not None:
            if timeline_debug_enabled_fn():
                log_timeline_fn(
                    "responses.stream.function_call.done",
                    call_id=provider_call.call_id,
                    tool_name=provider_call.name,
                    provider_item_type=provider_call.item_type,
                    arguments=provider_call.arguments,
                )
            state["tool_calls"].append(provider_call)
            state["followup_items"].append(dict(raw_item))
        return True
    response_item = _response_output_payload_to_response_input_item(raw_item)
    if response_item is not None:
        state["response_items"].append(response_item)
    normalized_followup = _response_output_payload_to_followup_item(raw_item)
    if normalized_followup is not None:
        state["followup_items"].append(normalized_followup)
    if raw_type in {"message", "output_message"}:
        flush_reasoning_only(state=state, turn_event_callback=turn_event_callback)
    buffered_item_id = ""
    if raw_type in {"message", "output_message"}:
        buffered_item_id = str(state["message_item_ids"].get(message_buffer_key(event)) or "").strip()
    item_id = resolved_output_item_id(
        raw_item,
        response_item_count=len(state["response_items"]),
        buffered_item_id=buffered_item_id,
    )
    turn_event = response_item_turn_event_fn(response_item, item_id) if response_item is not None else None
    if turn_event is not None:
        emit_completed_turn_event(
            raw_type=raw_type,
            item_id=item_id,
            response_item=response_item,
            turn_event=turn_event,
            state=state,
            turn_event_callback=turn_event_callback,
            timeline_debug_enabled_fn=timeline_debug_enabled_fn,
            log_timeline_fn=log_timeline_fn,
        )
    return True


def response_completed(
    *,
    event: Any,
    state: dict[str, Any],
    turn_event_callback: Callable[[dict[str, Any]], None],
    timeline_debug_enabled_fn: Callable[[], bool],
    log_timeline_fn: Callable[..., None],
    summarize_response_output_fn: Callable[[Any], Any],
    json_ready_fn: Callable[[Any], Any],
) -> Any:
    flush_pending_buffers(state=state, turn_event_callback=turn_event_callback)
    response = getattr(event, "response", None)
    if timeline_debug_enabled_fn():
        log_timeline_fn(
            "responses.stream.completed",
            response_id=str(getattr(response, "id", "") or "").strip() or None,
            output_items=summarize_response_output_fn(response) if response is not None else [],
        )
        log_timeline_fn(
            "responses.stream.completed_raw",
            response=json_ready_fn(response),
        )
    return response


def flush_pending_buffers(*, state: dict[str, Any], turn_event_callback: Callable[[dict[str, Any]], None]) -> None:
    flush_reasoning_only(state=state, turn_event_callback=turn_event_callback)
    for buffer_key in sorted(state["message_item_ids"]):
        flush_message_buffer(
            buffer_key=buffer_key,
            message_buffers=state["message_buffers"],
            message_item_ids=state["message_item_ids"],
            message_item_phases=state["message_item_phases"],
            emitted_message_ids=state["emitted_message_ids"],
            turn_event_callback=turn_event_callback,
        )


def flush_reasoning_only(*, state: dict[str, Any], turn_event_callback: Callable[[dict[str, Any]], None]) -> None:
    for buffer_key in sorted(state["reasoning_item_ids"]):
        flush_reasoning_buffer(
            buffer_key=buffer_key,
            reasoning_buffers=state["reasoning_buffers"],
            reasoning_item_ids=state["reasoning_item_ids"],
            emitted_reasoning_ids=state["emitted_reasoning_ids"],
            emitted_reasoning_texts=state["emitted_reasoning_texts"],
            turn_event_callback=turn_event_callback,
        )


def emit_completed_turn_event(
    *,
    raw_type: str,
    item_id: str,
    response_item: ResponseInputItem,
    turn_event: dict[str, Any],
    state: dict[str, Any],
    turn_event_callback: Callable[[dict[str, Any]], None],
    timeline_debug_enabled_fn: Callable[[], bool],
    log_timeline_fn: Callable[..., None],
) -> None:
    completed_text = response_item_text(response_item).strip()
    if raw_type == "reasoning" and completed_text:
        for buffer_key, buffered_text in list(state["reasoning_buffers"].items()):
            if str(buffered_text or "") != completed_text:
                continue
            buffered_item_id = str(state["reasoning_item_ids"].get(buffer_key) or "").strip()
            if buffered_item_id:
                state["emitted_reasoning_ids"].add(buffered_item_id)
        if completed_text in state["emitted_reasoning_texts"]:
            return
    if timeline_debug_enabled_fn():
        item = turn_event.get("item") if isinstance(turn_event, dict) else None
        log_timeline_fn(
            "responses.stream.turn_event.emit",
            event_type=turn_event.get("type") if isinstance(turn_event, dict) else None,
            item_type=item.get("type") if isinstance(item, dict) else None,
            item_id=item.get("id") if isinstance(item, dict) else None,
        )
    turn_event_callback(turn_event)
    state["emitted_message_ids"].add(str(item_id))
    if raw_type == "reasoning" and completed_text:
        state["emitted_reasoning_texts"].add(completed_text)
    for buffer_key, buffered_item_id in list(state["message_item_ids"].items()):
        buffered_text = str(state["message_buffers"].get(buffer_key) or "")
        if buffered_item_id == str(item_id) or (completed_text and buffered_text == completed_text):
            state["emitted_message_ids"].add(buffered_item_id)
            state["message_buffers"][buffer_key] = completed_text
            state["last_emitted_message_texts"][buffer_key] = completed_text


__all__ = [
    "emit_completed_turn_event",
    "flush_pending_buffers",
    "flush_reasoning_only",
    "response_completed",
    "response_output_item_done",
]

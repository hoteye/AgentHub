from __future__ import annotations

from typing import Any, Callable, Dict

from cli.agent_cli.debug_timeline import (
    _preview_text,
    log_timeline,
    timeline_debug_enabled,
)
from cli.agent_cli.providers.adapters import openai_responses_stream_buffer_runtime as stream_buffer_runtime


def stream_index_value(event: Any) -> int:
    return stream_buffer_runtime.stream_index_value(event)


def flush_message_buffer(
    *,
    buffer_key: str,
    message_buffers: Dict[str, str],
    message_item_ids: Dict[str, str],
    message_item_phases: Dict[str, str],
    emitted_message_ids: set[str],
    turn_event_callback: Callable[[Dict[str, Any]], None],
) -> bool:
    phase = str(message_item_phases.get(buffer_key) or "").strip().lower()
    return stream_buffer_runtime.flush_text_buffer(
        buffer_key=buffer_key,
        buffers=message_buffers,
        item_ids=message_item_ids,
        emitted_ids=emitted_message_ids,
        turn_event_callback=turn_event_callback,
        item_type="agent_message",
        item_extra={"phase": phase} if phase else None,
        timeline_debug_enabled_fn=timeline_debug_enabled,
        log_timeline_fn=log_timeline,
        preview_text_fn=_preview_text,
    )


def emit_live_message_update(
    *,
    buffer_key: str,
    message_buffers: Dict[str, str],
    message_item_ids: Dict[str, str],
    message_item_phases: Dict[str, str],
    last_emitted_message_texts: Dict[str, str],
    turn_event_callback: Callable[[Dict[str, Any]], None],
) -> bool:
    phase = str(message_item_phases.get(buffer_key) or "").strip().lower()
    return stream_buffer_runtime.emit_live_buffer_update(
        buffer_key=buffer_key,
        buffers=message_buffers,
        item_ids=message_item_ids,
        last_emitted_texts=last_emitted_message_texts,
        turn_event_callback=turn_event_callback,
        item_type="agent_message",
        item_extra={"phase": phase} if phase else None,
    )


def log_buffer_progress(
    *,
    buffer_key: str,
    text_buffers: Dict[str, str],
    item_ids: Dict[str, str],
    item_type: str,
) -> None:
    stream_buffer_runtime.log_buffer_progress(
        buffer_key=buffer_key,
        text_buffers=text_buffers,
        item_ids=item_ids,
        item_type=item_type,
        timeline_debug_enabled_fn=timeline_debug_enabled,
        log_timeline_fn=log_timeline,
        preview_text_fn=_preview_text,
    )


def flush_reasoning_buffer(
    *,
    buffer_key: str,
    reasoning_buffers: Dict[str, str],
    reasoning_item_ids: Dict[str, str],
    emitted_reasoning_ids: set[str],
    emitted_reasoning_texts: set[str],
    turn_event_callback: Callable[[Dict[str, Any]], None],
) -> bool:
    return stream_buffer_runtime.flush_text_buffer(
        buffer_key=buffer_key,
        buffers=reasoning_buffers,
        item_ids=reasoning_item_ids,
        emitted_ids=emitted_reasoning_ids,
        emitted_texts=emitted_reasoning_texts,
        turn_event_callback=turn_event_callback,
        item_type="reasoning",
        timeline_debug_enabled_fn=timeline_debug_enabled,
        log_timeline_fn=log_timeline,
        preview_text_fn=_preview_text,
    )


def emit_live_reasoning_update(
    *,
    buffer_key: str,
    reasoning_buffers: Dict[str, str],
    reasoning_item_ids: Dict[str, str],
    last_emitted_reasoning_texts: Dict[str, str],
    turn_event_callback: Callable[[Dict[str, Any]], None],
) -> bool:
    return stream_buffer_runtime.emit_live_buffer_update(
        buffer_key=buffer_key,
        buffers=reasoning_buffers,
        item_ids=reasoning_item_ids,
        last_emitted_texts=last_emitted_reasoning_texts,
        turn_event_callback=turn_event_callback,
        item_type="reasoning",
    )

from __future__ import annotations

from typing import Any, Callable, Dict


def stream_event_field(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def stream_index_value(event: Any) -> int:
    for key in ("output_index", "item_index", "summary_index", "content_index"):
        value = stream_event_field(event, key)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def log_buffer_progress(
    *,
    buffer_key: str,
    text_buffers: Dict[str, str],
    item_ids: Dict[str, str],
    item_type: str,
    timeline_debug_enabled_fn: Callable[[], bool],
    log_timeline_fn: Callable[..., Any],
    preview_text_fn: Callable[..., str],
) -> None:
    if not timeline_debug_enabled_fn():
        return
    item_id = item_ids.get(buffer_key)
    text = str(text_buffers.get(buffer_key) or "").strip()
    if not item_id or not text:
        return
    log_timeline_fn(
        "responses.stream.buffer.update",
        item_type=item_type,
        buffer_key=buffer_key,
        item_id=item_id,
        text_preview=preview_text_fn(text, max_chars=160),
        text_len=len(text),
    )


def emit_live_buffer_update(
    *,
    buffer_key: str,
    buffers: Dict[str, str],
    item_ids: Dict[str, str],
    last_emitted_texts: Dict[str, str],
    turn_event_callback: Callable[[Dict[str, Any]], None],
    item_type: str,
    item_extra: Dict[str, Any] | None = None,
) -> bool:
    item_id = str(item_ids.get(buffer_key) or "").strip()
    raw_text = str(buffers.get(buffer_key) or "")
    if not item_id or not raw_text.strip():
        return False
    if last_emitted_texts.get(buffer_key) == raw_text:
        return False
    item_payload: Dict[str, Any] = {
        "id": item_id,
        "type": item_type,
        "text": raw_text,
    }
    if item_extra:
        item_payload.update({key: value for key, value in item_extra.items() if value not in (None, "")})
    turn_event_callback({"type": "item.updated", "item": item_payload})
    last_emitted_texts[buffer_key] = raw_text
    return True


def flush_text_buffer(
    *,
    buffer_key: str,
    buffers: Dict[str, str],
    item_ids: Dict[str, str],
    emitted_ids: set[str],
    turn_event_callback: Callable[[Dict[str, Any]], None],
    item_type: str,
    item_extra: Dict[str, Any] | None = None,
    emitted_texts: set[str] | None = None,
    timeline_debug_enabled_fn: Callable[[], bool],
    log_timeline_fn: Callable[..., Any],
    preview_text_fn: Callable[..., str],
) -> bool:
    item_id = item_ids.get(buffer_key)
    raw_text = str(buffers.get(buffer_key) or "")
    if not item_id or not raw_text.strip() or item_id in emitted_ids:
        return False
    text = raw_text
    if timeline_debug_enabled_fn():
        log_timeline_fn(
            "responses.stream.buffer.flush",
            item_type=item_type,
            buffer_key=buffer_key,
            item_id=item_id,
            text_preview=preview_text_fn(text, max_chars=160),
            text_len=len(text),
        )
    item_payload: Dict[str, Any] = {
        "id": item_id,
        "type": item_type,
        "text": text,
    }
    if item_extra:
        item_payload.update({key: value for key, value in item_extra.items() if value not in (None, "")})
    turn_event_callback({"type": "item.completed", "item": item_payload})
    emitted_ids.add(item_id)
    if emitted_texts is not None:
        emitted_texts.add(text)
    return True

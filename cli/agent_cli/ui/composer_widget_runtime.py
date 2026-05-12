from __future__ import annotations

from typing import Any, Callable


def should_insert_native_paste_text_directly(text: str) -> bool:
    value = str(text or "")
    if not value:
        return False
    if any(token in value for token in ("\n", "\r", "\t")):
        return False
    if len(value) > 8:
        return False
    if not any(ord(character) >= 128 for character in value):
        return False
    # IME commits for short Unicode text can arrive as Paste events in terminals.
    # Keep path-like or attachment-like payloads on the paste pipeline.
    if any(token in value for token in ("/", "\\", "@")):
        return False
    return True


def sync_composer(composer: Any) -> None:
    composer.refresh(repaint=True, layout=False)
    try:
        composer.app.on_prompt_composer_changed()
    except Exception:
        pass


def handle_key_event(
    composer: Any,
    event: Any,
    *,
    is_paste_suppression_active_fn: Callable[[], bool],
    should_buffer_printable_char_fn: Callable[[str], bool],
    flush_paste_burst_fn: Callable[[], bool],
    handle_ascii_input_fn: Callable[[str], None],
    handle_submission_action_key_fn: Callable[[Any], bool],
) -> bool:
    if event.is_printable and event.character:
        if is_paste_suppression_active_fn():
            event.stop()
            event.prevent_default()
            handle_ascii_input_fn(event.character)
            return True
        if should_buffer_printable_char_fn(event.character):
            event.stop()
            event.prevent_default()
            handle_ascii_input_fn(event.character)
            return True
        flush_paste_burst_fn()
    else:
        flush_paste_burst_fn()
    return handle_submission_action_key_fn(event)


def handle_paste_event(
    composer: Any,
    event: Any,
    *,
    clear_paste_burst_state_fn: Callable[[], None],
    should_suppress_paste_fn: Callable[[str], bool],
    insert_text_fn: Callable[[str], None],
) -> None:
    if hasattr(event, "stop"):
        event.stop()
    if hasattr(event, "prevent_default"):
        event.prevent_default()
    clear_paste_burst_state_fn()
    text = str(getattr(event, "text", "") or "")
    if should_suppress_paste_fn(text):
        return
    if not text:
        return
    if should_insert_native_paste_text_directly(text):
        insert_text_fn(text)
        return
    try:
        composer.app.handle_paste_burst(text)
    except Exception:
        insert_text_fn(text)


def visible_line_count(
    composer: Any,
    width: int,
    *,
    display_text_and_cursor_fn: Callable[[str, int], tuple[str, int]],
    visual_lines_fn: Callable[[str, int, int], list[str]],
) -> int:
    display_text, display_cursor_pos = display_text_and_cursor_fn(composer._text, composer._cursor_pos)
    lines = len(
        visual_lines_fn(
            display_text,
            display_cursor_pos,
            max(1, width),
        )
    )
    return max(1, min(composer.MAX_VISIBLE_LINES, lines))


def render_width(composer: Any) -> int:
    return max(
        1,
        getattr(getattr(composer, "content_region", None), "width", 0)
        or getattr(getattr(composer, "region", None), "width", 0)
        or composer.size.width,
    )

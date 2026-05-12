from __future__ import annotations

from time import monotonic
from typing import Any


def should_buffer_printable_char(character: str) -> bool:
    return len(character) == 1 and ord(character) < 128


def handle_ascii_input(composer: Any, character: str) -> None:
    if (
        character == "?"
        and not composer._text
        and not composer._paste_burst_buffer
        and not composer._pending_ascii_char
    ):
        toggle_overlay = getattr(
            getattr(composer, "app", None),
            "toggle_shortcut_overlay_from_question_mark",
            None,
        )
        if callable(toggle_overlay):
            try:
                if bool(toggle_overlay()):
                    return
            except Exception:
                pass
    now = monotonic()
    if composer._paste_burst_buffer:
        if (now - composer._paste_burst_last_at) <= composer.PASTE_BURST_GAP_SECONDS:
            composer._paste_burst_buffer += character
            composer._paste_burst_last_at = now
            return
        flush_burst_buffer_as_paste(composer)
    if composer._pending_ascii_char:
        if (now - composer._pending_ascii_at) <= composer.PASTE_BURST_GAP_SECONDS:
            composer._paste_burst_buffer = composer._pending_ascii_char + character
            composer._pending_ascii_char = ""
            composer._pending_ascii_at = 0.0
            composer._paste_burst_last_at = now
            return
        flush_pending_ascii_as_typed(composer)
    composer._pending_ascii_char = character
    composer._pending_ascii_at = now


def flush_paste_burst_if_due(composer: Any) -> None:
    if not composer._paste_burst_buffer and not composer._pending_ascii_char:
        return
    now = monotonic()
    if composer._paste_burst_buffer:
        if (now - composer._paste_burst_last_at) < composer.PASTE_BURST_FLUSH_SECONDS:
            return
        flush_burst_buffer_as_paste(composer)
        return
    if (now - composer._pending_ascii_at) < composer.PASTE_BURST_FLUSH_SECONDS:
        return
    flush_pending_ascii_as_typed(composer)


def flush_paste_burst(composer: Any) -> bool:
    if composer._paste_burst_buffer:
        flush_burst_buffer_as_paste(composer)
        return True
    if composer._pending_ascii_char:
        flush_pending_ascii_as_typed(composer)
        return True
    return False


def flush_burst_buffer_as_paste(composer: Any) -> None:
    buffered = composer._paste_burst_buffer
    composer._paste_burst_buffer = ""
    composer._paste_burst_last_at = 0.0
    if buffered and should_suppress_paste(composer, buffered):
        return
    try:
        composer.app.handle_paste_burst(buffered)
    except Exception:
        composer.insert_text(buffered)


def flush_pending_ascii_as_typed(composer: Any) -> None:
    character = composer._pending_ascii_char
    composer._pending_ascii_char = ""
    composer._pending_ascii_at = 0.0
    if character:
        if should_suppress_paste(composer, character):
            return
        composer.insert_text(character)


def clear_paste_burst_state(composer: Any) -> None:
    composer._pending_ascii_char = ""
    composer._pending_ascii_at = 0.0
    composer._paste_burst_buffer = ""
    composer._paste_burst_last_at = 0.0


def is_paste_suppression_active(composer: Any) -> bool:
    return monotonic() <= composer._suppress_paste_until


def arm_paste_suppression(composer: Any, text: str | None = None) -> None:
    composer._suppress_paste_until = monotonic() + composer.RIGHT_CLICK_PASTE_SUPPRESS_SECONDS
    composer._suppress_paste_text = text


def should_suppress_paste(composer: Any, text: str) -> bool:
    now = monotonic()
    if now > composer._suppress_paste_until:
        composer._suppress_paste_until = 0.0
        composer._suppress_paste_text = None
        return False
    expected = composer._suppress_paste_text
    if expected is not None and text != expected:
        return False
    composer._suppress_paste_until = 0.0
    composer._suppress_paste_text = None
    return True

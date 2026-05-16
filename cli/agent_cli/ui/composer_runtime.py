from __future__ import annotations

from collections.abc import Callable
from typing import Any

_RAW_TERMINAL_KEY_ALIASES = {
    "\x1b[H": "home",
    "\x1bOH": "home",
    "\x1b[1~": "home",
    "\x1b[7~": "home",
    "\x1b[F": "end",
    "\x1bOF": "end",
    "\x1b[4~": "end",
    "\x1b[8~": "end",
    "\x1b[1;2H": "shift+home",
    "\x1b[7$": "shift+home",
    "\x1b[1;2F": "shift+end",
    "\x1b[8$": "shift+end",
    "\x01": "home",
    "\x04": "end",
}


def _consume_event(event: Any) -> None:
    event.stop()
    event.prevent_default()


def normalized_key(key: Any) -> str:
    value = str(key or "")
    return _RAW_TERMINAL_KEY_ALIASES.get(value, value)


def normalized_key_aliases(event: Any) -> set[str]:
    aliases: set[str] = set()
    for item in (getattr(event, "key", ""), *(getattr(event, "aliases", []) or [])):
        value = str(item or "")
        if not value:
            continue
        aliases.add(value)
        aliases.add(normalized_key(value))
    return aliases


def has_pending_alt_enter_escape_fallback(composer: Any) -> bool:
    return int(getattr(composer, "_pending_alt_enter_escape_active_token", 0) or 0) > 0


def should_arm_alt_enter_escape_fallback(composer: Any) -> bool:
    app = getattr(composer, "app", None)
    if app is None:
        return True
    if str(getattr(app, "_screen_mode", "prompt") or "prompt") != "prompt":
        return False
    if bool(getattr(app, "_shortcut_overlay_active", False)):
        return False
    if getattr(app, "_request_user_input_pending", None) is not None:
        return False
    has_active_completion_popup = getattr(app, "has_active_completion_popup", None)
    if callable(has_active_completion_popup):
        try:
            if bool(has_active_completion_popup()):
                return False
        except Exception:
            return False
    has_interruptible_run = getattr(app, "_has_interruptible_run", None)
    if callable(has_interruptible_run):
        try:
            if bool(has_interruptible_run()):
                return False
        except Exception:
            return False
    return True


def flush_alt_enter_escape_fallback(composer: Any, *, token: int | None = None) -> bool:
    active_token = int(getattr(composer, "_pending_alt_enter_escape_active_token", 0) or 0)
    if active_token <= 0:
        return False
    if token is not None and token != active_token:
        return False
    composer._pending_alt_enter_escape_active_token = 0
    handle_escape_key = getattr(getattr(composer, "app", None), "handle_escape_key", None)
    if not callable(handle_escape_key):
        return False
    try:
        return bool(handle_escape_key())
    except Exception:
        return False


def arm_alt_enter_escape_fallback(composer: Any) -> None:
    token = int(getattr(composer, "_pending_alt_enter_escape_token", 0) or 0) + 1
    composer._pending_alt_enter_escape_token = token
    composer._pending_alt_enter_escape_active_token = token
    set_timer = getattr(composer, "set_timer", None)
    if not callable(set_timer):
        return
    delay = float(getattr(composer, "ALT_ENTER_ESCAPE_FALLBACK_SECONDS", 0.08) or 0.08)
    try:
        set_timer(
            delay,
            lambda token=token: flush_alt_enter_escape_fallback(composer, token=token),
        )
    except Exception:
        return


def consume_alt_enter_escape_fallback(composer: Any) -> bool:
    if not has_pending_alt_enter_escape_fallback(composer):
        return False
    composer._pending_alt_enter_escape_active_token = 0
    return True


def handle_alt_enter_escape_fallback(*, composer: Any, event: Any) -> bool:
    key = normalized_key(getattr(event, "key", ""))
    if key in {"enter", "ctrl+m"} and consume_alt_enter_escape_fallback(composer):
        _consume_event(event)
        composer.insert_text("\n")
        return True
    if key == "escape":
        if not should_arm_alt_enter_escape_fallback(composer):
            return False
        _consume_event(event)
        arm_alt_enter_escape_fallback(composer)
        return True
    if has_pending_alt_enter_escape_fallback(composer):
        flush_alt_enter_escape_fallback(composer)
    return False


def handle_key_event(
    *,
    composer: Any,
    event: Any,
    prehandled: bool,
    app_ctrl_c_fn: Callable[[], None],
) -> bool:
    if prehandled:
        return True

    key = normalized_key(getattr(event, "key", ""))
    key_aliases = normalized_key_aliases(event)
    if key_aliases & {"ctrl+j", "shift+enter", "alt+enter", "meta+enter"}:
        _consume_event(event)
        composer.insert_text("\n")
        return True
    if key == "ctrl+c":
        if composer.copy_selection_to_clipboard():
            _consume_event(event)
            return True
        _consume_event(event)
        app_ctrl_c_fn()
        return True
    if key == "ctrl+x":
        if composer.cut_selection_to_clipboard():
            _consume_event(event)
            return True
    if key == "ctrl+shift+z":
        _consume_event(event)
        composer.redo()
        return True
    if key == "ctrl+y":
        _consume_event(event)
        composer.yank_kill_buffer()
        return True
    if key == "ctrl+z":
        _consume_event(event)
        composer.undo()
        return True
    if key == "ctrl+a":
        _consume_event(event)
        composer.select_all()
        return True
    if key in {"left", "ctrl+b"}:
        _consume_event(event)
        composer.move_cursor_left()
        return True
    if key in {"ctrl+left", "alt+left", "alt+b"}:
        _consume_event(event)
        composer.move_cursor_word_left()
        return True
    if key in {"right", "ctrl+f"}:
        _consume_event(event)
        composer.move_cursor_right()
        return True
    if key in {"ctrl+right", "alt+right", "alt+f"}:
        _consume_event(event)
        composer.move_cursor_word_right()
        return True
    if key in {"ctrl+home", "ctrl+shift+home"}:
        _consume_event(event)
        composer.move_cursor_home(extend=key == "ctrl+shift+home")
        return True
    if key in {"ctrl+end", "ctrl+shift+end"}:
        _consume_event(event)
        composer.move_cursor_end(extend=key == "ctrl+shift+end")
        return True
    if key == "shift+left":
        _consume_event(event)
        composer.move_cursor_left(extend=True)
        return True
    if key == "shift+right":
        _consume_event(event)
        composer.move_cursor_right(extend=True)
        return True
    if key == "ctrl+shift+left":
        _consume_event(event)
        composer.move_cursor_word_left(extend=True)
        return True
    if key == "ctrl+shift+right":
        _consume_event(event)
        composer.move_cursor_word_right(extend=True)
        return True
    if key == "up":
        _consume_event(event)
        composer.move_cursor_up()
        return True
    if key == "shift+up":
        _consume_event(event)
        composer.move_cursor_up(extend=True)
        return True
    if key == "down":
        _consume_event(event)
        composer.move_cursor_down()
        return True
    if key == "shift+down":
        _consume_event(event)
        composer.move_cursor_down(extend=True)
        return True
    if key == "home":
        _consume_event(event)
        composer.move_cursor_home()
        return True
    if key == "shift+home":
        _consume_event(event)
        composer.move_cursor_home(extend=True)
        return True
    if key == "end":
        _consume_event(event)
        composer.move_cursor_end()
        return True
    if key == "ctrl+e":
        _consume_event(event)
        composer.move_cursor_logical_line_end(move_to_next_line_when_at_end=True)
        return True
    if key == "shift+end":
        _consume_event(event)
        composer.move_cursor_end(extend=True)
        return True
    if key in {"backspace", "ctrl+h"}:
        _consume_event(event)
        composer.backspace()
        return True
    if key in {"alt+backspace", "ctrl+backspace", "ctrl+w", "ctrl+alt+h"}:
        _consume_event(event)
        composer.delete_backward_word()
        return True
    if key in {"delete", "ctrl+d"}:
        _consume_event(event)
        composer.delete_forward()
        return True
    if key in {"alt+delete", "ctrl+delete", "alt+d"}:
        _consume_event(event)
        composer.delete_forward_word()
        return True
    if key == "ctrl+u":
        _consume_event(event)
        composer.kill_line_start()
        return True
    if key == "ctrl+k":
        _consume_event(event)
        composer.kill_line_end()
        return True
    if event.is_printable and event.character:
        _consume_event(event)
        composer.insert_text(event.character)
        return True
    return False

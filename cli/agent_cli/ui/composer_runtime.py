from __future__ import annotations

from typing import Any, Callable


def _consume_event(event: Any) -> None:
    event.stop()
    event.prevent_default()


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
    key = str(getattr(event, "key", "") or "")
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

    key = event.key
    key_aliases = {str(item or "") for item in [key, *(getattr(event, "aliases", []) or [])] if str(item or "")}
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
    if key in {"ctrl+y", "ctrl+shift+z"}:
        _consume_event(event)
        composer.redo()
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
    if key in {"ctrl+left", "alt+b"}:
        _consume_event(event)
        composer.move_cursor_word_left()
        return True
    if key in {"right", "ctrl+f"}:
        _consume_event(event)
        composer.move_cursor_right()
        return True
    if key in {"ctrl+right", "alt+f"}:
        _consume_event(event)
        composer.move_cursor_word_right()
        return True
    if key == "shift+left":
        _consume_event(event)
        composer.move_cursor_left(extend=True)
        return True
    if key == "shift+right":
        _consume_event(event)
        composer.move_cursor_right(extend=True)
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
    if key in {"end", "ctrl+e"}:
        _consume_event(event)
        composer.move_cursor_end()
        return True
    if key == "shift+end":
        _consume_event(event)
        composer.move_cursor_end(extend=True)
        return True
    if key == "backspace":
        _consume_event(event)
        composer.backspace()
        return True
    if key in {"delete", "ctrl+d"}:
        _consume_event(event)
        composer.delete_forward()
        return True
    if key == "ctrl+u":
        _consume_event(event)
        composer.clear_text()
        return True
    if event.is_printable and event.character:
        _consume_event(event)
        composer.insert_text(event.character)
        return True
    return False

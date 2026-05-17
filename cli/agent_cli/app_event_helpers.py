from __future__ import annotations

from typing import Any

from textual.css.query import NoMatches

from cli.agent_cli.app_event_mouse_runtime import (
    on_mouse_down as on_mouse_down,
)
from cli.agent_cli.app_event_mouse_runtime import (
    on_mouse_move as on_mouse_move,
)
from cli.agent_cli.app_event_mouse_runtime import (
    on_mouse_up as on_mouse_up,
)
from cli.agent_cli.app_event_mouse_runtime import (
    record_idle_mouse_position as record_idle_mouse_position,
)
from cli.agent_cli.app_event_startup_runtime import (
    _present_startup_setup_overlay as _present_startup_setup_overlay,
)
from cli.agent_cli.app_event_startup_runtime import (
    _start_tab_workers as _start_tab_workers,
)
from cli.agent_cli.app_event_startup_runtime import (
    _startup_provider_status as _startup_provider_status,
)
from cli.agent_cli.app_event_startup_runtime import (
    _startup_setup_notice as _startup_setup_notice,
)
from cli.agent_cli.app_event_startup_runtime import (
    _startup_setup_payload as _startup_setup_payload,
)
from cli.agent_cli.app_event_startup_runtime import (
    _startup_setup_required as _startup_setup_required,
)
from cli.agent_cli.app_event_startup_runtime import (
    _startup_update_notice as _startup_update_notice,
)
from cli.agent_cli.app_event_startup_runtime import (
    on_mount as _startup_on_mount,
)
from cli.agent_cli.debug_timeline import log_timeline, timeline_debug_enabled
from cli.agent_cli.startup_debug import startup_log
from cli.agent_cli.ui.transcript_navigation_runtime import (
    latest_expandable_entry_id,
    toggle_entry_expansion,
)


def on_mount(app: Any) -> None:
    _startup_on_mount(app)


def on_key(app: Any, event: Any) -> None:
    if app._screen_mode == "transcript":
        if app._handle_transcript_search_key(event.key):
            event.stop()
            event.prevent_default()
            return
        character = str(getattr(event, "character", "") or "")
        if character and app._handle_transcript_search_text_input(character):
            event.stop()
            event.prevent_default()
            return
        if event.key == "escape":
            event.stop()
            event.prevent_default()
            app.action_toggle_transcript()
            return
        if event.key == "q":
            event.stop()
            event.prevent_default()
            app.action_toggle_transcript()
            return
        if app._handle_transcript_navigation_key(event.key):
            event.stop()
            event.prevent_default()
            return
    if event.key == "ctrl+c":
        event.stop()
        event.prevent_default()
        app.action_ctrl_c()
        return
    if event.key == "escape" and app.handle_escape_key():
        event.stop()
        event.prevent_default()
        return
    _route_prompt_key_to_composer(app, event)


def _route_prompt_key_to_composer(app: Any, event: Any) -> bool:
    if str(getattr(app, "_screen_mode", "prompt") or "prompt") != "prompt":
        return False
    if _has_active_keyboard_overlay(app):
        return False
    try:
        from cli.agent_cli.ui.composer import PromptComposer

        composer = app.query_one("#prompt_composer", PromptComposer)
    except Exception:
        return False
    focused = getattr(app, "focused", None)
    widget = focused
    while widget is not None:
        if widget is composer:
            return False
        widget = getattr(widget, "parent", None)
    if not _is_prompt_composer_key_candidate(event):
        return False
    try:
        composer.focus()
        composer.on_key(event)
    except Exception:
        return False
    return True


def _has_active_keyboard_overlay(app: Any) -> bool:
    for attr_name in ("_request_user_input_overlay", "_approval_overlay", "_setup_overlay"):
        overlay = getattr(app, attr_name, None)
        if bool(getattr(overlay, "is_active", False)):
            return True
    return False


def _is_prompt_composer_key_candidate(event: Any) -> bool:
    if bool(getattr(event, "is_printable", False)) and str(getattr(event, "character", "") or ""):
        return True
    from cli.agent_cli.ui.composer_runtime import normalized_key_aliases

    aliases = normalized_key_aliases(event)
    return bool(
        aliases
        & {
            "alt+b",
            "alt+backspace",
            "alt+d",
            "alt+delete",
            "alt+enter",
            "alt+f",
            "alt+left",
            "alt+right",
            "backspace",
            "ctrl+a",
            "ctrl+alt+h",
            "ctrl+b",
            "ctrl+backspace",
            "ctrl+d",
            "ctrl+delete",
            "ctrl+e",
            "ctrl+f",
            "ctrl+h",
            "ctrl+j",
            "ctrl+k",
            "ctrl+left",
            "ctrl+m",
            "ctrl+n",
            "ctrl+p",
            "ctrl+right",
            "ctrl+shift+z",
            "ctrl+shift+end",
            "ctrl+shift+home",
            "ctrl+shift+left",
            "ctrl+shift+right",
            "ctrl+end",
            "ctrl+home",
            "ctrl+u",
            "ctrl+v",
            "ctrl+w",
            "ctrl+x",
            "ctrl+y",
            "ctrl+z",
            "delete",
            "down",
            "end",
            "enter",
            "home",
            "left",
            "meta+enter",
            "right",
            "shift+down",
            "shift+end",
            "shift+enter",
            "shift+home",
            "shift+left",
            "shift+right",
            "shift+up",
            "tab",
            "up",
        }
    )


def action_ctrl_c(app: Any) -> None:
    startup_log(
        "app.action_ctrl_c "
        f"busy={app._busy} "
        f"interruptible={app._has_interruptible_run()} "
        f"has_prompt={bool(app._current_prompt_text())} "
        f"quit_armed={app._quit_shortcut_active()}"
    )
    if app._quit_shortcut_active():
        app._quit_shortcut_expires_at = None
        app._populate_exit_request_from_runtime()
        app._begin_shutdown()
        app.exit()
        return
    if app._has_interruptible_run():
        app._arm_quit_shortcut()
        app.action_interrupt_run()
        return
    app._flush_prompt_composer_burst()
    if app._current_prompt_text():
        app._clear_prompt_text()
        app._refresh_prompt_composer()
        app._focus_input()
    app._arm_quit_shortcut()


def action_interrupt_run(app: Any) -> None:
    if timeline_debug_enabled():
        log_timeline(
            "ui.interrupt.requested",
            busy=app._busy,
            focus_id=getattr(getattr(app, "focused", None), "id", None),
            queue_size=app._request_queue.qsize(),
            queued_run_labels=list(app._queued_run_labels),
        )
    optimistic_interrupt = app._has_interruptible_run()
    if optimistic_interrupt:
        app._mark_live_turn_interrupt_requested()
    result = app.runtime.interrupt_active_run()
    if timeline_debug_enabled():
        log_timeline(
            "ui.interrupt.result",
            busy=app._busy,
            result=dict(result or {}),
        )
    if result.get("ok"):
        if optimistic_interrupt:
            app._render_live_interrupt_notice()
        if app._busy:
            app._set_busy(False)
    elif optimistic_interrupt and not app._runtime_has_active_run():
        app._live_turn_interrupt_requested = False
    app._focus_input()


def handle_escape_key(app: Any) -> bool:
    if app._screen_mode == "transcript":
        app.action_toggle_transcript()
        if timeline_debug_enabled():
            log_timeline("ui.escape.handled", branch="exit_transcript", busy=app._busy)
        return True
    if bool(getattr(app, "_shortcut_overlay_active", False)):
        app._clear_shortcut_overlay()
        if timeline_debug_enabled():
            log_timeline("ui.escape.handled", branch="shortcut_overlay", busy=app._busy)
        return True
    cancel_approval_overlay = getattr(app, "_cancel_approval_overlay_on_escape", None)
    if callable(cancel_approval_overlay) and cancel_approval_overlay():
        if timeline_debug_enabled():
            log_timeline("ui.escape.handled", branch="approval_overlay_cancel", busy=app._busy)
        return True
    if app._cancel_request_user_input_on_escape():
        if timeline_debug_enabled():
            log_timeline("ui.escape.handled", branch="request_user_input_cancel", busy=app._busy)
        return True
    if app.dismiss_slash_popup():
        if timeline_debug_enabled():
            log_timeline("ui.escape.handled", branch="dismiss_popup", busy=app._busy)
        return True
    if app.handle_escape_interrupt():
        if timeline_debug_enabled():
            log_timeline("ui.escape.handled", branch="interrupt", busy=app._busy)
        return True
    if timeline_debug_enabled():
        log_timeline("ui.escape.handled", branch="ignored", busy=app._busy)
    return False


def on_prompt_composer_changed(app: Any) -> None:
    current_text = app._current_prompt_text()
    if current_text and bool(getattr(app, "_shortcut_overlay_active", False)):
        app._shortcut_overlay_active = False
    if (
        app._suppressed_slash_popup_text is not None
        and current_text != app._suppressed_slash_popup_text
    ):
        app._suppressed_slash_popup_text = None
    app._retain_pending_pastes_for_text(current_text)
    app._sync_prompt_history_navigation()
    app._update_completion_popup()
    app._refresh_prompt_composer()
    try:
        app._update_bottom_dock(max(1, app.size.width))
    except NoMatches:
        return


def action_toggle_latest_web_item(app: Any) -> None:
    entry_id = latest_expandable_entry_id(app._transcript_entries)
    if entry_id is None:
        return
    updated_entries, toggled = toggle_entry_expansion(app._transcript_entries, entry_id)
    if toggled:
        app._transcript_entries = updated_entries
        try:
            app._sync_transcript()
        except NoMatches:
            pass
        finally:
            app._focus_input()

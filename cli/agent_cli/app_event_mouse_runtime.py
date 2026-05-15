from __future__ import annotations

from time import monotonic
from typing import Any

from textual.css.query import NoMatches


def on_mouse_down(app: Any, event: Any) -> None:
    button = getattr(event, "button", None)
    if button == 3:
        if _copy_active_selection_to_clipboard(app):
            try:
                app._arm_prompt_paste_suppression()
            except Exception:
                pass
            if hasattr(event, "stop"):
                event.stop()
            if hasattr(event, "prevent_default"):
                event.prevent_default()
            return
        if app.paste_prompt_from_clipboard(
            report_empty=False,
            suppress_following_native_paste=True,
        ):
            if hasattr(event, "stop"):
                event.stop()
            if hasattr(event, "prevent_default"):
                event.prevent_default()
        return
    if button != 1:
        return
    if _switch_tab_from_rail_screen_position(app, event):
        event.stop()
        event.prevent_default()
        return


def on_mouse_up(app: Any, event: Any) -> None:
    record_idle_mouse_position(app, event)
    if event.button not in {1, 3}:
        return
    if event.button == 1 and _handle_split_toggle_click(app, event):
        event.stop()
        event.prevent_default()
        return
    if event.button == 1 and _switch_tab_from_rail_screen_position(app, event):
        event.stop()
        event.prevent_default()
        return
    if app._event_targets_prompt_composer(event):
        return
    if app._event_targets_active_overlay(event):
        return
    app.call_after_refresh(app._focus_input)


def on_mouse_move(app: Any, event: Any) -> None:
    record_idle_mouse_position(app, event)


def _handle_split_toggle_click(app: Any, event: Any) -> bool:
    from textual.widgets import Static

    try:
        btn = app.query_one("#split_toggle_btn", Static)
    except Exception:
        return False
    region = getattr(btn, "region", None)
    if region is None:
        return False
    screen_x = getattr(event, "screen_x", None)
    screen_y = getattr(event, "screen_y", None)
    if screen_x is None or screen_y is None:
        return False
    try:
        x = int(screen_x) - int(region.x)
        y = int(screen_y) - int(region.y)
        width = int(region.width)
        height = int(region.height)
    except Exception:
        return False
    if x < 0 or y < 0 or x >= width or y >= height:
        return False
    app._handle_preview_control_request("toggle")
    app._refresh_split_toggle_button()
    return True


def _switch_tab_from_rail_screen_position(app: Any, event: Any) -> bool:
    try:
        from cli.agent_cli.ui.tab_bar import TabBar
    except Exception:
        return False
    try:
        tab_bar = app.query_one("#tab_bar", TabBar)
    except Exception:
        return False
    if getattr(tab_bar, "orientation", "") != "vertical":
        return False
    screen_x = getattr(event, "screen_x", None)
    screen_y = getattr(event, "screen_y", None)
    if screen_x is None or screen_y is None:
        return False
    region = getattr(tab_bar, "region", None)
    if region is None:
        return False
    try:
        x = int(screen_x) - int(region.x)
        y = int(screen_y) - int(region.y)
        width = int(region.width)
        height = int(region.height)
    except Exception:
        return False
    if x < 0 or y < 0 or x >= width or y >= height:
        return False
    spans = list(getattr(tab_bar, "_tab_spans", []) or [])
    if not spans:
        try:
            tab_bar.render()
        except Exception:
            return False
        spans = list(getattr(tab_bar, "_tab_spans", []) or [])
    for tab_id, start_y, end_y in spans:
        if start_y <= y < end_y:
            mgr = getattr(app, "_tab_manager", None)
            if mgr is None or tab_id == getattr(mgr, "active_tab_id", None):
                return True
            if mgr.switch_to_tab(tab_id):
                app._refresh_top_title_bar()
                app._focus_input()
            return True
    return False


def _copy_active_selection_to_clipboard(app: Any) -> bool:
    if _copy_transcript_selection_to_clipboard(app):
        return True
    return _copy_composer_selection_to_clipboard(app)


def _copy_transcript_selection_to_clipboard(app: Any) -> bool:
    try:
        from textual.document._document import Selection

        from cli.agent_cli.ui.widgets import TranscriptArea

        transcript = app.query_one("#main_log", TranscriptArea)
        selected_text = str(getattr(transcript, "selected_text", "") or "").strip()
        if not selected_text:
            return False
        transcript.app.copy_to_clipboard(selected_text)
        transcript.selection = Selection.cursor(transcript.selection.end)
        transcript._last_right_click_copied_text = selected_text
        return True
    except Exception:
        return False


def _copy_composer_selection_to_clipboard(app: Any) -> bool:
    try:
        from cli.agent_cli.ui.composer import PromptComposer

        composer = app.query_one("#prompt_composer", PromptComposer)
    except Exception:
        return False
    if not bool(getattr(composer, "has_selection", False)):
        return False
    try:
        copied = bool(composer.copy_selection_to_clipboard())
        if copied:
            composer.clear_selection()
        return copied
    except Exception:
        return False


def record_idle_mouse_position(app: Any, event: Any) -> None:
    if not app._presentation.idle_cat_enabled:
        return
    if app._idle_status_started_at is None:
        return
    current_time = monotonic()
    if current_time - app._idle_status_started_at < app.IDLE_STATUS_DELAY_SECONDS:
        return
    mouse_x = getattr(event, "screen_x", None)
    if mouse_x is None:
        mouse_x = getattr(event, "x", None)
    if mouse_x is None:
        return
    interaction_triggered = app._idle_cat_animator.observe_mouse(
        x=int(mouse_x),
        width=max(1, int(app.size.width)),
        now=current_time,
    )
    if not interaction_triggered:
        return
    try:
        app._update_bottom_dock(max(1, app.size.width))
    except NoMatches:
        return

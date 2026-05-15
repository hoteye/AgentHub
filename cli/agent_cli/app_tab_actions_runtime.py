from __future__ import annotations

from typing import Any

from textual.css.query import NoMatches
from textual.widgets import Static

from cli.agent_cli.app_tab_actions_live_state_runtime import (
    capture_tab_live_turn_state,
    restore_tab_live_turn_state,
    run_with_tab_transcript_state,
)
from cli.agent_cli.ui.tab_bar import TabBar, TabInfo


def refresh_top_title_bar(app: Any) -> None:
    title_text = str(app._top_title_text or app._top_title_base)
    try:
        top_title_icon = app.query_one("#top_title_icon", Static)
        top_title_icon.update(app._top_title_leading_symbol)
        top_title_bar = app.query_one("#top_title_bar", Static)
        content_width = max(1, int(getattr(top_title_bar.size, "width", 0) or 0))
        if content_width <= 1:
            content_width = max(1, int(app.size.width) - 4)
        top_title_bar.update(app._crop_one_line(title_text, content_width))
    except NoMatches:
        pass
    try:
        tab_bar = app.query_one("#tab_bar", TabBar)
    except NoMatches:
        app._refresh_transcript_task_hint()
        return
    tab_bar.set_leading_symbol(app._top_title_leading_symbol)
    tab_bar.set_rail_palette(
        theme_bg=app._theme.info_surface_bg,
        text=app._theme.text_secondary,
        text_dim=app._theme.text_dim,
    )
    if app._tab_manager is not None:
        session = app._tab_manager.active_session
        session.top_title_text = title_text
        session.is_busy = app._busy
        tabs_info = []
        for tid, label, busy in app._tab_manager.tab_labels():
            tab_session = app._tab_manager.get(tid)
            tabs_info.append(
                TabInfo(
                    tab_id=tid,
                    label=app._crop_one_line(label, max(1, int(app.size.width) - 6)),
                    is_active=(tid == app._tab_manager.active_tab_id),
                    is_busy=busy,
                    has_pending_approval=bool(
                        tab_session
                        and (
                            getattr(tab_session, "pending_approvals", None)
                            or getattr(tab_session, "pending_request_user_input", None)
                        )
                    ),
                    has_unread_output=bool(
                        tab_session and getattr(tab_session, "has_unread_output", False)
                    ),
                    is_dirty=bool(tab_session and getattr(tab_session, "transcript_dirty", False)),
                )
            )
        tab_bar.update_tabs(tabs_info)
    else:
        tab_bar.update_tabs(
            [
                TabInfo(
                    tab_id="main",
                    label=app._crop_one_line(title_text, max(1, int(app.size.width) - 6)),
                    is_active=True,
                    is_busy=app._busy,
                ),
            ]
        )
    app._refresh_split_toggle_button()
    app._refresh_transcript_task_hint()


def action_new_tab(app: Any) -> None:
    if app._tab_manager is None:
        return
    from cli.agent_cli.runtime_kernels.codex_sidecar import codex_sidecar_artifact_available
    from cli.agent_cli.runtime_kernels.routing import select_new_tab_engine

    engine = select_new_tab_engine(
        app.runtime,
        artifact_available_fn=lambda: getattr(app, "_codex_sidecar_kernel", None) is not None
        or codex_sidecar_artifact_available(),
    )
    tab_id = app._tab_manager.create_tab(engine=engine)
    if not tab_id:
        app._write_system_notice(f"Failed to create tab (engine={engine})")
        return
    app._focus_input()
    app._refresh_top_title_bar()


def action_fork_tab(app: Any) -> None:
    if app._tab_manager is None:
        return
    active = app._tab_manager.active_tab_id
    tab_id = app._tab_manager.fork_tab(active)
    if not tab_id:
        return
    app._focus_input()
    app._refresh_top_title_bar()


def action_close_tab(app: Any) -> None:
    if app._tab_manager is None:
        return
    active = app._tab_manager.active_tab_id
    result = app._tab_manager.close_tab(active)
    if result is None:
        return
    app._refresh_top_title_bar()
    app._focus_input()


def adjacent_tab_id(order: list[str], current: str, *, offset: int) -> str | None:
    if len(order) <= 1:
        return None
    try:
        idx = order.index(current)
    except ValueError:
        return None
    return order[(idx + offset) % len(order)]


def switch_to_adjacent_tab(app: Any, *, offset: int) -> None:
    if app._tab_manager is None:
        return
    target = adjacent_tab_id(
        app._tab_manager._tab_order,
        app._tab_manager.active_tab_id,
        offset=offset,
    )
    if target is not None and app._tab_manager.switch_to_tab(target):
        app._refresh_top_title_bar()
        app._focus_input()


def action_next_tab(app: Any) -> None:
    switch_to_adjacent_tab(app, offset=1)


def action_prev_tab(app: Any) -> None:
    switch_to_adjacent_tab(app, offset=-1)


def dismiss_request_user_input_overlay_for_inactive_tab(app: Any) -> None:
    overlay = getattr(app, "_request_user_input_overlay", None)
    if overlay is not None and getattr(overlay, "is_active", False):
        deactivate = getattr(overlay, "deactivate", None)
        if callable(deactivate):
            deactivate()


def restore_pending_interactions_for_tab(app: Any, tab_id: str) -> None:
    mgr = app._tab_manager
    if mgr is None or tab_id != mgr.active_tab_id:
        return
    session = mgr.get(tab_id)
    if session is None:
        return
    pending_request = getattr(session, "pending_request_user_input", None)
    if pending_request is not None:
        with app._request_user_input_pending_lock:
            app._request_user_input_pending = pending_request
        app._dispatch_request_user_input_prompt(pending_request)
    else:
        with app._request_user_input_pending_lock:
            current = app._request_user_input_pending
            current_tab = str(getattr(current, "tab_id", "") or "").strip()
            if current is not None and current_tab != tab_id:
                app._request_user_input_pending = None
                app._set_request_user_input_waiting(False)
                app._dismiss_request_user_input_overlay_for_inactive_tab()
    pending_approvals = [
        str(item or "").strip()
        for item in list(getattr(session, "pending_approvals", []) or [])
        if str(item or "").strip()
    ]
    if pending_approvals:
        app._approval_overlay_queue = list(pending_approvals)
        app.status_data["pending_approvals"] = str(len(pending_approvals))
        app.status_data["latest_pending_approval_id"] = pending_approvals[0]
    else:
        app._approval_overlay_queue = []
        app._dismiss_approval_overlay()
        app.status_data["pending_approvals"] = "0"
        app.status_data["latest_pending_approval_id"] = "-"
    app._sync_pending_approval_surface_state()


def set_busy_for_tab(app: Any, tab_id: str, busy: bool) -> None:
    mgr = app._tab_manager
    if mgr is None:
        return
    session = mgr.get(tab_id)
    if session is None:
        return
    session.is_busy = busy
    if tab_id == mgr.active_tab_id:
        app._set_busy(busy)
    else:
        app._refresh_top_title_bar()


def mark_tab_transcript_updated(app: Any, tab_id: str, *, unread: bool) -> None:
    mgr = app._tab_manager
    if mgr is None:
        return
    session = mgr.get(tab_id)
    if session is None:
        return
    session.transcript_dirty = True
    if unread:
        session.has_unread_output = True
    app._refresh_top_title_bar()


def on_request_start_for_tab(app: Any, tab_id: str, text: str) -> None:
    mgr = app._tab_manager
    if mgr is None or tab_id != mgr.active_tab_id:
        return
    app._on_runtime_request_start(text)


def begin_activity_capture_for_tab(app: Any, tab_id: str) -> None:
    mgr = app._tab_manager
    if mgr is None or tab_id != mgr.active_tab_id:
        return
    app._begin_activity_capture()


def render_response_for_tab(app: Any, tab_id: str, response: object) -> None:
    mgr = app._tab_manager
    if mgr is None:
        return
    if tab_id == mgr.active_tab_id:
        app._render_response(response)
    else:
        session = mgr.get(tab_id)
        if session is None:
            return
        app._run_with_tab_transcript_state(session, lambda: app._render_response(response))
        app._mark_tab_transcript_updated(tab_id, unread=True)


def handle_response_for_tab(app: Any, tab_id: str, response: object) -> None:
    mgr = app._tab_manager
    if mgr is None or tab_id != mgr.active_tab_id:
        return
    app._handle_runtime_response(response)


def write_reply_for_tab(app: Any, tab_id: str, text: str) -> None:
    mgr = app._tab_manager
    if mgr is None:
        return
    if tab_id == mgr.active_tab_id:
        app._write_assistant_reply(text)
    else:
        session = mgr.get(tab_id)
        if session is None:
            return
        app._run_with_tab_transcript_state(session, lambda: app._write_assistant_reply(text))
        app._mark_tab_transcript_updated(tab_id, unread=True)


def on_tab_activity(app: Any, tab_id: str, event: object) -> None:
    mgr = app._tab_manager
    if mgr is None:
        return
    if tab_id == mgr.active_tab_id:
        app._on_runtime_activity(event)
    else:
        app._note_pending_approval_activity(event, tab_id=tab_id)
        code = str(getattr(event, "code", "") or "").strip().lower()
        if code.startswith("approval."):
            return
        session = mgr.get(tab_id)
        if session is not None:
            app._run_with_tab_transcript_state(
                session, lambda: app._write_live_activity_event(event)
            )
        app._mark_tab_transcript_updated(tab_id, unread=False)


def on_tab_turn_event(app: Any, tab_id: str, event: object) -> None:
    mgr = app._tab_manager
    if mgr is None:
        return
    if tab_id == mgr.active_tab_id:
        app._on_runtime_turn_event(event)
    else:
        session = mgr.get(tab_id)
        if session is not None and isinstance(event, dict):
            app._run_with_tab_transcript_state(session, lambda: app._write_live_turn_event(event))
        app._mark_tab_transcript_updated(tab_id, unread=False)


def echo_prompt_for_tab(
    app: Any,
    tab_id: str,
    text: str,
    attachments: list | None = None,
) -> None:
    mgr = app._tab_manager
    if mgr is None or tab_id != mgr.active_tab_id:
        return
    app._write_user_prompt(text, attachments=list(attachments or []))


def on_idle_for_tab(app: Any, tab_id: str) -> None:
    mgr = app._tab_manager
    if mgr is None or tab_id != mgr.active_tab_id:
        return
    app._focus_input()


__all__ = [
    "action_close_tab",
    "action_fork_tab",
    "action_new_tab",
    "action_next_tab",
    "action_prev_tab",
    "adjacent_tab_id",
    "begin_activity_capture_for_tab",
    "capture_tab_live_turn_state",
    "dismiss_request_user_input_overlay_for_inactive_tab",
    "echo_prompt_for_tab",
    "handle_response_for_tab",
    "mark_tab_transcript_updated",
    "on_idle_for_tab",
    "on_request_start_for_tab",
    "on_tab_activity",
    "on_tab_turn_event",
    "refresh_top_title_bar",
    "render_response_for_tab",
    "restore_pending_interactions_for_tab",
    "restore_tab_live_turn_state",
    "run_with_tab_transcript_state",
    "set_busy_for_tab",
    "switch_to_adjacent_tab",
    "write_reply_for_tab",
]

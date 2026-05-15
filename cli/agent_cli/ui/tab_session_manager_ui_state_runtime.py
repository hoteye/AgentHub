from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cli.agent_cli.ui.tab_session_manager_models import TabSession

_Collaborators = Mapping[str, Any]
_TAB_DISPLAY_ALPHABET = "123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _base_tab_label(manager: Any, session: TabSession) -> str:
    del manager
    return session.custom_label or session.thread_name or session.top_title_text or session.tab_id


def _decorated_tab_label(manager: Any, session: TabSession) -> str:
    label = manager._base_tab_label(session)
    role = str(getattr(session, "role", "standalone") or "standalone").strip()
    if role == "master":
        return f"[M] {label}"
    if role == "child":
        return f"[C] {label}"
    return label


def tab_labels(manager: Any) -> list[tuple[str, str, bool]]:
    return [
        (s.tab_id, manager._decorated_tab_label(s), s.is_busy)
        for s in (manager._tabs[tid] for tid in manager._tab_order)
    ]


def display_tab_label(manager: Any, tab_id: str) -> str:
    normalized = str(tab_id or "").strip()
    if not normalized:
        return ""
    try:
        index = manager._tab_order.index(normalized)
    except ValueError:
        return "?"
    return (
        _TAB_DISPLAY_ALPHABET[index] if 0 <= index < len(_TAB_DISPLAY_ALPHABET) else str(index + 1)
    )


def _save_current_state(manager: Any) -> None:
    session = manager._tabs.get(manager._active_tab_id)
    if session is None:
        return
    app = manager._app
    session.is_busy = getattr(app, "_busy", False)
    session.top_title_text = str(getattr(app, "_top_title_text", "AgentHub"))
    session.status_data = dict(getattr(app, "status_data", {}) or {})
    session.transcript_entries = list(getattr(app, "_transcript_entries", []))
    session.transcript_lines = list(getattr(app, "_transcript_lines", []))
    scroll_x, scroll_y = manager._current_transcript_scroll_offset()
    if scroll_x > 0 or scroll_y > 0:
        session.transcript_scroll_x = scroll_x
        session.transcript_scroll_y = scroll_y
    try:
        from cli.agent_cli.ui import PromptComposer

        composer = app.query_one("#prompt_composer", PromptComposer)
        session.prompt_text = composer.text
        session.prompt_cursor_position = int(getattr(composer, "cursor_pos", 0) or 0)
    except Exception:
        pass


def _restore_tab_state(
    manager: Any,
    tab_id: str,
    *,
    collaborators: _Collaborators,
) -> None:
    restore_runtime_transcript_snapshot = collaborators["_restore_runtime_transcript_snapshot"]
    merge_status_preserving_known_values = collaborators["_merge_status_preserving_known_values"]
    provider_status_for_runtime = collaborators["_provider_status_for_runtime"]

    session = manager._tabs.get(tab_id)
    if session is None:
        return
    if bool(getattr(session, "runtime_restore_pending", False)):
        manager._schedule_runtime_restore_poll(tab_id)
    if session.transcript_restore_pending:
        try:
            entries, lines = restore_runtime_transcript_snapshot(manager._app, session.runtime)
            session.transcript_entries = entries
            session.transcript_lines = lines
        except Exception:
            pass
        else:
            session.transcript_restore_pending = False
    app = manager._app
    app._busy = session.is_busy
    app._top_title_text = session.top_title_text
    session.status_data = merge_status_preserving_known_values(
        session.status_data,
        provider_status_for_runtime(session.runtime),
    )
    app._transcript_entries = list(session.transcript_entries)
    app._transcript_lines = list(session.transcript_lines)
    screen_mode = str(getattr(app, "_screen_mode", "prompt") or "prompt").strip().lower()
    if screen_mode == "transcript":
        try:
            app._transcript_screen_snapshot_entries = app._snapshot_transcript_entries(
                app._transcript_entries
            )
        except Exception:
            app._transcript_screen_snapshot_entries = list(app._transcript_entries)
    else:
        app._transcript_screen_snapshot_entries = None
    try:
        from cli.agent_cli.ui import PromptComposer

        composer = app.query_one("#prompt_composer", PromptComposer)
        composer.set_text(session.prompt_text)
        set_cursor = getattr(composer, "_set_cursor_position", None)
        if callable(set_cursor):
            set_cursor(session.prompt_cursor_position, extend=False)
            composer.refresh(repaint=True, layout=False)
    except Exception:
        pass
    try:
        from cli.agent_cli.ui import TranscriptArea, TranscriptVirtualList

        if screen_mode == "transcript":
            app._sync_transcript()
            log = app.query_one("#transcript_log", TranscriptVirtualList)
        else:
            log = app.query_one("#main_log", TranscriptArea)
            log.load_transcript(app._transcript_lines)
            app._sync_transcript()
        manager._restore_transcript_scroll(log, session)
    except Exception:
        pass
    session.transcript_dirty = False
    session.has_unread_output = False
    restore_pending = getattr(app, "_restore_pending_interactions_for_tab", None)
    if callable(restore_pending):
        try:
            restore_pending(tab_id)
        except Exception:
            pass
    update_fn = getattr(app, "_update_status", None)
    if callable(update_fn):
        try:
            update_fn({})
        except Exception:
            pass


def _rebuild_fork_transcript_from_runtime(
    manager: Any,
    tab_id: str,
    *,
    collaborators: _Collaborators,
) -> None:
    from cli.agent_cli.ui.transcript_history import system_notice_entry
    from cli.agent_cli.ui.transcript_visual_rendering import render_transcript_entries

    fork_runtime_transcript_source_items = collaborators["_fork_runtime_transcript_source_items"]
    history_item_to_transcript_entry = collaborators["_history_item_to_transcript_entry"]
    running_fork_notice = collaborators["RUNNING_FORK_NOTICE"]

    app = manager._app
    session = manager._tabs.get(tab_id)
    if session is None:
        return
    app._transcript_entries = []
    app._transcript_lines = []
    try:
        app._restore_transcript_from_runtime_history()
    except Exception:
        pass
    if not app._transcript_lines and session.runtime is not None:
        entries = []
        for item in fork_runtime_transcript_source_items(session.runtime):
            entry = history_item_to_transcript_entry(item)
            if entry is not None:
                entries.append(entry)
        if entries:
            app._transcript_entries = entries
            app._transcript_lines = render_transcript_entries(entries)
    notice = system_notice_entry(running_fork_notice)
    app._transcript_entries = [*list(app._transcript_entries), notice]
    app._transcript_lines = render_transcript_entries(app._transcript_entries)
    session.transcript_entries = list(app._transcript_entries)
    session.transcript_lines = list(app._transcript_lines)
    manager._restore_tab_state(tab_id)


def _current_transcript_scroll_offset(manager: Any) -> tuple[int, int]:
    app = manager._app
    screen_mode = str(getattr(app, "_screen_mode", "prompt") or "prompt").strip().lower()
    widget_id = "#transcript_log" if screen_mode == "transcript" else "#main_log"
    try:
        from cli.agent_cli.ui import TranscriptArea, TranscriptVirtualList

        widget_type = TranscriptVirtualList if screen_mode == "transcript" else TranscriptArea
        log = app.query_one(widget_id, widget_type)
    except Exception:
        return (0, 0)
    helper = getattr(log, "transcript_scroll_offset", None)
    if callable(helper):
        try:
            scroll_x, scroll_y = helper()
            return (max(0, int(scroll_x)), max(0, int(scroll_y)))
        except Exception:
            pass
    try:
        offset = log.scroll_offset
        return (max(0, int(offset.x)), max(0, int(offset.y)))
    except Exception:
        pass
    try:
        return (max(0, int(log.scroll_x)), max(0, int(log.scroll_y)))
    except Exception:
        return (0, 0)


def _restore_transcript_scroll(manager: Any, log: Any, session: TabSession) -> None:
    scroll_x = max(0, int(session.transcript_scroll_x or 0))
    scroll_y = max(0, int(session.transcript_scroll_y or 0))
    if scroll_y <= 0:
        return
    tab_id = session.tab_id

    def _restore_if_active(_log: Any = log, _sx: int = scroll_x, _sy: int = scroll_y) -> None:
        if manager._active_tab_id != tab_id:
            return
        manager._scroll_widget_to(_log, scroll_x=_sx, scroll_y=_sy)

    manager._scroll_widget_to(log, scroll_x=scroll_x, scroll_y=scroll_y)
    call_after_refresh = getattr(manager._app, "call_after_refresh", None)
    if callable(call_after_refresh):
        call_after_refresh(_restore_if_active)
    set_timer = getattr(manager._app, "set_timer", None)
    if callable(set_timer):
        set_timer(0.3, _restore_if_active)


def _scroll_widget_to(log: Any, *, scroll_x: int, scroll_y: int) -> None:
    helper = getattr(log, "restore_transcript_viewport", None)
    if callable(helper):
        try:
            helper(scroll_x=scroll_x, scroll_y=scroll_y)
            return
        except Exception:
            pass
    try:
        log.scroll_to(
            x=scroll_x,
            y=scroll_y,
            animate=False,
            immediate=True,
            force=True,
        )
    except Exception:
        return

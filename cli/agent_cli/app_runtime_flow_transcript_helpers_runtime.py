from __future__ import annotations

from typing import Any

from textual.css.query import NoMatches

from cli.agent_cli import app_runtime_flow_normalization_helpers_runtime as normalization_helpers_runtime
from cli.agent_cli import app_runtime_flow_projection_helpers_runtime as projection_helpers_runtime
from cli.agent_cli import app_runtime_flow_pure_helpers_runtime as pure_helpers_runtime
from cli.agent_cli.ui import TranscriptArea, TranscriptVirtualList
from cli.agent_cli.ui.transcript_browsing_runtime import (
    TranscriptBrowsingState,
    next_match,
    prev_match,
)


def activate_transcript_search_mode(app: Any) -> None:
    setattr(app, "_transcript_search_mode_active_flag", True)
    setattr(
        app,
        "_transcript_search_query_buffer_value",
        str(app._transcript_browsing_state.query or ""),
    )
    try:
        app._update_bottom_dock(max(1, app.size.width))
    except NoMatches:
        return


def deactivate_transcript_search_mode(app: Any) -> None:
    setattr(app, "_transcript_search_mode_active_flag", False)
    try:
        app._update_bottom_dock(max(1, app.size.width))
    except NoMatches:
        return


def apply_transcript_search_query(app: Any, query: str) -> None:
    transcript_entries = list(
        getattr(app, "_transcript_screen_snapshot_entries", None)
        or getattr(app, "_transcript_entries", [])
    )
    app._transcript_browsing_state = projection_helpers_runtime.build_transcript_search_state(
        transcript_entries=transcript_entries,
        query=query,
        current_state=app._transcript_browsing_state,
    )
    matches = app._transcript_browsing_state.match_entry_ids
    active_entry_id = app._transcript_browsing_state.active_match_entry_id
    try:
        transcript_log = app.query_one("#transcript_log", TranscriptVirtualList)
    except NoMatches:
        return
    transcript_log.set_highlighted_entry_ids(set(matches), active_entry_id)
    if active_entry_id:
        transcript_log.scroll_to_entry(active_entry_id, align="center")


def move_transcript_search_match(app: Any, *, forward: bool) -> bool:
    state = getattr(app, "_transcript_browsing_state", TranscriptBrowsingState())
    if not state.match_entry_ids:
        return False
    next_state = next_match(state) if forward else prev_match(state)
    app._transcript_browsing_state = next_state
    active_entry_id = next_state.active_match_entry_id
    try:
        transcript_log = app.query_one("#transcript_log", TranscriptVirtualList)
    except NoMatches:
        return False
    transcript_log.set_highlighted_entry_ids(set(next_state.match_entry_ids), active_entry_id)
    if active_entry_id:
        transcript_log.scroll_to_entry(active_entry_id, align="center")
    return True


def set_screen_mode(app: Any, screen_mode: str) -> None:
    next_mode = normalization_helpers_runtime.normalize_screen_mode(screen_mode)
    if next_mode == app._screen_mode:
        return
    if next_mode == "transcript":
        app._transcript_screen_snapshot_entries = app._snapshot_transcript_entries(app._transcript_entries)
    else:
        app._transcript_screen_snapshot_entries = None
    app._screen_mode = next_mode
    if next_mode == "transcript":
        try:
            app.dismiss_slash_popup()
        except Exception:
            pass
    app._apply_screen_state_to_widgets()
    try:
        app._sync_transcript()
        if next_mode != "transcript":
            try:
                app.query_one("#transcript_log", TranscriptVirtualList).clear_entries()
            except NoMatches:
                pass
        app._update_bottom_dock(max(1, app.size.width))
    except NoMatches:
        return
    if next_mode == "prompt":
        app._focus_input()


def handle_transcript_navigation_key(app: Any, key: str) -> bool:
    try:
        if app._screen_mode == "transcript":
            main_log = app.query_one("#transcript_log", TranscriptVirtualList)
        else:
            main_log = app.query_one("#main_log", TranscriptArea)
    except NoMatches:
        return False
    action_name = pure_helpers_runtime.transcript_navigation_action_name(key)
    if not action_name:
        return False
    action = getattr(main_log, action_name, None)
    if callable(action):
        action()
        return True
    return False


__all__ = [
    "activate_transcript_search_mode",
    "apply_transcript_search_query",
    "deactivate_transcript_search_mode",
    "handle_transcript_navigation_key",
    "move_transcript_search_match",
    "set_screen_mode",
]

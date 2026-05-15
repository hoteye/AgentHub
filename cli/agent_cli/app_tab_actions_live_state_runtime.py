from __future__ import annotations

from collections.abc import Callable
from typing import Any


def capture_tab_live_turn_state(app: Any) -> dict[str, object]:
    return {
        "active_transcript_turn_key": str(
            getattr(app, "_active_transcript_turn_key", "turn:0") or "turn:0"
        ),
        "active_runtime_request_is_slash": bool(
            getattr(app, "_active_runtime_request_is_slash", False)
        ),
        "active_runtime_request_text": str(getattr(app, "_active_runtime_request_text", "") or ""),
        "assistant_message_streaming_active": bool(
            getattr(app, "_assistant_message_streaming_active", False)
        ),
        "busy_status_hidden": bool(getattr(app, "_busy_status_hidden", False)),
        "live_activity_signatures": set(getattr(app, "_live_activity_signatures", set())),
        "live_command_execution_commands": dict(
            getattr(app, "_live_command_execution_commands", {}) or {}
        ),
        "live_streamed_texts": set(getattr(app, "_live_streamed_texts", set())),
        "live_turn_backfill_counts": dict(getattr(app, "_live_turn_backfill_counts", {}) or {}),
        "live_turn_event_sequence": int(getattr(app, "_live_turn_event_sequence", 0) or 0),
        "live_turn_event_signatures": set(getattr(app, "_live_turn_event_signatures", set())),
        "live_turn_final_separator_emitted": bool(
            getattr(app, "_live_turn_final_separator_emitted", False)
        ),
        "live_turn_had_work_activity": bool(getattr(app, "_live_turn_had_work_activity", False)),
        "live_turn_interrupt_requested": bool(
            getattr(app, "_live_turn_interrupt_requested", False)
        ),
        "live_turn_last_agent_message_key": getattr(app, "_live_turn_last_agent_message_key", None),
        "live_turn_last_agent_message_sequence": int(
            getattr(app, "_live_turn_last_agent_message_sequence", -1) or -1
        ),
        "live_turn_last_tool_sequence": int(
            getattr(app, "_live_turn_last_tool_sequence", -1) or -1
        ),
        "live_turn_request_is_slash": bool(getattr(app, "_live_turn_request_is_slash", False)),
        "pending_status_indicator_restore": bool(
            getattr(app, "_pending_status_indicator_restore", False)
        ),
        "transcript_turn_serial": int(getattr(app, "_transcript_turn_serial", 0) or 0),
    }


def restore_tab_live_turn_state(app: Any, state: dict[str, object]) -> None:
    app._active_transcript_turn_key = str(state.get("active_transcript_turn_key") or "turn:0")
    app._active_runtime_request_is_slash = bool(state.get("active_runtime_request_is_slash", False))
    app._active_runtime_request_text = str(state.get("active_runtime_request_text") or "")
    app._assistant_message_streaming_active = bool(
        state.get("assistant_message_streaming_active", False)
    )
    app._busy_status_hidden = bool(state.get("busy_status_hidden", False))
    app._live_activity_signatures = set(state.get("live_activity_signatures") or set())
    app._live_command_execution_commands = dict(state.get("live_command_execution_commands") or {})
    app._live_streamed_texts = set(state.get("live_streamed_texts") or set())
    app._live_turn_backfill_counts = dict(state.get("live_turn_backfill_counts") or {})
    app._live_turn_event_sequence = int(state.get("live_turn_event_sequence") or 0)
    app._live_turn_event_signatures = set(state.get("live_turn_event_signatures") or set())
    app._live_turn_final_separator_emitted = bool(
        state.get("live_turn_final_separator_emitted", False)
    )
    app._live_turn_had_work_activity = bool(state.get("live_turn_had_work_activity", False))
    app._live_turn_interrupt_requested = bool(state.get("live_turn_interrupt_requested", False))
    app._live_turn_last_agent_message_key = state.get("live_turn_last_agent_message_key")
    app._live_turn_last_agent_message_sequence = int(
        state.get("live_turn_last_agent_message_sequence") or -1
    )
    app._live_turn_last_tool_sequence = int(state.get("live_turn_last_tool_sequence") or -1)
    app._live_turn_request_is_slash = bool(state.get("live_turn_request_is_slash", False))
    app._pending_status_indicator_restore = bool(
        state.get("pending_status_indicator_restore", False)
    )
    app._transcript_turn_serial = int(state.get("transcript_turn_serial") or 0)


def run_with_tab_transcript_state(
    app: Any, session: object, callback: Callable[[], object]
) -> None:
    saved_entries = list(app._transcript_entries)
    saved_lines = list(app._transcript_lines)
    saved_snapshot_entries = app._transcript_screen_snapshot_entries
    saved_live_turn_state = app._capture_tab_live_turn_state()
    saved_status_override = getattr(app, "_status_data_session_override", None)
    app._transcript_entries = list(getattr(session, "transcript_entries", []) or [])
    app._transcript_lines = list(getattr(session, "transcript_lines", []) or [])
    app._transcript_screen_snapshot_entries = None
    app._status_data_session_override = session
    app._restore_tab_live_turn_state(dict(getattr(session, "live_turn_state", {}) or {}))
    try:
        callback()
    finally:
        session.transcript_entries = list(app._transcript_entries)
        session.transcript_lines = list(app._transcript_lines)
        session.live_turn_state = app._capture_tab_live_turn_state()
        app._transcript_entries = saved_entries
        app._transcript_lines = saved_lines
        app._transcript_screen_snapshot_entries = saved_snapshot_entries
        app._status_data_session_override = saved_status_override
        app._restore_tab_live_turn_state(saved_live_turn_state)
        try:
            app._update_bottom_dock(max(1, app.size.width))
        except Exception:
            pass


__all__ = [
    "capture_tab_live_turn_state",
    "restore_tab_live_turn_state",
    "run_with_tab_transcript_state",
]

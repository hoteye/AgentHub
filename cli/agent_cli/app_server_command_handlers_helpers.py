from __future__ import annotations

from typing import Any

from cli.agent_cli import app_server_command_handlers_runtime
from cli.agent_cli.app_server_shell_protocol import _first_text, _optional_int_param, _shell_phase


def handle_command_write_stdin(server: Any, request_id: Any, params: dict[str, Any]) -> None:
    session_id = _first_text(params, "sessionId", "session_id")
    chars = params.get("chars")
    requested_yield_time_ms = _optional_int_param(params, "yieldTimeMs", "yield_time_ms")
    if not session_id:
        server._emit_error_response(
            request_id=request_id,
            code=-32602,
            message="Invalid params",
            data={"detail": "params.sessionId must be a non-empty string"},
        )
        return
    if not isinstance(chars, str):
        server._emit_error_response(
            request_id=request_id,
            code=-32602,
            message="Invalid params",
            data={"detail": "params.chars must be a string"},
        )
        return
    entry = server._command_sessions.get(session_id)
    if not isinstance(entry, dict):
        server._emit_error_response(
            request_id=request_id,
            code=-32004,
            message="Unknown command session",
            data={"detail": session_id},
        )
        return
    tool_event = server._write_command_session_stdin(
        session_id,
        chars,
        yield_time_ms=requested_yield_time_ms,
        on_activity=lambda payload: server._emit_command_session_activity(
            request_id=entry["request_id"],
            stream=bool(entry.get("stream")),
            payload=payload,
        ),
    )
    tool_event = app_server_command_handlers_runtime.with_write_yield_time(
        tool_event,
        requested_yield_time_ms=requested_yield_time_ms,
    )
    if str((tool_event.payload or {}).get("status") or "").strip() == "unsupported":
        server._emit_error_response(
            request_id=request_id,
            code=-32005,
            message="Interactive shell unsupported",
        )
        return
    if _shell_phase(tool_event.payload) == "completed" and session_id in server._command_sessions:
        session_turn_events = list((entry or {}).get("turn_events") or [])
        server._emit_command_session_completed(
            request_id=entry["request_id"],
            session_id=session_id,
            command=str(entry.get("command") or ""),
            tool_event=tool_event,
            session_turn_events=session_turn_events,
        )
        server._command_sessions.pop(session_id, None)
    server._emit_result(
        request_id,
        app_server_command_handlers_runtime.build_write_stdin_result(
            tool_event=tool_event,
            session_id=session_id,
            chars=chars,
        ),
    )

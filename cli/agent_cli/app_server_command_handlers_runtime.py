from __future__ import annotations

from typing import Any

from cli.agent_cli.app_server_shell_protocol import (
    _optional_int_param,
    _shell_aggregated_output,
    _shell_call_id,
    _shell_lifecycle_dict,
    _shell_protocol_fields,
    _shell_stderr,
    _shell_stdout,
)
from cli.agent_cli.models import ToolEvent


def build_command_session_entry(
    *,
    request_id: Any,
    command: str,
    stream: bool,
    process_id: str,
    shell_options: dict[str, Any],
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "command": command,
        "stream": stream,
        "process_id": process_id,
        "shell_options": shell_options,
        "turn_events": [],
    }


def build_started_payload(
    *,
    session: dict[str, Any],
    command: str,
    session_id: str,
    process_id: str,
) -> dict[str, Any]:
    payload = {
        "phase": "started",
        "command": str(session.get("command") or command),
        "session_id": session_id,
        "call_id": _shell_call_id(session) or None,
        "process_id": process_id,
        "cwd": session.get("cwd"),
        "login": session.get("login"),
        "tty": session.get("tty"),
        "io_mode": session.get("io_mode"),
        "shell": session.get("shell"),
        "status": str(session.get("status") or "started"),
    }
    lifecycle = dict(session.get("lifecycle") or {})
    if lifecycle:
        payload["lifecycle"] = lifecycle
    return payload


def build_command_start_result(*, session: dict[str, Any], session_id: str, job_id: Any) -> dict[str, Any]:
    return {
        "accepted": True,
        "jobId": str(job_id),
        "kind": "command",
        **_shell_protocol_fields(session, session_id=session_id, include_raw=True),
        "stdout": _shell_stdout(session),
        "stderr": _shell_stderr(session),
        "aggregatedOutput": _shell_aggregated_output(session),
    }


def with_write_yield_time(tool_event: ToolEvent, *, requested_yield_time_ms: int | None) -> ToolEvent:
    tool_payload = dict(tool_event.payload or {})
    if requested_yield_time_ms is None or tool_payload.get("yield_time_ms") is not None:
        return tool_event
    tool_payload["yield_time_ms"] = requested_yield_time_ms
    return ToolEvent(
        name=tool_event.name,
        ok=tool_event.ok,
        summary=tool_event.summary,
        payload=tool_payload,
    )


def build_write_stdin_result(
    *,
    tool_event: ToolEvent,
    session_id: str,
    chars: str,
) -> dict[str, Any]:
    return {
        "accepted": bool(tool_event.ok),
        **_shell_protocol_fields(tool_event.payload, session_id=session_id, include_raw=True),
        "stdout": _shell_stdout(tool_event.payload),
        "stderr": _shell_stderr(tool_event.payload),
        "aggregatedOutput": _shell_aggregated_output(tool_event.payload),
        "toolEvent": {
            "name": tool_event.name,
            "ok": tool_event.ok,
            "summary": tool_event.summary,
            "payload": dict(tool_event.payload or {}),
        },
        "yieldTimeMs": _optional_int_param(dict(tool_event.payload or {}), "yield_time_ms"),
        "isPoll": not bool(chars),
    }


def build_terminate_result(
    *,
    payload: dict[str, Any] | None,
    session_id: str,
    command: str | None,
) -> dict[str, Any]:
    return {
        "ok": True,
        **_shell_protocol_fields(
            payload,
            session_id=session_id,
            command=command or None,
            include_raw=True,
        ),
        "stdout": _shell_stdout(payload),
        "stderr": _shell_stderr(payload),
        "aggregatedOutput": _shell_aggregated_output(payload),
        "interrupted": True,
        "already_requested": False,
        "run_token": session_id,
        "run_label": "command",
    }


def approved_shell_session_registration(
    *,
    request_id: Any,
    result: dict[str, Any],
) -> dict[str, Any] | None:
    action_request = result.get("action_request")
    action_result = result.get("action_result")
    if action_request is None or not isinstance(action_result, dict):
        return None
    if str(getattr(action_request, "action_type", "") or "").strip() != "shell_command":
        return None
    payload = dict(getattr(action_request, "payload", {}) or {})
    if str(payload.get("exec_mode") or "").strip().lower() != "session_start":
        return None
    output = dict(action_result.get("output") or {})
    session_id = str(output.get("session_id") or "").strip()
    if not session_id:
        return None
    metadata = dict(getattr(action_request, "metadata", {}) or {})
    source_request_id = metadata.get("app_server_request_id", request_id)
    stream = bool(metadata.get("app_server_stream", True))
    process_id = str(output.get("process_id") or session_id).strip() or session_id
    command = str(output.get("command") or payload.get("command") or "").strip()
    lifecycle = _shell_lifecycle_dict(output) or {
        "phase": "started",
        "kind": "begin",
        "call_id": _shell_call_id(output) or "",
        "session_id": session_id,
        "process_id": process_id,
        "source": "shell_session_manager",
        "status": "started",
    }
    shell_options = {
        "cwd": payload.get("cwd"),
        "login": payload.get("login"),
        "tty": payload.get("tty"),
        "shell": payload.get("shell"),
        "max_output_chars": payload.get("max_output_chars"),
    }
    return {
        "request_id": source_request_id,
        "stream": stream,
        "session_id": session_id,
        "command": command,
        "process_id": process_id,
        "session_entry": build_command_session_entry(
            request_id=source_request_id,
            command=command,
            stream=stream,
            process_id=process_id,
            shell_options=shell_options,
        ),
        "activity_payload": {
            "phase": "started",
            "command": command,
            "session_id": session_id,
            "call_id": _shell_call_id(output) or None,
            "process_id": process_id,
            "cwd": payload.get("cwd"),
            "login": payload.get("login"),
            "tty": payload.get("tty"),
            "shell": payload.get("shell"),
            "lifecycle": lifecycle,
        },
    }

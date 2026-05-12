from __future__ import annotations

import threading
from typing import Any

from cli.agent_cli.command_execution_summary_runtime import command_activity_params
from cli.agent_cli.app_server_shell_protocol import (
    _compose_command_turn_events,
    _completed_shell_item_events,
    _exit_code_for_response,
    _shell_activity_to_event,
    _shell_activity_to_turn_event,
    _shell_aggregated_output,
    _shell_phase,
    _shell_protocol_fields,
    _shell_stderr,
    _shell_stdout,
)
from cli.agent_cli.headless import prompt_response_to_dict
from cli.agent_cli.models import ActivityEvent, PromptResponse, ToolEvent, prompt_response_turn_events


def activity_event_to_dict(item: ActivityEvent) -> dict[str, Any]:
    return {
        "title": item.title,
        "status": item.status,
        "detail": item.detail,
        "kind": item.kind,
    }


def tool_event_to_dict(item: ToolEvent) -> dict[str, Any]:
    return {
        "name": item.name,
        "ok": item.ok,
        "summary": item.summary,
        "payload": dict(item.payload or {}),
    }


def tool_event_prompt_response(command: str, tool_event: ToolEvent, *, exec_mode: str = "exec_once") -> PromptResponse:
    response = PromptResponse(
        user_text=f"/shell start {command}" if exec_mode == "session_start" else f"/shell {command}",
        assistant_text="",
        commentary_text="",
        tool_events=[tool_event],
        handled_as_command=True,
    )
    response.turn_events = prompt_response_turn_events(response)
    return response


def emit_command_session_activity(
    server: Any,
    *,
    request_id: Any,
    stream: bool,
    payload: dict[str, Any],
) -> None:
    event = _shell_activity_to_event(payload)
    protocol_fields = _shell_protocol_fields(payload, include_raw=True)
    activity_payload = {
        "requestId": request_id,
        **{key: value for key, value in protocol_fields.items() if key != "raw"},
        "stdout": _shell_stdout(payload),
        "stderr": _shell_stderr(payload),
        "aggregatedOutput": _shell_aggregated_output(payload),
        "raw": dict(protocol_fields.get("raw") or {}),
    }
    turn_event = _shell_activity_to_turn_event(payload)
    session_id = str(payload.get("session_id") or "").strip()
    if session_id and turn_event is not None:
        entry = server._command_sessions.get(session_id)
        if isinstance(entry, dict):
            history = entry.get("turn_events")
            if isinstance(history, list):
                history.append(dict(turn_event))
    if stream and (event is not None or turn_event is not None):
        if event is not None:
            activity_payload["event"] = activity_event_to_dict(event)
        if turn_event is not None:
            activity_payload["turnEvent"] = turn_event
        server._emit_notification("session/activity", activity_payload)
    if _shell_phase(payload) != "completed":
        return
    entry = server._command_sessions.pop(session_id, None) if session_id else None
    if not isinstance(entry, dict):
        return
    tool_event = ToolEvent(
        name="shell",
        ok=bool(payload.get("ok")),
        summary=(
            "shell interrupted"
            if payload.get("interrupted")
            else ("shell timeout" if payload.get("timed_out") else f"shell rc={payload.get('returncode')}")
        ),
        payload={
            **dict(payload or {}),
            "command": str(payload.get("command") or ""),
            "session_id": session_id or None,
            "process_id": str(payload.get("process_id") or "") or None,
            "exit_code": payload.get("exit_code", payload.get("returncode")),
            "stdout": str(payload.get("stdout") or ""),
            "stderr": str(payload.get("stderr") or ""),
            "interrupted": bool(payload.get("interrupted")),
            "timed_out": bool(payload.get("timed_out")),
            "ok": bool(payload.get("ok")),
            "status": str(payload.get("status") or ""),
        },
    )
    emit_command_session_completed(
        server,
        request_id=entry["request_id"],
        session_id=session_id,
        command=str(entry.get("command") or ""),
        tool_event=tool_event,
        session_turn_events=list(entry.get("turn_events") or []),
    )


def emit_command_session_completed(
    server: Any,
    *,
    request_id: Any,
    session_id: str,
    command: str,
    tool_event: ToolEvent,
    session_turn_events: list[dict[str, Any]] | None = None,
) -> None:
    response = PromptResponse(
        user_text=f"/shell {command}",
        assistant_text="",
        commentary_text="",
        tool_events=[tool_event],
        handled_as_command=True,
    )
    original_payload = dict(tool_event.payload or {})
    override_payload = dict(original_payload)
    if tool_event.ok:
        override_payload["status"] = "ok"
    tool_event = ToolEvent(
        name=tool_event.name,
        ok=tool_event.ok,
        summary=tool_event.summary,
        payload=override_payload,
    )
    response.tool_events = [tool_event]
    response.turn_events = _compose_command_turn_events(
        response,
        item_events=_completed_shell_item_events(
            original_payload,
            session_turn_events=session_turn_events,
        ),
    )
    protocol_fields = _shell_protocol_fields(override_payload, session_id=session_id, include_raw=True)
    completed_fields = {key: value for key, value in protocol_fields.items() if key != "raw"}
    completed_fields["status"] = "ok" if tool_event.ok else (protocol_fields.get("status") or "error")
    completed_fields["raw"] = dict(original_payload or {})
    server._emit_notification(
        "command/completed",
        {
            "requestId": request_id,
            "kind": "command",
            **completed_fields,
            "stdout": _shell_stdout(tool_event.payload),
            "stderr": _shell_stderr(tool_event.payload),
            "aggregatedOutput": _shell_aggregated_output(tool_event.payload),
            "response": prompt_response_to_dict(response),
            "exitCode": _exit_code_for_response(response),
        },
    )


def run_direct_shell_command(
    server: Any,
    command: str,
    *,
    request_id: Any,
    stream: bool,
    cancel_event: threading.Event | None,
    shell_options: dict[str, Any] | None = None,
) -> PromptResponse:
    activity_events: list[ActivityEvent] = []
    item_events: list[dict[str, Any]] = []
    shell_options = dict(shell_options or {})
    metadata = dict(shell_options.pop("metadata", {}) or {})

    def on_activity(payload: dict[str, Any]) -> None:
        emit_command_session_activity(
            server,
            request_id=request_id,
            stream=stream,
            payload=payload,
        )
        event = _shell_activity_to_event(payload)
        if event is not None:
            activity_events.append(event)
        turn_event = _shell_activity_to_turn_event(payload)
        if turn_event is not None:
            item_events.append(dict(turn_event))

    result = server.runtime.begin_shell_request(
        command,
        on_activity=on_activity,
        cancel_event=cancel_event,
        requested_by="app_server",
        exec_mode="exec_once",
        metadata=metadata,
        **shell_options,
    )
    if result.get("status") == "approval_required":
        return result.get("response")
    tool_event = result.get("tool_event")
    if not any(item.status in {"ok", "error"} for item in activity_events):
        activity_events.append(
            ActivityEvent(
                title="Shell command completed",
                status="ok" if tool_event.ok else "error",
                detail=tool_event.summary,
                kind="command",
                code="command.run",
                params=command_activity_params({"command": command}),
            )
        )
    response = PromptResponse(
        user_text=f"/shell {command}",
        assistant_text="",
        commentary_text="",
        tool_events=[tool_event],
        activity_events=activity_events,
        handled_as_command=True,
    )
    response.turn_events = _compose_command_turn_events(response, item_events=item_events)
    return response

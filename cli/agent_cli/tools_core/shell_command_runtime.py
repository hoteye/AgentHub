from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Optional

from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.models import (
    CommandExecutionResult,
    ToolEvent,
    shell_command_assistant_text,
    shell_tool_call_item_events,
)


def shell_command_result(
    assistant_text: str,
    event: ToolEvent,
    *,
    command: str | None = None,
) -> CommandExecutionResult:
    return CommandExecutionResult(
        assistant_text=shell_command_assistant_text(str(assistant_text or ""), event),
        tool_events=[event],
        item_events=shell_tool_call_item_events(event, command=command),
    )


def session_started_event_from_session(
    session: Dict[str, Any],
    *,
    command: str,
    exec_mode: str = "session_start",
) -> ToolEvent:
    session_id = str(session.get("session_id") or "").strip()
    process_id = str(session.get("process_id") or session_id).strip() or session_id
    payload = {
        "command": str(session.get("command") or command),
        "session_id": session_id or None,
        "call_id": str(session.get("call_id") or "").strip() or None,
        "process_id": process_id or None,
        "cwd": session.get("cwd"),
        "login": session.get("login"),
        "tty": session.get("tty"),
        "shell": session.get("shell"),
        "started_at_ms": session.get("started_at_ms"),
        "exec_mode": exec_mode,
        "status": "started",
        "lifecycle": dict(session.get("lifecycle") or {})
        or {
            "phase": "started",
            "kind": "begin",
            "call_id": str(session.get("call_id") or "").strip(),
            "session_id": session_id,
            "process_id": process_id,
            "source": "shell_session_manager",
            "status": "started",
        },
    }
    for key in (
        "task_id",
        "background_artifact_path",
        "completion_notification_available",
        "completion_notification_status",
        "completion_poll_tool",
    ):
        if session.get(key) is not None:
            payload[key] = session.get(key)
    if session_id:
        return ToolEvent(
            name="shell_start",
            ok=True,
            summary=f"shell session started {session_id}",
            payload=payload,
        )
    return ToolEvent(
        name="shell_start",
        ok=False,
        summary="shell session start failed",
        payload={**payload, "error": "shell_start did not return session_id", "status": "start_failed"},
    )


def execute_shell(
    *,
    host_platform: HostPlatform,
    command: str,
    manager_factory: Callable[[HostPlatform], Any],
    cwd: Optional[str] = None,
    timeout_sec: int = 60,
    login: bool = True,
    tty: bool = False,
    shell: Optional[str] = None,
    max_output_chars: int = 12000,
    on_activity: Optional[Callable[[Dict[str, Any]], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> ToolEvent:
    normalized_command = str(command or "").strip()
    if not normalized_command:
        return ToolEvent(
            name="shell",
            ok=False,
            summary="shell invalid command",
            payload={
                "command": normalized_command,
                "error": "command must be a non-empty string",
                "timed_out": False,
                "interrupted": False,
                "status": "invalid",
            },
        )
    normalized_cwd = str(cwd or "").strip() or None
    normalized_shell = host_platform.normalize_shell_override(shell)
    manager = manager_factory(host_platform)
    try:
        session_info = manager.start_session(
            command=normalized_command,
            cwd=normalized_cwd,
            login=login,
            tty=tty,
            shell=normalized_shell,
            max_output_chars=max_output_chars,
            on_activity=on_activity,
            cancel_event=cancel_event,
        )
    except OSError as exc:
        started_at = time.monotonic()
        started_at_ms = int(time.time() * 1000)
        payload = {
            "command": normalized_command,
            "cwd": normalized_cwd,
            "call_id": None,
            "error": str(exc),
            "timed_out": False,
            "interrupted": False,
            "duration_ms": int((time.monotonic() - started_at) * 1000),
            "status": "spawn_failed",
            "exit_code": None,
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "stdout_truncated": False,
            "stderr_truncated": False,
            "stdout_total_chars": 0,
            "stderr_total_chars": 0,
            "session_id": None,
            "process_id": None,
            "login": bool(login),
            "tty": bool(tty),
            "shell": normalized_shell,
            "started_at_ms": started_at_ms,
            "finished_at_ms": int(time.time() * 1000),
            "lifecycle": {
                "phase": "spawn_failed",
                "kind": "end",
                "call_id": "",
                "session_id": "",
                "process_id": "",
                "source": "shell_session_manager",
                "status": "spawn_failed",
            },
        }
        if on_activity is not None:
            on_activity(
                {
                    "phase": "completed",
                    "command": normalized_command,
                    "cwd": normalized_cwd,
                    "timed_out": False,
                    "interrupted": False,
                    "duration_ms": payload["duration_ms"],
                    "ok": False,
                    "error": payload["error"],
                }
            )
        return ToolEvent(
            name="shell",
            ok=False,
            summary="shell spawn failed",
            payload=payload,
        )
    payload = manager.wait_for_completion(
        str(session_info.get("session_id") or ""),
        timeout_sec=timeout_sec,
        cancel_event=cancel_event,
        on_activity=on_activity,
    )
    returncode = payload.get("returncode")
    return ToolEvent(
        name="shell",
        ok=bool(payload.get("ok")),
        summary="shell interrupted"
        if payload.get("interrupted")
        else ("shell timeout" if payload.get("timed_out") else f"shell rc={returncode}"),
        payload=payload,
    )


def execute_shell_result(
    *,
    host_platform: HostPlatform,
    command: str,
    execute_shell_fn: Callable[..., ToolEvent],
    cwd: Optional[str] = None,
    timeout_sec: int = 60,
    login: bool = True,
    tty: bool = False,
    shell: Optional[str] = None,
    max_output_chars: int = 12000,
    on_activity: Optional[Callable[[Dict[str, Any]], None]] = None,
    cancel_event: Optional[threading.Event] = None,
) -> CommandExecutionResult:
    event = execute_shell_fn(
        host_platform=host_platform,
        command=command,
        cwd=cwd,
        timeout_sec=timeout_sec,
        login=login,
        tty=tty,
        shell=shell,
        max_output_chars=max_output_chars,
        on_activity=on_activity,
        cancel_event=cancel_event,
    )
    return shell_command_result("Run shell command.", event, command=command)

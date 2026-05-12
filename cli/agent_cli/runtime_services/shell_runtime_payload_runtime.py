from __future__ import annotations

from typing import Any, Dict


def shell_start_payload(
    session: Dict[str, Any],
    *,
    command: str,
    exec_mode: str,
) -> tuple[Dict[str, Any], str, str]:
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
    return payload, session_id, process_id


def apply_start_session_defaults(
    session: Dict[str, Any],
    *,
    normalized_command: str,
    effective_command: str,
    policy_payload: Dict[str, Any] | None,
    cwd: str | None,
    login: bool,
    tty: bool,
    shell: str | None,
) -> Dict[str, Any]:
    session_id = str(session.get("session_id") or "").strip()
    process_id = str(session.get("process_id") or session_id).strip() or session_id
    session["session_id"] = session_id
    session["process_id"] = process_id
    session.setdefault("command", normalized_command)
    if effective_command != normalized_command:
        session["effective_command"] = str(session.get("command") or effective_command)
        session["command"] = normalized_command
    if policy_payload:
        session["command_policy"] = policy_payload
    session.setdefault("cwd", cwd)
    session.setdefault("login", bool(login))
    session.setdefault("tty", bool(tty))
    session.setdefault("shell", shell)
    return session


def event_command(event: Any) -> str | None:
    payload = getattr(event, "payload", None)
    command = str((payload or {}).get("command") or "").strip()
    return command or None

from __future__ import annotations

from typing import Any, Dict, Optional

from cli.agent_cli.models import ShellLifecycleEnvelope, ToolEvent
from cli.agent_cli.tools_core.output_persistence_runtime import shell_background_contract_fields
from cli.agent_cli.tools_core.shell_session_state import _ShellSession


def completed_lifecycle_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "phase": "completed",
        "kind": "end",
        "call_id": str(payload.get("call_id") or ""),
        "session_id": str(payload.get("session_id") or ""),
        "process_id": str(payload.get("process_id") or ""),
        "source": "shell_session_manager",
        "status": "completed",
    }


def lifecycle_payload(
    *,
    phase: str,
    kind: str,
    call_id: str,
    session_id: str,
    process_id: str,
    source: str = "shell_session_manager",
    stream: str = "",
    status: str = "",
) -> Dict[str, Any]:
    return ShellLifecycleEnvelope(
        phase=phase,
        kind=kind,
        call_id=call_id,
        session_id=session_id,
        process_id=process_id,
        source=source,
        stream=stream,
        status=status,
    ).to_dict()


def event_payload(
    session: _ShellSession,
    *,
    phase: str,
    kind: str,
    stream: str = "",
    status: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = {
        "phase": phase,
        "command": session.command,
        "session_id": session.session_id,
        "call_id": session.call_id,
        "process_id": session.process_id,
        "io_mode": session.io_mode,
        "cwd": session.cwd,
        "login": session.login,
        "tty": session.tty,
        "shell": session.shell,
        "source": "shell_session_manager",
        "lifecycle": lifecycle_payload(
            phase=phase,
            kind=kind,
            call_id=session.call_id,
            session_id=session.session_id,
            process_id=session.process_id,
            stream=stream,
            status=status,
        ),
    }
    if status:
        payload["status"] = status
    if stream:
        payload["stream"] = stream
    if extra:
        payload.update(extra)
    payload.update(
        shell_background_contract_fields(
            payload,
            workspace_root=session.workspace_root,
            task_id=session.task_id,
            persist=phase == "started",
        )
    )
    return payload


def completed_replay_event(completed_payload: Dict[str, Any]) -> ToolEvent:
    payload = dict(completed_payload)
    payload.setdefault("phase", "completed")
    payload["lifecycle"] = completed_lifecycle_payload(payload)
    return ToolEvent(
        name="shell",
        ok=bool(payload.get("ok")),
        summary=f"shell rc={payload.get('returncode')}",
        payload=payload,
    )


def subscribe_payload_from_completed_payload(completed_payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(completed_payload or {})
    session_id = str(payload.get("session_id") or "").strip()
    call_id = str(payload.get("call_id") or "").strip()
    process_id = str(payload.get("process_id") or session_id).strip() or session_id
    subscribe_payload: Dict[str, Any] = {
        "phase": "subscribe",
        "command": str(payload.get("command") or ""),
        "session_id": session_id,
        "call_id": call_id,
        "process_id": process_id,
        "io_mode": str(payload.get("io_mode") or ""),
        "cwd": payload.get("cwd"),
        "login": payload.get("login"),
        "tty": payload.get("tty"),
        "shell": payload.get("shell"),
        "source": str(payload.get("source") or "shell_session_manager"),
        "status": "subscribed",
        "lifecycle": lifecycle_payload(
            phase="subscribe",
            kind="subscribe",
            call_id=call_id,
            session_id=session_id,
            process_id=process_id,
            status="subscribed",
        ),
    }
    subscribe_payload.update(
        shell_background_contract_fields(
            subscribe_payload,
            workspace_root=str(payload.get("workspace_root") or payload.get("cwd") or "").strip() or None,
            task_id=str(payload.get("task_id") or session_id).strip() or session_id,
            persist=False,
        )
    )
    return subscribe_payload


def completed_readonly_write_payload(
    completed_payload: Dict[str, Any],
    *,
    input_chars: str,
) -> Dict[str, Any]:
    payload = dict(completed_payload)
    payload.update(
        {
            "status": "completed",
            "final_status": completed_payload.get("status"),
            "accepted": False,
            "stdin": input_chars,
            "chars": input_chars,
            "interaction_input": input_chars,
            "ok": False,
        }
    )
    payload.setdefault("phase", "completed")
    payload["lifecycle"] = completed_lifecycle_payload(payload)
    payload.update(
        shell_background_contract_fields(
            payload,
            workspace_root=str(payload.get("workspace_root") or payload.get("cwd") or "").strip() or None,
            task_id=str(payload.get("task_id") or payload.get("session_id") or "").strip() or None,
            persist=False,
            foreground_adopted=True,
        )
    )
    return payload

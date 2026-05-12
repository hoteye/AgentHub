from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def preview_text(value: Any, *, max_chars: int = 240) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}..."


def runtime_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def preserve_terminal_reason(session: Any, fallback: str) -> str:
    existing = str(getattr(session, "terminal_reason", "") or "").strip()
    return existing or str(fallback or "").strip()


def sync_delegated_run_record(
    runtime: Any,
    session: Any,
    *,
    forced_status: str | None = None,
    forced_summary: str | None = None,
) -> None:
    manager = getattr(runtime, "run_manager", None)
    if manager is None:
        return
    agent_id = str(getattr(session, "agent_id", "") or "").strip()
    protocol_run_id = str(getattr(session, "protocol_run_id", "") or "").strip()
    run_id = protocol_run_id or f"delegated:{agent_id or 'unknown'}"
    if not run_id:
        return
    role = str(getattr(session, "role", "") or "").strip().lower()
    delegation_mode = str(getattr(session, "delegation_mode", "") or "").strip().lower()
    kind = "background" if role == "teammate" and delegation_mode == "background" else "task"
    parent_run_id = str(getattr(session, "protocol_parent_run_id", "") or "").strip()
    thread_id = (
        str(getattr(session, "protocol_thread_id", "") or "").strip()
        or str(getattr(runtime, "thread_id", "") or "").strip()
    )
    status = str(forced_status or "").strip().lower()
    if not status:
        session_status = str(getattr(session, "status", "") or "").strip().lower()
        terminal_reason = str(getattr(session, "terminal_reason", "") or "").strip().lower()
        if session_status in {"running", "starting"}:
            status = "running"
        elif session_status == "failed":
            status = "failed"
        elif session_status == "completed":
            status = "completed"
        elif session_status == "closed":
            if terminal_reason == "failed":
                status = "failed"
            elif terminal_reason == "completed":
                status = "completed"
            else:
                status = "cancelled"
        else:
            status = "created"
    summary = str(forced_summary or "").strip() or f"delegated session {status}"
    payload = {
        "agent_id": agent_id,
        "role": str(getattr(session, "role", "") or "").strip(),
        "session_status": str(getattr(session, "status", "") or "").strip(),
        "terminal_reason": str(getattr(session, "terminal_reason", "") or "").strip(),
        "delegation_mode": str(getattr(session, "delegation_mode", "") or "").strip(),
    }
    if manager.get(run_id) is None:
        try:
            manager.create(
                run_id=run_id,
                kind=kind,
                thread_id=thread_id,
                parent_run_id=parent_run_id,
                summary="delegated session created",
                payload=payload,
            )
        except Exception:
            return
    try:
        manager.update(run_id, status=status, summary=summary, payload=payload)
    except Exception:
        return

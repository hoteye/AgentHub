from __future__ import annotations

from typing import Any, Callable


def delegated_background_task_status(status: str, *, has_text: bool, terminal_reason: str = "") -> str:
    normalized = str(status or "").strip().lower() or "queued"
    normalized_reason = str(terminal_reason or "").strip().lower()
    if normalized in {"running", "starting", "closing"}:
        return "running"
    if normalized == "completed":
        return "completed"
    if normalized == "failed":
        return "failed"
    if normalized == "closed":
        if normalized_reason in {"orphan_cleanup", "restore_resolution_failed", "role_override_changed"}:
            return "cancelled"
        return "completed" if has_text else "cancelled"
    return "queued"


def delegated_background_notification_state(
    *,
    status: str,
    adopted: bool,
    terminal_reason: str,
) -> str:
    normalized_status = str(status or "").strip().lower() or "queued"
    normalized_reason = str(terminal_reason or "").strip().lower()
    if adopted:
        return "foreground_adopted"
    if normalized_reason in {"orphan_cleanup", "restore_resolution_failed", "role_override_changed"}:
        return "orphaned"
    if normalized_status in {"queued", "starting", "running", "closing", "idle"}:
        return "pending"
    if normalized_status == "failed":
        return "failed"
    if normalized_status == "closed":
        return "closed"
    if normalized_status == "completed":
        return "ready"
    return "pending"


def delegated_orphan_cleanup_candidate(
    *,
    status: Any,
    queued_inputs: list[dict[str, Any]] | None = None,
    active_input: dict[str, Any] | None = None,
) -> bool:
    normalized_status = str(status or "").strip().lower()
    if active_input is not None:
        return True
    if list(queued_inputs or []):
        return True
    return normalized_status in {"queued", "starting", "running", "closing", "idle"}


def request_session_cleanup(
    *,
    session: Any,
    reason: str,
    summary: str,
    now_iso_fn: Callable[[], str],
    refresh_current_step_id_fn: Callable[[Any], Any],
    record_checkpoint_fn: Callable[..., None],
) -> dict[str, Any]:
    normalized_reason = str(reason or "").strip()
    if session.closed and str(session.terminal_reason or "").strip().lower() == normalized_reason.lower():
        return {"changed": False, "worker_running": False}
    worker_running = bool(session.worker is not None and session.worker.is_alive())
    if session.active_input is not None:
        session.cancel_event.set()
    session.close_requested = True
    session.terminal_reason = normalized_reason
    session.queued_inputs.clear()
    if worker_running and session.active_input is not None:
        session.status = "closing"
        checkpoint_status = "closing"
    else:
        session.closed = True
        session.active_input = None
        session.status = "closed"
        checkpoint_status = "closed"
    session.scheduler_reason = ""
    refresh_current_step_id_fn(session)
    session.updated_at = now_iso_fn()
    record_checkpoint_fn(
        session,
        kind="session_orphan_cleanup",
        status=checkpoint_status,
        summary=summary,
        step_id=str(session.current_step_id or "").strip(),
    )
    return {"changed": True, "worker_running": worker_running}


def restored_delegated_status(
    *,
    status: Any,
    queued_inputs: list[dict[str, Any]],
    close_requested: bool,
    closed: bool,
    assistant_text: str,
    error: str,
) -> str:
    normalized = str(status or "").strip().lower()
    if closed:
        return "closed"
    if queued_inputs:
        return "queued"
    if normalized == "failed" or (error and not assistant_text):
        return "failed"
    if close_requested:
        return "closed"
    if assistant_text or normalized == "completed":
        return "completed"
    if normalized == "idle":
        return "idle"
    return "idle"

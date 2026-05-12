from __future__ import annotations

from typing import Any, Dict, List


def delegated_step_id(session: Any) -> str:
    return f"step_{len(list(session.progress_steps or [])) + 1}"


def delegated_step(session: Any, step_id: str) -> Dict[str, Any] | None:
    normalized = str(step_id or "").strip()
    if not normalized:
        return None
    for item in reversed(list(session.progress_steps or [])):
        if isinstance(item, dict) and str(item.get("step_id") or "").strip() == normalized:
            return item
    return None


def delegated_queue_item_step_id(item: Any) -> str:
    if not isinstance(item, dict):
        return ""
    return str(item.get("step_id") or "").strip()


def resolved_delegated_current_step_id(session: Any) -> str:
    active_step_id = delegated_queue_item_step_id(session.active_input)
    if active_step_id:
        return active_step_id
    for item in list(session.queued_inputs or []):
        queued_step_id = delegated_queue_item_step_id(item)
        if queued_step_id:
            return queued_step_id
    current_step_id = str(session.current_step_id or "").strip()
    if current_step_id and delegated_step(session, current_step_id) is not None:
        return current_step_id
    if session.progress_steps:
        last_step = session.progress_steps[-1]
        if isinstance(last_step, dict):
            return str(last_step.get("step_id") or "").strip()
    return ""


def refresh_delegated_current_step_id(session: Any) -> str:
    session.current_step_id = resolved_delegated_current_step_id(session)
    return session.current_step_id


def record_delegated_checkpoint(
    session: Any,
    *,
    kind: str,
    status: str,
    summary: str,
    now_iso,
    step_id: str = "",
) -> None:
    checkpoint = {
        "checkpoint_id": f"checkpoint_{len(list(session.progress_checkpoints or [])) + 1}",
        "kind": str(kind or "").strip() or "checkpoint",
        "status": str(status or "").strip() or "info",
        "summary": str(summary or "").strip(),
        "timestamp": now_iso(),
    }
    if str(step_id or "").strip():
        checkpoint["step_id"] = str(step_id or "").strip()
    session.progress_checkpoints.append(checkpoint)


def queue_delegated_step(
    session: Any,
    *,
    user_text: str,
    source: str,
    preview_text,
    now_iso,
    retry_of_step_id: str = "",
    retry_root_step_id: str = "",
    retry_attempt: int = 0,
) -> str:
    step_id = delegated_step_id(session)
    step = {
        "step_id": step_id,
        "index": len(list(session.progress_steps or [])) + 1,
        "title": preview_text(user_text or step_id, max_chars=96),
        "status": "queued",
        "source": str(source or "queued"),
        "user_text": str(user_text or "").strip(),
        "retry_attempt": max(0, int(retry_attempt or 0)),
        "queued_at": now_iso(),
        "started_at": "",
        "finished_at": "",
        "summary": "queued",
        "assistant_text": "",
        "error": "",
    }
    if str(retry_of_step_id or "").strip():
        step["retry_of_step_id"] = str(retry_of_step_id or "").strip()
    if str(retry_root_step_id or "").strip():
        step["retry_root_step_id"] = str(retry_root_step_id or "").strip()
    session.progress_steps.append(step)
    if session.active_input is None and not list(session.queued_inputs or []):
        session.current_step_id = step_id
    record_delegated_checkpoint(
        session,
        kind="step_queued",
        status="queued",
        summary=f"queued {step_id}",
        step_id=step_id,
        now_iso=now_iso,
    )
    return step_id


def update_delegated_step(
    session: Any,
    *,
    step_id: str,
    status: str,
    summary: str,
    now_iso,
    assistant_text: str = "",
    error: str = "",
    started: bool = False,
    finished: bool = False,
) -> None:
    step = delegated_step(session, step_id)
    if step is None:
        return
    now = now_iso()
    step["status"] = str(status or "").strip() or str(step.get("status") or "queued")
    step["summary"] = str(summary or "").strip() or str(step.get("summary") or "")
    if started and not str(step.get("started_at") or "").strip():
        step["started_at"] = now
    if finished:
        step["finished_at"] = now
    if assistant_text:
        step["assistant_text"] = str(assistant_text or "").strip()
    if error:
        step["error"] = str(error or "").strip()


def delegated_step_retry_root_id(step: Dict[str, Any] | None) -> str:
    if not isinstance(step, dict):
        return ""
    return (
        str(step.get("retry_root_step_id") or "").strip()
        or str(step.get("retry_of_step_id") or "").strip()
        or str(step.get("step_id") or "").strip()
    )


def delegated_step_retry_attempt(step: Dict[str, Any] | None) -> int:
    if not isinstance(step, dict):
        return 0
    try:
        return max(0, int(step.get("retry_attempt") or 0))
    except (TypeError, ValueError):
        return 0


def next_delegated_retry_attempt(session: Any, *, retry_root_step_id: str) -> int:
    normalized_root = str(retry_root_step_id or "").strip()
    if not normalized_root:
        return 1
    max_attempt = 0
    for item in list(session.progress_steps or []):
        if not isinstance(item, dict):
            continue
        if delegated_step_retry_root_id(item) != normalized_root:
            continue
        max_attempt = max(max_attempt, delegated_step_retry_attempt(item))
    return max_attempt + 1


def delegated_latest_recoverable_step(
    session: Any,
    *,
    step_id: str = "",
) -> Dict[str, Any] | None:
    normalized_step_id = str(step_id or "").strip()
    if normalized_step_id:
        candidate = delegated_step(session, normalized_step_id)
        if not isinstance(candidate, dict):
            return None
        if str(candidate.get("status") or "").strip() not in {"failed", "cancelled"}:
            return None
        if not str(candidate.get("user_text") or "").strip():
            return None
        return candidate
    for item in reversed(list(session.progress_steps or [])):
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "").strip()
        if status in {"completed", "running", "queued"}:
            break
        if status not in {"failed", "cancelled"}:
            continue
        if not str(item.get("user_text") or "").strip():
            continue
        return item
    return None


def delegated_recovery_actions(session: Any) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    recoverable_step = None
    if session.active_input is None and not list(session.queued_inputs or []):
        recoverable_step = delegated_latest_recoverable_step(session)
    if recoverable_step is not None:
        actions.append(
            {
                "action": "retry_step",
                "label": "retry failed step",
                "step_id": str(recoverable_step.get("step_id") or "").strip(),
                "retry_root_step_id": delegated_step_retry_root_id(recoverable_step),
                "retry_attempt": delegated_step_retry_attempt(recoverable_step) + 1,
                "reason": str(recoverable_step.get("status") or "").strip() or "failed",
            }
        )
    if session.closed or session.close_requested:
        actions.append(
            {
                "action": "resume_session",
                "label": "resume delegated session",
            }
        )
    if not (session.closed or session.close_requested):
        actions.append(
            {
                "action": "close_session",
                "label": "close delegated session",
            }
        )
    return actions


def delegated_workflow_state(session: Any) -> str:
    status = str(session.status or "").strip().lower() or "queued"
    if status in {"queued", "starting", "running", "closing"}:
        return "active"
    if delegated_latest_recoverable_step(session) is not None:
        return "recoverable"
    if status == "completed":
        return "completed"
    if status == "closed":
        return "closed"
    if status == "failed":
        return "failed"
    return "idle"


def delegated_progress_summary(
    session: Any,
    *,
    include_history: bool = False,
) -> Dict[str, Any]:
    current_step_id = resolved_delegated_current_step_id(session)
    current_step = delegated_step(session, current_step_id)
    payload: Dict[str, Any] = {
        "step_count": len(list(session.progress_steps or [])),
        "checkpoint_count": len(list(session.progress_checkpoints or [])),
        "workflow_state": delegated_workflow_state(session),
    }
    if current_step_id:
        payload["current_step_id"] = current_step_id
    if isinstance(current_step, dict):
        payload["current_step_status"] = str(current_step.get("status") or "").strip() or "queued"
        payload["current_step_title"] = str(current_step.get("title") or "").strip()
    recovery_actions = delegated_recovery_actions(session)
    payload["recovery_action_count"] = len(recovery_actions)
    if recovery_actions:
        payload["recovery_actions"] = [dict(item) for item in recovery_actions if isinstance(item, dict)]
    if session.progress_checkpoints:
        latest_checkpoint = session.progress_checkpoints[-1]
        if isinstance(latest_checkpoint, dict):
            payload["latest_checkpoint"] = dict(latest_checkpoint)
    if include_history:
        payload["steps"] = [
            dict(item)
            for item in list(session.progress_steps or [])
            if isinstance(item, dict)
        ]
        payload["checkpoints"] = [
            dict(item)
            for item in list(session.progress_checkpoints or [])
            if isinstance(item, dict)
        ]
    return payload

from __future__ import annotations

from typing import Any

from . import lifecycle_runtime as lifecycle_runtime_service
from .models import BackgroundTaskStatus, TaskEnvelope, TaskResult, utc_now_iso
from .storage import BackgroundTaskStorage


def _claim_dispatch(
    storage: BackgroundTaskStorage,
    envelope: TaskEnvelope,
    *,
    runner_token: str,
    claimed: bool,
) -> bool:
    if claimed:
        control = storage.get_control(envelope.task_id)
        return bool(
            isinstance(control, dict)
            and int(control.get("dispatch_id") or 1) == int(envelope.dispatch_id or 1)
            and str(control.get("queue_state") or "") == BackgroundTaskStatus.RUNNING.value
            and str(control.get("runner_token") or "") == str(runner_token or "")
        )
    if storage.get_control(envelope.task_id) is None:
        storage.upsert_envelope(
            envelope,
            queue_state=BackgroundTaskStatus.RUNNING.value,
            runner_token=runner_token,
        )
        return True
    return storage.claim_dispatch(
        envelope.task_id,
        dispatch_id=envelope.dispatch_id,
        runner_token=runner_token,
    )


def _task_artifact(
    envelope: TaskEnvelope,
    *,
    queue_state: str,
    cancel_requested: bool,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return lifecycle_runtime_service.normalize_artifact(
        artifact=dict(extra or {}),
        task_type=envelope.task_type.value,
        dispatch_id=int(envelope.dispatch_id or 1),
        queue_state=str(queue_state or ""),
        cancel_requested=bool(cancel_requested),
    )


def _cancelled_result(
    envelope: TaskEnvelope,
    *,
    started_at: str,
    retry_count: int,
    summary: str,
) -> TaskResult:
    return TaskResult(
        task_id=envelope.task_id,
        status=BackgroundTaskStatus.CANCELLED,
        started_at=started_at,
        finished_at=utc_now_iso(),
        summary=summary,
        artifact=_task_artifact(
            envelope,
            queue_state=BackgroundTaskStatus.CANCELLED.value,
            cancel_requested=False,
            extra={"terminal_state": "cancelled"},
        ),
        retry_count=retry_count,
    )


def _subprocess_progress_payload(
    *,
    title: str,
    goal: str,
    command: list[str],
    returncode: int,
    started_at: str,
    finished_at: str,
    status: BackgroundTaskStatus,
    summary: str,
    error: str = "",
) -> dict[str, Any]:
    step_status = (
        "cancelled"
        if status == BackgroundTaskStatus.CANCELLED
        else "completed"
        if status == BackgroundTaskStatus.COMPLETED
        else "failed"
    )
    step = {
        "step_id": "step_1",
        "index": 1,
        "title": title,
        "status": step_status,
        "source": "background_task",
        "summary": summary,
        "queued_at": started_at,
        "started_at": started_at,
        "finished_at": finished_at,
        "command": list(command or []),
        "returncode": int(returncode),
        "assistant_text": "",
        "error": error,
    }
    terminal_kind = "step_completed"
    if step_status == "failed":
        terminal_kind = "step_failed"
    elif step_status == "cancelled":
        terminal_kind = "step_cancelled"
    checkpoints = [
        {
            "checkpoint_id": "checkpoint_1",
            "kind": "step_started",
            "status": "running",
            "summary": f"started background task {goal}",
            "timestamp": started_at,
            "step_id": "step_1",
        },
        {
            "checkpoint_id": "checkpoint_2",
            "kind": terminal_kind,
            "status": step_status,
            "summary": summary,
            "timestamp": finished_at,
            "step_id": "step_1",
        },
    ]
    return {
        "goal": goal,
        "step_count": 1,
        "checkpoint_count": len(checkpoints),
        "current_step_id": "step_1",
        "current_step_status": step_status,
        "current_step_title": str(step.get("title") or ""),
        "latest_checkpoint": dict(checkpoints[-1]),
        "steps": [step],
        "checkpoints": checkpoints,
    }


def _subprocess_artifact(progress_payload: dict[str, Any]) -> dict[str, Any]:
    artifact = {
        "step_count": int(progress_payload.get("step_count") or 0),
        "checkpoint_count": int(progress_payload.get("checkpoint_count") or 0),
        "current_step_id": str(progress_payload.get("current_step_id") or ""),
        "current_step_status": str(progress_payload.get("current_step_status") or ""),
    }
    if str(progress_payload.get("current_step_title") or "").strip():
        artifact["current_step_title"] = str(progress_payload.get("current_step_title") or "").strip()
    latest_checkpoint = progress_payload.get("latest_checkpoint")
    if isinstance(latest_checkpoint, dict):
        artifact["latest_checkpoint"] = dict(latest_checkpoint)
    return artifact

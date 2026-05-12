from __future__ import annotations

from typing import Any, Callable

from .models import BackgroundTaskStatus, TaskEnvelope, TaskResult


def lifecycle_visibility(status_payload: dict[str, Any]) -> dict[str, Any]:
    artifact = dict(status_payload.get("artifact") or {})
    return {
        "queue_source_of_truth": str(status_payload.get("queue_source_of_truth") or ""),
        "queue_provider": str(status_payload.get("queue_provider") or ""),
        "queue_state": str(status_payload.get("queue_state") or ""),
        "dispatch_id": int(status_payload.get("dispatch_id") or 0),
        "last_event": str(artifact.get("lifecycle_last_event") or ""),
        "cleanup_count": int(artifact.get("lifecycle_cleanup_count") or 0),
        "restore_count": int(artifact.get("lifecycle_restore_count") or 0),
        "stale_requeue_count": int(artifact.get("stale_requeue_count") or 0),
    }


def build_cancelled_before_execution_result(
    *,
    task_id: str,
    status_payload: dict[str, Any],
    result: TaskResult,
    provider: str,
    status_artifact_fn: Callable[..., dict[str, Any]],
    now_fn: Callable[[], str],
) -> TaskResult:
    return TaskResult(
        task_id=task_id,
        status=BackgroundTaskStatus.CANCELLED,
        started_at=str(result.started_at or ""),
        finished_at=now_fn(),
        summary="cancelled before execution",
        artifact=status_artifact_fn(
            result,
            task_type=str(status_payload.get("task_type") or ""),
            dispatch_id=int(status_payload.get("dispatch_id") or 0),
            queue_state="cancelled",
            cancel_requested=False,
            provider=provider,
        ),
        error=str(result.error or ""),
        retry_count=int(result.retry_count or 0),
    )


def build_cancel_requested_result(
    *,
    task_id: str,
    status_payload: dict[str, Any],
    result: TaskResult,
    provider: str,
    status_artifact_fn: Callable[..., dict[str, Any]],
) -> TaskResult:
    return TaskResult(
        task_id=task_id,
        status=result.status,
        started_at=str(result.started_at or ""),
        finished_at=str(result.finished_at or ""),
        summary=str(result.summary or "cancel requested"),
        artifact=status_artifact_fn(
            result,
            task_type=str(status_payload.get("task_type") or ""),
            dispatch_id=int(status_payload.get("dispatch_id") or 0),
            queue_state=str(status_payload.get("queue_state") or ""),
            cancel_requested=True,
            provider=provider,
        ),
        error=str(result.error or ""),
        retry_count=int(result.retry_count or 0),
    )


def build_retry_restore_artifact(
    *,
    next_envelope: TaskEnvelope,
    queue_provider: str,
    queued_artifact_fn: Callable[..., dict[str, Any]],
    prior_artifact: dict[str, Any] | None,
    prior_status: Any,
    now_fn: Callable[[], str],
) -> dict[str, Any]:
    retry_artifact = queued_artifact_fn(next_envelope, provider=queue_provider)
    retry_artifact["lifecycle_last_event"] = "manual_retry_restore"
    retry_artifact["lifecycle_restore_from_status"] = getattr(prior_status, "value", str(prior_status or ""))
    retry_artifact["lifecycle_restore_at"] = now_fn()
    retry_artifact["lifecycle_restore_count"] = int(
        dict(prior_artifact or {}).get("lifecycle_restore_count") or 0
    ) + 1
    return retry_artifact

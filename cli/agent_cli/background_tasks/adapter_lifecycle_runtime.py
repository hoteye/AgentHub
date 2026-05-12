from __future__ import annotations

from typing import Any, Callable

from . import adapter_runtime as adapter_runtime_service
from . import adapter_status_runtime as adapter_status_runtime_service
from . import lifecycle_runtime as lifecycle_runtime_service
from .models import BackgroundTaskStatus, TaskResult


def reconcile_terminal_control(
    *,
    storage: Any,
    task_id: str,
    result: TaskResult | None,
    control: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if result is None or not isinstance(control, dict):
        return control
    result_status = str(getattr(getattr(result, "status", None), "value", "") or "").strip().lower()
    if not lifecycle_runtime_service.is_terminal_background_task_state(result_status):
        return control
    queue_state = str(control.get("queue_state") or "").strip().lower()
    if lifecycle_runtime_service.is_terminal_background_task_state(queue_state):
        return control
    result_dispatch_id = int(dict(getattr(result, "artifact", {}) or {}).get("dispatch_id") or 0)
    control_dispatch_id = int(control.get("dispatch_id") or 0)
    if result_dispatch_id <= 0 or result_dispatch_id != control_dispatch_id:
        return control
    if not storage.complete_dispatch(
        task_id,
        dispatch_id=control_dispatch_id,
        queue_state=result_status,
    ):
        return control
    refreshed = storage.control_snapshot(task_id)
    return refreshed if isinstance(refreshed, dict) else control


def cancel_task(
    *,
    storage: Any,
    task_id: str,
    provider_label: str,
    get_status_fn: Callable[[str], dict[str, Any] | None],
    status_artifact_fn: Callable[..., dict[str, Any]],
    now_fn: Callable[[], str],
) -> dict[str, Any] | None:
    status = get_status_fn(task_id)
    if status is None:
        return None
    control = status.get("control")
    normalized_status = str(status.get("status") or "").strip().lower()
    normalized_queue_state = str(status.get("queue_state") or "").strip().lower()
    if lifecycle_runtime_service.is_terminal_background_task_state(
        normalized_status
    ) or lifecycle_runtime_service.is_terminal_background_task_state(normalized_queue_state):
        return status
    result_payload = status.get("result")
    if not storage.request_cancel(task_id):
        return status
    if isinstance(control, dict) and str(control.get("queue_state") or "") == "queued":
        storage.cancel_queued(task_id)
        result = TaskResult.from_dict(result_payload if isinstance(result_payload, dict) else {"task_id": task_id})
        storage.upsert_result(
            adapter_status_runtime_service.build_cancelled_before_execution_result(
                task_id=task_id,
                status_payload=status,
                result=result,
                provider=provider_label,
                status_artifact_fn=status_artifact_fn,
                now_fn=now_fn,
            )
        )
        return get_status_fn(task_id)
    result = TaskResult.from_dict(result_payload if isinstance(result_payload, dict) else {"task_id": task_id})
    storage.upsert_result(
        adapter_status_runtime_service.build_cancel_requested_result(
            task_id=task_id,
            status_payload=status,
            result=result,
            provider=provider_label,
            status_artifact_fn=status_artifact_fn,
        )
    )
    return get_status_fn(task_id)


def retry_task(
    *,
    storage: Any,
    task_id: str,
    provider_label: str,
    get_status_fn: Callable[[str], dict[str, Any] | None],
    get_envelope_fn: Callable[[str], Any],
    enqueue_fn: Callable[[Any], Any],
    queued_artifact_fn: Callable[..., dict[str, Any]],
    now_fn: Callable[[], str],
    task_result_cls: Any,
    task_envelope_cls: Any,
) -> dict[str, Any] | None:
    status = get_status_fn(task_id)
    if status is None:
        return None
    result_payload = status.get("result")
    envelope = get_envelope_fn(task_id)
    if envelope is None:
        return status
    result = task_result_cls.from_dict(result_payload if isinstance(result_payload, dict) else {"task_id": task_id})
    if result.status not in {BackgroundTaskStatus.FAILED, BackgroundTaskStatus.CANCELLED}:
        return status
    next_payload = envelope.to_dict()
    next_payload["dispatch_id"] = max(1, int(envelope.dispatch_id or 1)) + 1
    next_payload["created_at"] = now_fn()
    next_envelope = task_envelope_cls.from_dict(next_payload)
    next_retry_count = int(result.retry_count or 0) + 1
    handle = enqueue_fn(next_envelope)
    refreshed = get_status_fn(task_id) or {"task_id": task_id}
    refreshed["retry_count"] = next_retry_count
    refreshed["handle"] = handle.to_dict()
    retry_artifact = adapter_status_runtime_service.build_retry_restore_artifact(
        next_envelope=next_envelope,
        queue_provider=provider_label,
        queued_artifact_fn=queued_artifact_fn,
        prior_artifact=dict(getattr(result, "artifact", {}) or {}),
        prior_status=result.status,
        now_fn=now_fn,
    )
    storage.upsert_result(
        task_result_cls(
            task_id=task_id,
            status=BackgroundTaskStatus.QUEUED,
            summary="queued for retry",
            artifact=retry_artifact,
            retry_count=next_retry_count,
        )
    )
    return get_status_fn(task_id)


def cleanup_stale_tasks(
    *,
    storage: Any,
    provider_label: str,
    max_age_seconds: float,
    now_fn: Callable[[], str],
) -> list[dict[str, Any]]:
    recovered = list(storage.requeue_stale_running(max_age_seconds=max_age_seconds) or [])
    if not recovered:
        return []
    recovered_at = now_fn()
    for item in recovered:
        task_id = str(item.get("task_id") or "").strip()
        if not task_id:
            continue
        current = storage.get_result(task_id)
        artifact = adapter_runtime_service.stale_requeue_artifact(
            current_artifact=dict(getattr(current, "artifact", {}) or {}),
            item=item,
            recovered_at=recovered_at,
            provider=provider_label,
        )
        artifact["lifecycle_last_event"] = "cleanup_requeue"
        artifact["lifecycle_cleanup_recovered_at"] = recovered_at
        artifact["lifecycle_cleanup_count"] = int(artifact.get("lifecycle_cleanup_count") or 0) + 1
        artifact["lifecycle_requeue_dispatch_id"] = int(item.get("dispatch_id") or 0)
        storage.upsert_result(
            TaskResult(
                task_id=task_id,
                status=BackgroundTaskStatus.QUEUED,
                started_at=str(getattr(current, "started_at", "") or ""),
                finished_at="",
                summary="queued after stale worker cleanup",
                artifact=artifact,
                error="",
                retry_count=int(getattr(current, "retry_count", 0) or 0),
            )
        )
    return recovered


def run_pending(
    *,
    queue: Any,
    storage: Any,
    max_jobs: int,
    perform_maintenance: bool,
    cleanup_stale_tasks_fn: Callable[[], list[dict[str, Any]]],
    new_task_id_fn: Callable[[str], str],
    execute_background_task_fn: Callable[..., Any],
) -> int:
    if perform_maintenance:
        cleanup_stale_tasks_fn()
    # Provider queue heartbeat hook only; dispatch table remains the
    # source of truth for backlog and task consumption.
    queue.run_pending(max_jobs=max_jobs)
    completed = 0
    remaining = max(1, int(max_jobs))
    for _ in range(remaining):
        runner_token = new_task_id_fn("bgw")
        envelope = storage.claim_next_queued(runner_token=runner_token)
        if envelope is None:
            break
        execute_background_task_fn(
            envelope,
            storage=storage,
            runner_token=runner_token,
            claimed=True,
        )
        completed += 1
    return completed

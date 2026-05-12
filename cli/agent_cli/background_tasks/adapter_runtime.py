from __future__ import annotations

from typing import Any

from . import lifecycle_runtime as lifecycle_runtime_service


def build_status_payload(
    *,
    task_id: str,
    result: Any,
    control: dict[str, Any] | None,
    queue_source_of_truth: str,
    queue_provider: str,
) -> dict[str, Any]:
    result_artifact = dict(getattr(result, "artifact", {}) or {}) if result is not None else {}
    envelope_payload = control.get("envelope") if isinstance(control, dict) else None
    task_type = ""
    dispatch_id = 0
    queue_state = ""
    cancel_requested = False
    runner_pid = 0
    if isinstance(control, dict):
        if isinstance(envelope_payload, dict):
            task_type = str(envelope_payload.get("task_type") or "").strip()
        task_type = task_type or str(control.get("task_type") or "").strip()
        dispatch_id = int(control.get("dispatch_id") or 0)
        queue_state = str(control.get("queue_state") or "").strip()
        cancel_requested = bool(control.get("cancel_requested"))
        runner_pid = int(control.get("runner_pid") or 0)
    if not task_type:
        task_type = str(result_artifact.get("task_type") or "").strip()
    if dispatch_id <= 0:
        dispatch_id = int(result_artifact.get("dispatch_id") or 0)
    if not queue_state:
        queue_state = str(result_artifact.get("queue_state") or "").strip()
    if not isinstance(control, dict):
        cancel_requested = bool(result_artifact.get("cancel_requested"))
    result_status = str(getattr(getattr(result, "status", None), "value", "") or "").strip()
    if not isinstance(control, dict):
        queue_state = lifecycle_runtime_service.normalized_queue_state(
            queue_state=queue_state,
            result_status=result_status,
        )
    status_text = resolve_status_text(result_status=result_status, queue_state=queue_state)
    artifact = status_artifact(
        result_artifact=result_artifact,
        task_type=task_type,
        dispatch_id=dispatch_id,
        queue_state=queue_state,
        cancel_requested=cancel_requested,
        provider=queue_provider,
    )
    payload: dict[str, Any] = {
        "task_id": task_id,
        "status": status_text,
        "task_type": task_type,
        "dispatch_id": dispatch_id,
        "queue_state": queue_state,
        "cancel_requested": cancel_requested,
        "runner_pid": runner_pid,
        "queue_source_of_truth": queue_source_of_truth,
        "queue_provider": str(queue_provider or ""),
        "result": result.to_dict() if result is not None else None,
        "control": control,
    }
    if artifact:
        payload["artifact"] = artifact
    if result is not None:
        payload["summary"] = str(getattr(result, "summary", "") or "")
        payload["retry_count"] = int(getattr(result, "retry_count", 0) or 0)
        payload["error"] = str(getattr(result, "error", "") or "")
    return payload


def resolve_status_text(*, result_status: str, queue_state: str) -> str:
    normalized_result = str(result_status or "").strip().lower()
    normalized_queue = str(queue_state or "").strip().lower()
    if lifecycle_runtime_service.is_terminal_background_task_state(
        normalized_queue
    ) and not lifecycle_runtime_service.is_terminal_background_task_state(normalized_result):
        return normalized_queue
    return normalized_result or normalized_queue or "unknown"


def normalize_task_request(
    *,
    task_type: Any,
    payload: dict[str, Any] | None,
    source: str,
    thread_id: str,
    parent_agent_id: str,
    priority: Any,
    metadata: Any,
    task_type_cls: Any,
    priority_cls: Any,
    metadata_cls: Any,
    new_task_id_fn: Any,
    now_fn: Any,
) -> Any:
    resolved_task_type = task_type if isinstance(task_type, task_type_cls) else coerce_task_type(task_type, task_type_cls)
    resolved_priority = priority if isinstance(priority, priority_cls) else coerce_priority(priority, priority_cls)
    resolved_metadata = metadata if isinstance(metadata, metadata_cls) else metadata_cls.from_dict(metadata)
    task_id_prefix = "bg"
    task_type_value = str(getattr(resolved_task_type, "value", resolved_task_type) or "").strip().lower()
    if task_type_value == "benchmark":
        task_id_prefix = "bg_benchmark"
    elif task_type_value == "smoke":
        task_id_prefix = "bg_smoke"
    elif task_type_value == "teammate":
        task_id_prefix = "bg_teammate"
    return {
        "task_id": new_task_id_fn(task_id_prefix),
        "task_type": resolved_task_type,
        "source": str(source or "runtime"),
        "created_at": now_fn(),
        "thread_id": str(thread_id or ""),
        "parent_agent_id": str(parent_agent_id or ""),
        "priority": resolved_priority,
        "payload": dict(payload or {}),
        "metadata": resolved_metadata,
    }


def coerce_task_type(value: Any, task_type_cls: Any) -> Any:
    try:
        return task_type_cls(str(value or "").strip().lower() or task_type_cls.BENCHMARK.value)
    except ValueError:
        return task_type_cls.BENCHMARK


def coerce_priority(value: Any, priority_cls: Any) -> Any:
    try:
        return priority_cls(str(value or "").strip().lower() or priority_cls.LOW.value)
    except ValueError:
        return priority_cls.LOW


def queued_artifact(*, task_type: str, dispatch_id: int, provider: str) -> dict[str, Any]:
    return lifecycle_runtime_service.normalize_artifact(
        artifact={},
        task_type=task_type,
        dispatch_id=int(dispatch_id or 1),
        queue_state="queued",
        cancel_requested=False,
        provider=provider,
    )


def status_artifact(
    *,
    result_artifact: dict[str, Any] | None,
    task_type: str,
    dispatch_id: int,
    queue_state: str,
    cancel_requested: bool,
    provider: str,
) -> dict[str, Any]:
    return lifecycle_runtime_service.normalize_artifact(
        artifact=result_artifact,
        task_type=task_type,
        dispatch_id=dispatch_id,
        queue_state=queue_state,
        cancel_requested=cancel_requested,
        provider=provider,
    )


def stale_requeue_artifact(
    *,
    current_artifact: dict[str, Any] | None,
    item: dict[str, Any],
    recovered_at: str,
    provider: str,
) -> dict[str, Any]:
    artifact = dict(current_artifact or {})
    stale_requeue_count = int(artifact.get("stale_requeue_count") or 0) + 1
    artifact["stale_requeued"] = True
    artifact["stale_requeued_at"] = recovered_at
    artifact["stale_requeue_reason"] = "stale_running_dispatch"
    artifact["stale_requeue_count"] = stale_requeue_count
    artifact["last_stale_runner_pid"] = int(item.get("runner_pid") or 0)
    artifact["last_stale_runner_token"] = str(item.get("runner_token") or "").strip()
    artifact["last_stale_dispatch_updated_at"] = str(item.get("updated_at") or "").strip()
    artifact["last_stale_age_seconds"] = float(item.get("stale_age_seconds") or 0.0)
    return lifecycle_runtime_service.normalize_artifact(
        artifact=artifact,
        queue_state="queued",
        cancel_requested=False,
        provider=provider,
    )

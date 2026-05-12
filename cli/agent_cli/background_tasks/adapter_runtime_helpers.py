from __future__ import annotations

from typing import Any, Callable, Dict

from . import lifecycle_runtime as lifecycle_runtime_service


def enqueue(
    *,
    storage: Any,
    queue: Any,
    envelope: Any,
    queued_artifact_fn: Callable[..., Dict[str, Any]],
    task_result_cls: Any,
    queued_status: Any,
    queue_handle_cls: Any,
) -> Any:
    existing_result = storage.get_result(envelope.task_id)
    retry_count = int(getattr(existing_result, "retry_count", 0) or 0)
    storage.upsert_envelope(envelope, queue_state="queued")
    storage.upsert_result(
        task_result_cls(
            task_id=envelope.task_id,
            status=queued_status,
            summary="queued",
            artifact=queued_artifact_fn(envelope, provider=queue.provider_label),
            retry_count=retry_count,
        )
    )
    handle = queue.enqueue(envelope)
    if isinstance(handle, queue_handle_cls):
        return handle
    return queue_handle_cls(task_id=envelope.task_id, status="queued", provider=queue.provider_label)


def submit(
    *,
    task_type: Any,
    payload: Dict[str, Any] | None,
    source: str,
    thread_id: str,
    parent_agent_id: str,
    metadata: Any,
    normalize_task_request_fn: Callable[..., Any],
    enqueue_fn: Callable[[Any], Any],
) -> Any:
    envelope = normalize_task_request_fn(
        task_type=task_type,
        payload=payload,
        source=source,
        thread_id=thread_id,
        parent_agent_id=parent_agent_id,
        metadata=metadata,
    )
    enqueue_fn(envelope)
    return envelope


def submit_policy_helper_regression(
    *,
    payload: Dict[str, Any] | None,
    argv: list[str] | tuple[str, ...] | str | None,
    source: str,
    thread_id: str,
    parent_agent_id: str,
    metadata: Any,
    smoke_task_type: Any,
    build_policy_helper_regression_payload_fn: Callable[..., Dict[str, Any]],
    submit_fn: Callable[..., Any],
) -> Any:
    return submit_fn(
        task_type=smoke_task_type,
        payload=build_policy_helper_regression_payload_fn(payload=payload, argv=argv),
        source=source,
        thread_id=thread_id,
        parent_agent_id=parent_agent_id,
        metadata=metadata,
    )


def mark_running(
    *,
    storage: Any,
    task_id: str,
    now_fn: Callable[[], str],
    task_result_cls: Any,
    running_status: Any,
    status_artifact_fn: Callable[..., Dict[str, Any]],
    queue_provider: str,
) -> None:
    current = storage.get_result(task_id)
    control = _sync_control_state(storage=storage, task_id=task_id, queue_state="running")
    storage.upsert_result(
        task_result_cls(
            task_id=task_id,
            status=running_status,
            started_at=str(getattr(current, "started_at", "") or now_fn()),
            summary="running",
            artifact=_normalized_transition_artifact(
                current=current,
                control=control,
                queue_state="running",
                cancel_requested=bool((control or {}).get("cancel_requested")),
                provider=queue_provider,
                status_artifact_fn=status_artifact_fn,
            ),
            retry_count=int(getattr(current, "retry_count", 0) or 0),
        )
    )


def mark_completed(
    *,
    storage: Any,
    task_id: str,
    now_fn: Callable[[], str],
    task_result_cls: Any,
    completed_status: Any,
    status_artifact_fn: Callable[..., Dict[str, Any]],
    queue_provider: str,
    summary: str = "",
    artifact: Dict[str, Any] | None = None,
) -> Any:
    current = storage.get_result(task_id)
    control = _sync_control_state(storage=storage, task_id=task_id, queue_state="completed")
    artifact_seed = dict(getattr(current, "artifact", {}) or {})
    artifact_seed.update(dict(artifact or {}))
    result = task_result_cls(
        task_id=task_id,
        status=completed_status,
        started_at=str(getattr(current, "started_at", "") or ""),
        finished_at=now_fn(),
        summary=summary,
        artifact=_normalized_transition_artifact(
            current=current,
            control=control,
            queue_state="completed",
            cancel_requested=False,
            provider=queue_provider,
            artifact_seed=artifact_seed,
            status_artifact_fn=status_artifact_fn,
        ),
        retry_count=int(getattr(current, "retry_count", 0) or 0),
    )
    storage.upsert_result(result)
    return result


def mark_failed(
    *,
    storage: Any,
    task_id: str,
    now_fn: Callable[[], str],
    task_result_cls: Any,
    failed_status: Any,
    status_artifact_fn: Callable[..., Dict[str, Any]],
    queue_provider: str,
    error: str,
    retry_count: int = 0,
) -> Any:
    current = storage.get_result(task_id)
    control = _sync_control_state(storage=storage, task_id=task_id, queue_state="failed")
    next_retry_count = max(int(retry_count or 0), int(getattr(current, "retry_count", 0) or 0))
    result = task_result_cls(
        task_id=task_id,
        status=failed_status,
        started_at=str(getattr(current, "started_at", "") or ""),
        finished_at=now_fn(),
        error=error,
        retry_count=next_retry_count,
        summary="failed",
        artifact=_normalized_transition_artifact(
            current=current,
            control=control,
            queue_state="failed",
            cancel_requested=False,
            provider=queue_provider,
            status_artifact_fn=status_artifact_fn,
        ),
    )
    storage.upsert_result(result)
    return result


def get_status(
    *,
    storage: Any,
    task_id: str,
    queue_source_of_truth: str,
    queue_provider_label: str,
    reconcile_terminal_control_fn: Callable[..., Dict[str, Any] | None],
    build_status_payload_fn: Callable[..., Dict[str, Any]],
    lifecycle_visibility_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> Dict[str, Any] | None:
    result = storage.get_result(task_id)
    control = storage.control_snapshot(task_id)
    control = reconcile_terminal_control_fn(task_id, result=result, control=control)
    if result is None and control is None:
        return None
    payload = build_status_payload_fn(
        task_id=task_id,
        result=result,
        control=control if isinstance(control, dict) else None,
        queue_source_of_truth=queue_source_of_truth,
        queue_provider=queue_provider_label,
    )
    payload["lifecycle"] = lifecycle_visibility_fn(payload)
    return payload


def apply_staged_changes(*, task_id: str, apply_fn: Callable[..., Any], get_status_fn: Callable[[str], Dict[str, Any] | None], storage: Any) -> Dict[str, Any] | None:
    result = apply_fn(task_id, storage=storage)
    if result is None:
        return None
    return get_status_fn(task_id)


def reject_staged_changes(*, task_id: str, reject_fn: Callable[..., Any], get_status_fn: Callable[[str], Dict[str, Any] | None], storage: Any) -> Dict[str, Any] | None:
    result = reject_fn(task_id, storage=storage)
    if result is None:
        return None
    return get_status_fn(task_id)


def _sync_control_state(*, storage: Any, task_id: str, queue_state: str) -> Dict[str, Any] | None:
    control = storage.control_snapshot(task_id)
    if not isinstance(control, dict):
        return None
    normalized_queue_state = str(queue_state or "").strip().lower()
    if normalized_queue_state == "running":
        envelope = storage.get_envelope(task_id)
        if envelope is None:
            return control
        storage.upsert_envelope(
            envelope,
            queue_state="running",
            cancel_requested=bool(control.get("cancel_requested")),
            runner_pid=int(control.get("runner_pid") or 0),
            runner_token=str(control.get("runner_token") or ""),
        )
    elif lifecycle_runtime_service.is_terminal_background_task_state(normalized_queue_state):
        dispatch_id = int(control.get("dispatch_id") or 0)
        if dispatch_id <= 0:
            return control
        storage.complete_dispatch(
            task_id,
            dispatch_id=dispatch_id,
            queue_state=normalized_queue_state,
            runner_token=str(control.get("runner_token") or ""),
        )
    refreshed = storage.control_snapshot(task_id)
    return refreshed if isinstance(refreshed, dict) else control


def _control_task_type(control: Dict[str, Any] | None) -> str:
    if not isinstance(control, dict):
        return ""
    envelope = control.get("envelope")
    if isinstance(envelope, dict):
        value = str(envelope.get("task_type") or "").strip()
        if value:
            return value
    return str(control.get("task_type") or "").strip()


def _control_dispatch_id(control: Dict[str, Any] | None, artifact_seed: Dict[str, Any]) -> int:
    if isinstance(control, dict):
        dispatch_id = int(control.get("dispatch_id") or 0)
        if dispatch_id > 0:
            return dispatch_id
    return int(artifact_seed.get("dispatch_id") or 0)


def _normalized_transition_artifact(
    *,
    current: Any,
    control: Dict[str, Any] | None,
    queue_state: str,
    cancel_requested: bool,
    provider: str,
    status_artifact_fn: Callable[..., Dict[str, Any]],
    artifact_seed: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    seeded_artifact = dict(getattr(current, "artifact", {}) or {})
    if artifact_seed:
        seeded_artifact.update(dict(artifact_seed))
    result_like = type("ResultLike", (), {"artifact": seeded_artifact})()
    return status_artifact_fn(
        result_like,
        task_type=_control_task_type(control) or str(seeded_artifact.get("task_type") or ""),
        dispatch_id=_control_dispatch_id(control, seeded_artifact),
        queue_state=str((control or {}).get("queue_state") or queue_state),
        cancel_requested=cancel_requested,
        provider=provider,
    )

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from . import adapter_helpers as adapter_helpers_service
from . import adapter_lifecycle_runtime as adapter_lifecycle_runtime_service
from . import adapter_runtime_helpers as adapter_runtime_helpers_service
from . import adapter_runtime as adapter_runtime_service
from . import adapter_status_runtime as adapter_status_runtime_service
from .config import BackgroundTasksConfig
from .models import (
    BackgroundTaskPriority,
    BackgroundTaskStatus,
    BackgroundTaskType,
    QueueHandle,
    TaskEnvelope,
    TaskMetadata,
    TaskResult,
    new_task_id,
    utc_now_iso,
)
from .queue import BackgroundTaskQueue
from .storage import BackgroundTaskStorage
from .tasks import apply_staged_teammate_result, execute_background_task, reject_staged_teammate_result
from .worker_state import background_worker_status

DEFAULT_STALE_DISPATCH_AGE_SECONDS = 30.0
POLICY_HELPER_REGRESSION_PRESET = "policy_helper_regression"


@dataclass(slots=True)
class BackgroundTaskAdapter:
    config: BackgroundTasksConfig
    storage: BackgroundTaskStorage
    queue: BackgroundTaskQueue
    queue_source_of_truth: str = "dispatch"

    def enqueue(self, envelope: TaskEnvelope) -> QueueHandle:
        return adapter_runtime_helpers_service.enqueue(
            storage=self.storage,
            queue=self.queue,
            envelope=envelope,
            queued_artifact_fn=_queued_artifact,
            task_result_cls=TaskResult,
            queued_status=BackgroundTaskStatus.QUEUED,
            queue_handle_cls=QueueHandle,
        )

    def submit(
        self,
        *,
        task_type: BackgroundTaskType,
        payload: Dict[str, Any] | None = None,
        source: str = "runtime",
        thread_id: str = "",
        parent_agent_id: str = "",
        metadata: TaskMetadata | None = None,
    ) -> TaskEnvelope:
        return adapter_runtime_helpers_service.submit(
            task_type=task_type,
            payload=payload,
            source=source,
            thread_id=thread_id,
            parent_agent_id=parent_agent_id,
            metadata=metadata,
            normalize_task_request_fn=normalize_task_request,
            enqueue_fn=self.enqueue,
        )

    def submit_policy_helper_regression(
        self,
        *,
        payload: Dict[str, Any] | None = None,
        argv: list[str] | tuple[str, ...] | str | None = None,
        source: str = "runtime",
        thread_id: str = "",
        parent_agent_id: str = "",
        metadata: TaskMetadata | None = None,
    ) -> TaskEnvelope:
        return adapter_runtime_helpers_service.submit_policy_helper_regression(
            payload=payload,
            argv=argv,
            source=source,
            thread_id=thread_id,
            parent_agent_id=parent_agent_id,
            metadata=metadata,
            smoke_task_type=BackgroundTaskType.SMOKE,
            build_policy_helper_regression_payload_fn=build_policy_helper_regression_payload,
            submit_fn=self.submit,
        )

    def mark_running(self, task_id: str) -> None:
        adapter_runtime_helpers_service.mark_running(
            storage=self.storage,
            task_id=task_id,
            now_fn=utc_now_iso,
            task_result_cls=TaskResult,
            running_status=BackgroundTaskStatus.RUNNING,
            status_artifact_fn=_status_artifact,
            queue_provider=self.queue.provider_label,
        )

    def mark_completed(
        self,
        task_id: str,
        *,
        summary: str = "",
        artifact: Dict[str, Any] | None = None,
    ) -> TaskResult:
        return adapter_runtime_helpers_service.mark_completed(
            storage=self.storage,
            task_id=task_id,
            now_fn=utc_now_iso,
            task_result_cls=TaskResult,
            completed_status=BackgroundTaskStatus.COMPLETED,
            status_artifact_fn=_status_artifact,
            queue_provider=self.queue.provider_label,
            summary=summary,
            artifact=artifact,
        )

    def mark_failed(self, task_id: str, *, error: str, retry_count: int = 0) -> TaskResult:
        return adapter_runtime_helpers_service.mark_failed(
            storage=self.storage,
            task_id=task_id,
            now_fn=utc_now_iso,
            task_result_cls=TaskResult,
            failed_status=BackgroundTaskStatus.FAILED,
            status_artifact_fn=_status_artifact,
            queue_provider=self.queue.provider_label,
            error=error,
            retry_count=retry_count,
        )

    def get_result(self, task_id: str) -> TaskResult | None:
        return self.storage.get_result(task_id)

    def get_envelope(self, task_id: str) -> TaskEnvelope | None:
        return self.storage.get_envelope(task_id)

    def get_status(self, task_id: str) -> Dict[str, Any] | None:
        return adapter_runtime_helpers_service.get_status(
            storage=self.storage,
            task_id=task_id,
            queue_source_of_truth=self.queue_source_of_truth,
            queue_provider_label=self.queue.provider_label,
            reconcile_terminal_control_fn=self._reconcile_terminal_control,
            build_status_payload_fn=adapter_runtime_service.build_status_payload,
            lifecycle_visibility_fn=_lifecycle_visibility,
        )

    def _reconcile_terminal_control(
        self,
        task_id: str,
        *,
        result: TaskResult | None,
        control: Dict[str, Any] | None,
    ) -> Dict[str, Any] | None:
        return adapter_lifecycle_runtime_service.reconcile_terminal_control(storage=self.storage, task_id=task_id, result=result, control=control if isinstance(control, dict) else None)

    def cancel(self, task_id: str) -> Dict[str, Any] | None:
        return adapter_lifecycle_runtime_service.cancel_task(
            storage=self.storage,
            task_id=task_id,
            provider_label=self.queue.provider_label,
            get_status_fn=self.get_status,
            status_artifact_fn=_status_artifact,
            now_fn=utc_now_iso,
        )

    def retry(self, task_id: str) -> Dict[str, Any] | None:
        return adapter_lifecycle_runtime_service.retry_task(
            storage=self.storage,
            task_id=task_id,
            provider_label=self.queue.provider_label,
            get_status_fn=self.get_status,
            get_envelope_fn=self.get_envelope,
            enqueue_fn=self.enqueue,
            queued_artifact_fn=_queued_artifact,
            now_fn=utc_now_iso,
            task_result_cls=TaskResult,
            task_envelope_cls=TaskEnvelope,
        )

    def apply_staged_changes(self, task_id: str) -> Dict[str, Any] | None:
        return adapter_runtime_helpers_service.apply_staged_changes(
            task_id=task_id,
            apply_fn=apply_staged_teammate_result,
            get_status_fn=self.get_status,
            storage=self.storage,
        )

    def reject_staged_changes(self, task_id: str) -> Dict[str, Any] | None:
        return adapter_runtime_helpers_service.reject_staged_changes(
            task_id=task_id,
            reject_fn=reject_staged_teammate_result,
            get_status_fn=self.get_status,
            storage=self.storage,
        )

    def cleanup_stale_tasks(self, *, max_age_seconds: float = DEFAULT_STALE_DISPATCH_AGE_SECONDS) -> list[Dict[str, Any]]:
        return adapter_lifecycle_runtime_service.cleanup_stale_tasks(storage=self.storage, provider_label=self.queue.provider_label, max_age_seconds=max_age_seconds, now_fn=utc_now_iso)

    def run_pending(self, *, max_jobs: int = 1, perform_maintenance: bool = True) -> int:
        return adapter_lifecycle_runtime_service.run_pending(
            queue=self.queue,
            storage=self.storage,
            max_jobs=max_jobs,
            perform_maintenance=perform_maintenance,
            cleanup_stale_tasks_fn=self.cleanup_stale_tasks,
            new_task_id_fn=new_task_id,
            execute_background_task_fn=execute_background_task,
        )

    def list_recent(self, *, limit: int = 20) -> list[TaskResult]:
        return self.storage.list_recent(limit=limit)

    def worker_status(self) -> Dict[str, Any]:
        return background_worker_status(self.config, queue_provider=self.queue.provider_label)


def build_background_task_adapter(
    *,
    cwd: str | Path | None = None,
    config: BackgroundTasksConfig | None = None,
    force_enable: bool = False,
) -> BackgroundTaskAdapter:
    return adapter_helpers_service.build_background_task_adapter(cwd=cwd, config=config, force_enable=force_enable, adapter_cls=BackgroundTaskAdapter)


def normalize_task_request(
    *,
    task_type: BackgroundTaskType | str,
    payload: Dict[str, Any] | None = None,
    source: str = "runtime",
    thread_id: str = "",
    parent_agent_id: str = "",
    priority: BackgroundTaskPriority | str = BackgroundTaskPriority.LOW,
    metadata: TaskMetadata | Dict[str, Any] | None = None,
) -> TaskEnvelope:
    return adapter_helpers_service.normalize_task_request(task_type=task_type, payload=payload, source=source, thread_id=thread_id, parent_agent_id=parent_agent_id, priority=priority, metadata=metadata)


def build_task_envelope(**kwargs: Any) -> TaskEnvelope:
    return normalize_task_request(**kwargs)


def enqueue_background_task(
    *,
    task_type: BackgroundTaskType | str,
    payload: Dict[str, Any] | None = None,
    source: str = "runtime",
    priority: BackgroundTaskPriority | str = BackgroundTaskPriority.LOW,
    metadata: TaskMetadata | Dict[str, Any] | None = None,
    thread_id: str = "",
    parent_agent_id: str = "",
    cwd: str | Path | None = None,
    adapter: BackgroundTaskAdapter | None = None,
    force_enable: bool = False,
) -> QueueHandle:
    return adapter_helpers_service.enqueue_background_task(
        task_type=task_type,
        payload=payload,
        source=source,
        priority=priority,
        metadata=metadata,
        thread_id=thread_id,
        parent_agent_id=parent_agent_id,
        cwd=cwd,
        adapter=adapter,
        force_enable=force_enable,
        build_background_task_adapter_fn=build_background_task_adapter,
        normalize_task_request_fn=normalize_task_request,
    )


def submit_background_task(**kwargs: Any) -> QueueHandle:
    return enqueue_background_task(**kwargs)


def build_policy_helper_regression_payload(
    *,
    payload: Dict[str, Any] | None = None,
    argv: list[str] | tuple[str, ...] | str | None = None,
) -> Dict[str, Any]:
    return adapter_helpers_service.build_policy_helper_regression_payload(payload=payload, argv=argv, preset=POLICY_HELPER_REGRESSION_PRESET)


def enqueue_policy_helper_regression_task(
    *,
    payload: Dict[str, Any] | None = None,
    argv: list[str] | tuple[str, ...] | str | None = None,
    source: str = "runtime",
    priority: BackgroundTaskPriority | str = BackgroundTaskPriority.LOW,
    metadata: TaskMetadata | Dict[str, Any] | None = None,
    thread_id: str = "",
    parent_agent_id: str = "",
    cwd: str | Path | None = None,
    adapter: BackgroundTaskAdapter | None = None,
    force_enable: bool = False,
) -> QueueHandle:
    return adapter_helpers_service.enqueue_policy_helper_regression_task(payload=payload, argv=argv, source=source, priority=priority, metadata=metadata, thread_id=thread_id, parent_agent_id=parent_agent_id, cwd=cwd, adapter=adapter, force_enable=force_enable, enqueue_background_task_fn=enqueue_background_task, smoke_task_type=BackgroundTaskType.SMOKE, build_policy_helper_regression_payload_fn=build_policy_helper_regression_payload)


def _coerce_task_type(value: BackgroundTaskType | str) -> BackgroundTaskType:
    return adapter_runtime_service.coerce_task_type(value, BackgroundTaskType)


def _coerce_priority(value: BackgroundTaskPriority | str) -> BackgroundTaskPriority:
    return adapter_runtime_service.coerce_priority(value, BackgroundTaskPriority)


def _queued_artifact(envelope: TaskEnvelope, *, provider: str) -> Dict[str, Any]:
    return adapter_runtime_service.queued_artifact(task_type=envelope.task_type.value, dispatch_id=int(envelope.dispatch_id or 1), provider=provider)


def _status_artifact(
    result: TaskResult,
    *,
    task_type: str,
    dispatch_id: int,
    queue_state: str,
    cancel_requested: bool,
    provider: str,
) -> Dict[str, Any]:
    return adapter_runtime_service.status_artifact(result_artifact=dict(result.artifact or {}), task_type=task_type, dispatch_id=dispatch_id, queue_state=queue_state, cancel_requested=cancel_requested, provider=provider)


def _lifecycle_visibility(status_payload: Dict[str, Any]) -> Dict[str, Any]:
    return adapter_status_runtime_service.lifecycle_visibility(status_payload)

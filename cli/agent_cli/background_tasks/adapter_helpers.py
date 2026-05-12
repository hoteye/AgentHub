from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict

from . import adapter_runtime as adapter_runtime_service
from .config import BackgroundTasksConfig, read_background_tasks_config
from .models import (
    BackgroundTaskPriority,
    BackgroundTaskType,
    QueueHandle,
    TaskEnvelope,
    TaskMetadata,
    new_task_id,
    utc_now_iso,
)
from .queue import create_queue
from .storage import BackgroundTaskStorage
from .tasks import execute_background_task


def build_background_task_adapter(
    *,
    cwd: str | Path | None = None,
    config: BackgroundTasksConfig | None = None,
    force_enable: bool = False,
    adapter_cls: Callable[..., Any],
) -> Any:
    resolved_config = config or read_background_tasks_config(cwd=cwd)
    if force_enable and not resolved_config.enabled:
        resolved_config = BackgroundTasksConfig(
            enabled=True,
            provider=resolved_config.provider,
            huey=resolved_config.huey,
            source_paths=resolved_config.source_paths,
        )
    storage = BackgroundTaskStorage(
        results_dir=resolved_config.huey.results_dir,
        db_path=resolved_config.huey.path,
    )
    queue = create_queue(resolved_config, executor=lambda envelope: execute_background_task(envelope, storage=storage))
    return adapter_cls(
        config=resolved_config,
        storage=storage,
        queue=queue,
    )


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
    return TaskEnvelope(
        **adapter_runtime_service.normalize_task_request(
            task_type=task_type,
            payload=payload,
            source=source,
            thread_id=thread_id,
            parent_agent_id=parent_agent_id,
            priority=priority,
            metadata=metadata,
            task_type_cls=BackgroundTaskType,
            priority_cls=BackgroundTaskPriority,
            metadata_cls=TaskMetadata,
            new_task_id_fn=new_task_id,
            now_fn=utc_now_iso,
        )
    )


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
    adapter: Any | None = None,
    force_enable: bool = False,
    build_background_task_adapter_fn: Callable[..., Any],
    normalize_task_request_fn: Callable[..., TaskEnvelope],
) -> QueueHandle:
    active_adapter = adapter or build_background_task_adapter_fn(cwd=cwd, force_enable=force_enable)
    envelope = normalize_task_request_fn(
        task_type=task_type,
        payload=payload,
        source=source,
        priority=priority,
        metadata=metadata,
        thread_id=thread_id,
        parent_agent_id=parent_agent_id,
    )
    if not active_adapter.config.enabled:
        return QueueHandle(task_id=envelope.task_id, status="disabled", provider=active_adapter.queue.provider_label)
    return active_adapter.enqueue(envelope)


def build_policy_helper_regression_payload(
    *,
    payload: Dict[str, Any] | None = None,
    argv: list[str] | tuple[str, ...] | str | None = None,
    preset: str,
) -> Dict[str, Any]:
    merged = dict(payload or {})
    merged["preset"] = preset
    if argv is not None:
        if isinstance(argv, (list, tuple)):
            merged["argv"] = [str(item) for item in argv]
        else:
            merged["argv"] = str(argv)
    return merged


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
    adapter: Any | None = None,
    force_enable: bool = False,
    enqueue_background_task_fn: Callable[..., QueueHandle],
    smoke_task_type: BackgroundTaskType,
    build_policy_helper_regression_payload_fn: Callable[..., Dict[str, Any]],
) -> QueueHandle:
    return enqueue_background_task_fn(
        task_type=smoke_task_type,
        payload=build_policy_helper_regression_payload_fn(payload=payload, argv=argv),
        source=source,
        priority=priority,
        metadata=metadata,
        thread_id=thread_id,
        parent_agent_id=parent_agent_id,
        cwd=cwd,
        adapter=adapter,
        force_enable=force_enable,
    )

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from .config import BackgroundTasksConfig, HueyConfig
from .models import QueueHandle, TaskEnvelope, TaskResult

try:
    from huey import SqliteHuey  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    SqliteHuey = None  # type: ignore


TaskExecutor = Callable[[TaskEnvelope], TaskResult]


class BackgroundTaskQueue(Protocol):
    @property
    def provider_label(self) -> str:
        ...

    @property
    def immediate(self) -> bool:
        ...

    def enqueue(self, envelope: TaskEnvelope | dict[str, Any]) -> QueueHandle:
        ...

    def run_pending(self, *, max_jobs: int = 1) -> int:
        ...

    def huey_instance(self) -> Any:
        ...


@dataclass(slots=True)
class InProcessQueue:
    executor: TaskExecutor | None = None
    provider_label: str = "inprocess"
    immediate: bool = True

    def enqueue(self, envelope: TaskEnvelope | dict[str, Any]) -> QueueHandle:
        task = _coerce_envelope(envelope)
        if self.executor is not None:
            result = self.executor(task)
            return QueueHandle(
                task_id=task.task_id,
                status=result.status.value,
                job_id=task.task_id,
                provider=self.provider_label,
            )
        return QueueHandle(task_id=task.task_id, status="queued", job_id=task.task_id, provider=self.provider_label)

    def run_pending(self, *, max_jobs: int = 1) -> int:
        _ = max_jobs
        return 0

    def huey_instance(self) -> Any:
        return None


class HueyQueue:
    def __init__(self, config: BackgroundTasksConfig, *, executor: TaskExecutor | None = None) -> None:
        self._config = config
        self._executor = executor
        self._huey = None
        self._task_fn = None
        self.provider_label = "huey"
        self.immediate = False

        if SqliteHuey is None:
            self.provider_label = "huey-unavailable"
            return

        huey_path = str(config.huey.path)
        Path(huey_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._huey = SqliteHuey(
            name="agenthub_background",
            filename=huey_path,
            immediate=bool(config.huey.immediate),
        )

        @self._huey.task()
        def _runner(envelope_dict: dict[str, Any]) -> dict[str, Any]:
            envelope = TaskEnvelope.from_dict(envelope_dict)
            if self._executor is None:
                return {"task_id": envelope.task_id, "status": "queued"}
            result = self._executor(envelope)
            return result.to_dict()

        self._task_fn = _runner

    def enqueue(self, envelope: TaskEnvelope | dict[str, Any]) -> QueueHandle:
        task = _coerce_envelope(envelope)
        # Dispatch storage is the business queue source of truth.
        # Keep Huey as a provider/health dependency but do not enqueue
        # business tasks into Huey's internal task table here.
        if self._task_fn is None:
            return QueueHandle(task_id=task.task_id, status="queued", job_id=task.task_id, provider=self.provider_label)
        return QueueHandle(
            task_id=task.task_id,
            status="queued",
            job_id=task.task_id,
            provider=self.provider_label,
        )

    def run_pending(self, *, max_jobs: int = 1) -> int:
        _ = max_jobs
        # Huey queue execution happens in external consumer process.
        return 0

    def huey_instance(self) -> Any:
        return self._huey


def create_queue(
    config: BackgroundTasksConfig | dict[str, Any] | None = None,
    *,
    executor: TaskExecutor | None = None,
    immediate: bool | None = None,
    sqlite_path: str | Path | None = None,
    results_dir: str | Path | None = None,
) -> BackgroundTaskQueue:
    effective = _coerce_config(config, immediate=immediate, sqlite_path=sqlite_path, results_dir=results_dir)
    if effective.provider != "huey":
        return InProcessQueue(executor=executor, provider_label=f"inprocess:{effective.provider}", immediate=True)
    if effective.huey.immediate:
        return InProcessQueue(executor=executor, provider_label="huey-immediate", immediate=True)
    return HueyQueue(effective, executor=executor)


def build_queue(
    config: BackgroundTasksConfig | dict[str, Any] | None = None,
    *,
    executor: TaskExecutor | None = None,
    immediate: bool | None = None,
    sqlite_path: str | Path | None = None,
    results_dir: str | Path | None = None,
) -> BackgroundTaskQueue:
    return create_queue(
        config,
        executor=executor,
        immediate=immediate,
        sqlite_path=sqlite_path,
        results_dir=results_dir,
    )


def huey_available() -> bool:
    return SqliteHuey is not None


def _coerce_envelope(envelope: TaskEnvelope | dict[str, Any]) -> TaskEnvelope:
    if isinstance(envelope, TaskEnvelope):
        return envelope
    return TaskEnvelope.from_dict(envelope if isinstance(envelope, dict) else {})


def _coerce_config(
    config: BackgroundTasksConfig | dict[str, Any] | None,
    *,
    immediate: bool | None = None,
    sqlite_path: str | Path | None = None,
    results_dir: str | Path | None = None,
) -> BackgroundTasksConfig:
    if isinstance(config, BackgroundTasksConfig):
        base = config
    else:
        payload = config if isinstance(config, dict) else {}
        huey_payload = payload.get("huey")
        nested_payload = payload.get("background_tasks")
        if isinstance(nested_payload, dict):
            enabled = bool(nested_payload.get("enabled", payload.get("enabled", False)))
            provider = str(nested_payload.get("provider") or payload.get("provider") or "huey").strip() or "huey"
            if isinstance(nested_payload.get("huey"), dict):
                huey_payload = nested_payload.get("huey")
        else:
            enabled = bool(payload.get("enabled", False))
            provider = str(payload.get("provider") or "huey").strip() or "huey"
        huey_mapping = huey_payload if isinstance(huey_payload, dict) else {}
        base = BackgroundTasksConfig(
            enabled=enabled,
            provider=provider,
            huey=HueyConfig(
                backend=str(huey_mapping.get("backend") or "sqlite").strip() or "sqlite",
                path=Path(str(huey_mapping.get("path") or "agenthub_huey.db")),
                results_dir=Path(str(huey_mapping.get("results_dir") or "results")),
                worker_count=max(1, int(huey_mapping.get("worker_count") or 1)),
                immediate=bool(huey_mapping.get("immediate", False)),
            ),
        )

    effective_huey = HueyConfig(
        backend=base.huey.backend,
        path=Path(sqlite_path) if sqlite_path is not None else base.huey.path,
        results_dir=Path(results_dir) if results_dir is not None else base.huey.results_dir,
        worker_count=base.huey.worker_count,
        immediate=base.huey.immediate if immediate is None else bool(immediate),
    )
    return BackgroundTasksConfig(
        enabled=base.enabled,
        provider=base.provider,
        huey=effective_huey,
        source_paths=base.source_paths,
    )

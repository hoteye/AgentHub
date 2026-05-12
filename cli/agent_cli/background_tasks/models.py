from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_task_id(prefix: str = "bg") -> str:
    return f"{prefix}_{uuid4().hex}"


class BackgroundTaskType(str, Enum):
    BENCHMARK = "benchmark"
    SMOKE = "smoke"
    TEAMMATE = "teammate"


class BackgroundTaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BackgroundTaskPriority(str, Enum):
    LOW = "low"


@dataclass(slots=True)
class QueueHandle:
    task_id: str
    status: str = "queued"
    job_id: str = ""
    provider: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "job_id": self.job_id,
            "provider": self.provider,
        }


@dataclass(slots=True)
class TaskMetadata:
    provider_name: str = ""
    model: str = ""
    reason: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "provider_name": self.provider_name,
            "model": self.model,
            "reason": self.reason,
        }
        if self.extra:
            payload["extra"] = dict(self.extra)
        return payload

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "TaskMetadata":
        data = payload if isinstance(payload, dict) else {}
        extra = data.get("extra")
        return cls(
            provider_name=str(data.get("provider_name") or ""),
            model=str(data.get("model") or ""),
            reason=str(data.get("reason") or ""),
            extra=dict(extra) if isinstance(extra, dict) else {},
        )


@dataclass(slots=True)
class TaskEnvelope:
    task_id: str
    task_type: BackgroundTaskType
    dispatch_id: int = 1
    source: str = "runtime"
    created_at: str = field(default_factory=utc_now_iso)
    thread_id: str = ""
    parent_agent_id: str = ""
    priority: BackgroundTaskPriority = BackgroundTaskPriority.LOW
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: TaskMetadata = field(default_factory=TaskMetadata)
    run_id: str = ""
    parent_run_id: str = ""
    tenant_id: str = "default"
    workspace_scope: str = "default"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "dispatch_id": int(self.dispatch_id),
            "source": self.source,
            "created_at": self.created_at,
            "thread_id": self.thread_id,
            "parent_agent_id": self.parent_agent_id,
            "priority": self.priority.value,
            "payload": dict(self.payload),
            "metadata": self.metadata.to_dict(),
            "run_id": self.run_id,
            "parent_run_id": self.parent_run_id,
            "tenant_id": self.tenant_id,
            "workspace_scope": self.workspace_scope,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "TaskEnvelope":
        data = payload if isinstance(payload, dict) else {}
        task_type_text = str(data.get("task_type") or BackgroundTaskType.BENCHMARK.value)
        priority_text = str(data.get("priority") or BackgroundTaskPriority.LOW.value)
        try:
            task_type = BackgroundTaskType(task_type_text)
        except ValueError:
            task_type = BackgroundTaskType.BENCHMARK
        try:
            priority = BackgroundTaskPriority(priority_text)
        except ValueError:
            priority = BackgroundTaskPriority.LOW
        raw_payload = data.get("payload")
        return cls(
            task_id=str(data.get("task_id") or new_task_id()),
            task_type=task_type,
            dispatch_id=max(1, int(data.get("dispatch_id") or 1)),
            source=str(data.get("source") or "runtime"),
            created_at=str(data.get("created_at") or utc_now_iso()),
            thread_id=str(data.get("thread_id") or ""),
            parent_agent_id=str(data.get("parent_agent_id") or ""),
            priority=priority,
            payload=dict(raw_payload) if isinstance(raw_payload, dict) else {},
            metadata=TaskMetadata.from_dict(data.get("metadata")),
            run_id=str(data.get("run_id") or ""),
            parent_run_id=str(data.get("parent_run_id") or ""),
            tenant_id=str(data.get("tenant_id") or "default"),
            workspace_scope=str(data.get("workspace_scope") or "default"),
        )


@dataclass(slots=True)
class TaskResult:
    task_id: str
    status: BackgroundTaskStatus
    started_at: str = ""
    finished_at: str = ""
    summary: str = ""
    artifact: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "summary": self.summary,
            "artifact": dict(self.artifact),
            "error": self.error,
            "retry_count": int(self.retry_count),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "TaskResult":
        data = payload if isinstance(payload, dict) else {}
        status_text = str(data.get("status") or BackgroundTaskStatus.QUEUED.value)
        try:
            status = BackgroundTaskStatus(status_text)
        except ValueError:
            status = BackgroundTaskStatus.QUEUED
        raw_artifact = data.get("artifact")
        retry_count = data.get("retry_count")
        try:
            parsed_retry = int(retry_count) if retry_count is not None else 0
        except (TypeError, ValueError):
            parsed_retry = 0
        return cls(
            task_id=str(data.get("task_id") or ""),
            status=status,
            started_at=str(data.get("started_at") or ""),
            finished_at=str(data.get("finished_at") or ""),
            summary=str(data.get("summary") or ""),
            artifact=dict(raw_artifact) if isinstance(raw_artifact, dict) else {},
            error=str(data.get("error") or ""),
            retry_count=max(0, parsed_retry),
        )

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Mapping


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SubagentTaskStatus(str, Enum):
    QUEUED = "queued"
    STARTED = "started"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    ADOPTED = "adopted"


_TERMINAL_SUBAGENT_TASK_STATUSES = frozenset(
    {
        SubagentTaskStatus.COMPLETED,
        SubagentTaskStatus.FAILED,
        SubagentTaskStatus.TIMED_OUT,
        SubagentTaskStatus.ADOPTED,
    }
)


def is_terminal_subagent_task_status(status: SubagentTaskStatus) -> bool:
    return status in _TERMINAL_SUBAGENT_TASK_STATUSES


@dataclass(frozen=True, slots=True)
class SubagentTaskRecord:
    agent_id: str
    run_id: str
    parent_run_id: str | None = None
    role: str = "subagent"
    status: SubagentTaskStatus = SubagentTaskStatus.QUEUED
    inherited_context: Dict[str, Any] = field(default_factory=dict)
    timeout: int | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def create(
        cls,
        *,
        agent_id: str,
        run_id: str,
        parent_run_id: str | None = None,
        role: str = "subagent",
        inherited_context: Mapping[str, Any] | None = None,
        timeout: int | None = None,
        now_iso: str | None = None,
    ) -> "SubagentTaskRecord":
        now = str(now_iso or utc_now_iso())
        return cls(
            agent_id=str(agent_id),
            run_id=str(run_id),
            parent_run_id=str(parent_run_id) if parent_run_id is not None else None,
            role=str(role or "subagent"),
            status=SubagentTaskStatus.QUEUED,
            inherited_context=dict(inherited_context or {}),
            timeout=timeout,
            created_at=now,
            updated_at=now,
        )

    def with_status(self, status: SubagentTaskStatus, *, now_iso: str | None = None) -> "SubagentTaskRecord":
        return SubagentTaskRecord(
            agent_id=self.agent_id,
            run_id=self.run_id,
            parent_run_id=self.parent_run_id,
            role=self.role,
            status=status,
            inherited_context=dict(self.inherited_context),
            timeout=self.timeout,
            created_at=self.created_at,
            updated_at=str(now_iso or utc_now_iso()),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "run_id": self.run_id,
            "parent_run_id": self.parent_run_id,
            "role": self.role,
            "status": self.status.value,
            "inherited_context": dict(self.inherited_context),
            "timeout": self.timeout,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

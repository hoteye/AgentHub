from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class RunKind(str, Enum):
    TURN = "turn"
    TASK = "task"
    WORKFLOW = "workflow"
    BACKGROUND = "background"
    CUSTOM = "custom"


@dataclass(slots=True)
class RunRecord:
    run_id: str
    kind: RunKind
    status: RunStatus = RunStatus.CREATED
    thread_id: str = ""
    parent_run_id: str = ""
    summary: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    started_at: str = ""
    finished_at: str = ""
    cancelled_at: str = ""
    timed_out_at: str = ""

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.TIMED_OUT,
        }

    @property
    def terminal_state(self) -> str:
        return self.status.value if self.is_terminal else ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "kind": self.kind.value,
            "status": self.status.value,
            "is_terminal": self.is_terminal,
            "terminal_state": self.terminal_state,
            "thread_id": self.thread_id,
            "parent_run_id": self.parent_run_id,
            "summary": self.summary,
            "payload": dict(self.payload or {}),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "cancelled_at": self.cancelled_at,
            "timed_out_at": self.timed_out_at,
        }

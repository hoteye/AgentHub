from __future__ import annotations

from enum import StrEnum
from typing import Any, TypeVar


class ComplexTaskMode(StrEnum):
    SINGLE = "single"
    ASSISTED = "assisted"
    ORCHESTRATED = "orchestrated"


class ComplexTaskRunStatus(StrEnum):
    DRAFT = "draft"
    PLANNING = "planning"
    READY = "ready"
    RUNNING = "running"
    REVIEW = "review"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskCardKind(StrEnum):
    READ_ONLY = "read_only"
    WORKSPACE_MUTATING = "workspace_mutating"
    CONTEXT_SENSITIVE = "context_sensitive"
    LONG_RUNNING = "long_running"


class TaskCardExecutionMode(StrEnum):
    STAY_LOCAL = "stay_local"
    VISIBLE_CHILD_TAB = "visible_child_tab"
    DELEGATED_SUBAGENT = "delegated_subagent"
    DELEGATED_TEAMMATE = "delegated_teammate"
    BACKGROUND_TEAMMATE = "background_teammate"
    BACKGROUND_TASK = "background_task"


class TaskCardExecutorRole(StrEnum):
    ORCHESTRATOR = "orchestrator"
    SCOUT = "scout"
    EXECUTOR = "executor"
    REVIEWER = "reviewer"


class TaskCardStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    QUEUED = "queued"
    RUNNING = "running"
    REVIEW = "review"
    ACCEPTED = "accepted"
    REWORK = "rework"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskCardDependencyStatus(StrEnum):
    PENDING = "pending"
    SATISFIED = "satisfied"
    BLOCKED = "blocked"


class CardResultStatus(StrEnum):
    REPORTED = "reported"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class CardAcceptanceDecision(StrEnum):
    ACCEPT = "accept"
    REWORK = "rework"
    BLOCK = "block"
    REJECT = "reject"


class ExecutionRefKind(StrEnum):
    BACKGROUND_TASK = "background_task"
    DELEGATED_SUBAGENT = "delegated_subagent"
    DELEGATED_TEAMMATE = "delegated_teammate"
    VISIBLE_CHILD_TAB = "visible_child_tab"
    LOCAL = "local"


TaskCardStateStatus = TaskCardStatus
TaskDependencyStatus = TaskCardDependencyStatus


_EnumT = TypeVar("_EnumT", bound=StrEnum)


def parse_enum(enum_cls: type[_EnumT], value: Any, *, field_name: str) -> _EnumT:  # noqa: UP047
    try:
        return enum_cls(str(value or "").strip())
    except ValueError as exc:
        choices = ", ".join(item.value for item in enum_cls)
        raise ValueError(f"invalid {field_name}: {value!r}; expected one of: {choices}") from exc


def coerce_text(value: Any, *, default: str = "") -> str:
    return str(value if value is not None else default)


def coerce_int(value: Any, *, default: int = 0, minimum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(default)
    if minimum is not None:
        parsed = max(minimum, parsed)
    return parsed


def coerce_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def coerce_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def coerce_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def coerce_dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            items.append(dict(item))
    return items

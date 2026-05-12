from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_delegation.events import (
    EVENT_TYPE_BY_STATUS,
    SUBAGENT_ADOPTED,
    SUBAGENT_COMPLETED,
    SUBAGENT_FAILED,
    SUBAGENT_QUEUED,
    SUBAGENT_RUNNING,
    SUBAGENT_STARTED,
    SUBAGENT_TIMED_OUT,
)
from cli.agent_cli.runtime_delegation.models import SubagentTaskStatus, is_terminal_subagent_task_status

_STATUS_BY_EVENT_TYPE = {
    SUBAGENT_QUEUED: SubagentTaskStatus.QUEUED,
    SUBAGENT_STARTED: SubagentTaskStatus.STARTED,
    SUBAGENT_RUNNING: SubagentTaskStatus.RUNNING,
    SUBAGENT_COMPLETED: SubagentTaskStatus.COMPLETED,
    SUBAGENT_FAILED: SubagentTaskStatus.FAILED,
    SUBAGENT_TIMED_OUT: SubagentTaskStatus.TIMED_OUT,
    SUBAGENT_ADOPTED: SubagentTaskStatus.ADOPTED,
}

_STATUS_BY_VALUE = {item.value: item for item in SubagentTaskStatus}


def status_from_event_type(event_type: str | None) -> SubagentTaskStatus:
    normalized = str(event_type or "").strip()
    return _STATUS_BY_EVENT_TYPE.get(normalized, SubagentTaskStatus.QUEUED)


def status_from_event_payload(payload: Any) -> SubagentTaskStatus:
    if not isinstance(payload, dict):
        return SubagentTaskStatus.QUEUED
    event_status = status_from_event_type(payload.get("event_type"))
    raw = str(payload.get("status") or "").strip().lower()
    payload_status = _STATUS_BY_VALUE.get(raw)
    if payload_status is None:
        return event_status
    if event_status is SubagentTaskStatus.QUEUED:
        return payload_status
    return event_status


def event_type_for_status(status: SubagentTaskStatus) -> str:
    return EVENT_TYPE_BY_STATUS.get(status, SUBAGENT_QUEUED)


def terminal_state_from_status(status: SubagentTaskStatus) -> str:
    if not is_terminal_subagent_task_status(status):
        return ""
    return status.value

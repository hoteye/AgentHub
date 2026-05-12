from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping

from cli.agent_cli.runtime_delegation.models import (
    SubagentTaskRecord,
    SubagentTaskStatus,
    is_terminal_subagent_task_status,
    utc_now_iso,
)


SUBAGENT_QUEUED = "subagent.queued"
SUBAGENT_STARTED = "subagent.started"
SUBAGENT_RUNNING = "subagent.running"
SUBAGENT_COMPLETED = "subagent.completed"
SUBAGENT_FAILED = "subagent.failed"
SUBAGENT_TIMED_OUT = "subagent.timed_out"
SUBAGENT_ADOPTED = "subagent.adopted"

EVENT_TYPE_BY_STATUS: dict[SubagentTaskStatus, str] = {
    SubagentTaskStatus.QUEUED: SUBAGENT_QUEUED,
    SubagentTaskStatus.STARTED: SUBAGENT_STARTED,
    SubagentTaskStatus.RUNNING: SUBAGENT_RUNNING,
    SubagentTaskStatus.COMPLETED: SUBAGENT_COMPLETED,
    SubagentTaskStatus.FAILED: SUBAGENT_FAILED,
    SubagentTaskStatus.TIMED_OUT: SUBAGENT_TIMED_OUT,
    SubagentTaskStatus.ADOPTED: SUBAGENT_ADOPTED,
}


@dataclass(frozen=True, slots=True)
class SubagentProtocolEvent:
    event_type: str
    payload: Dict[str, Any]
    emitted_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "payload": dict(self.payload),
            "emitted_at": self.emitted_at,
        }


def _event_payload(
    record: SubagentTaskRecord,
    *,
    status: SubagentTaskStatus,
    emitted_at: str,
    extra: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    payload = record.with_status(status, now_iso=emitted_at).to_dict()
    payload["terminal"] = is_terminal_subagent_task_status(status)
    payload["terminal_state"] = status.value if payload["terminal"] else ""
    payload["adopted"] = status is SubagentTaskStatus.ADOPTED
    if extra:
        payload.update(dict(extra))
    return payload


def subagent_event(
    record: SubagentTaskRecord,
    *,
    status: SubagentTaskStatus,
    extra: Mapping[str, Any] | None = None,
    emitted_at: str | None = None,
) -> SubagentProtocolEvent:
    emitted = str(emitted_at or utc_now_iso())
    return SubagentProtocolEvent(
        event_type=EVENT_TYPE_BY_STATUS.get(status, SUBAGENT_QUEUED),
        payload=_event_payload(record, status=status, emitted_at=emitted, extra=extra),
        emitted_at=emitted,
    )


def subagent_queued(
    record: SubagentTaskRecord,
    *,
    extra: Mapping[str, Any] | None = None,
    emitted_at: str | None = None,
) -> SubagentProtocolEvent:
    return subagent_event(
        record,
        status=SubagentTaskStatus.QUEUED,
        extra=extra,
        emitted_at=emitted_at,
    )


def subagent_started(
    record: SubagentTaskRecord,
    *,
    extra: Mapping[str, Any] | None = None,
    emitted_at: str | None = None,
) -> SubagentProtocolEvent:
    return subagent_event(
        record,
        status=SubagentTaskStatus.STARTED,
        extra=extra,
        emitted_at=emitted_at,
    )


def subagent_running(
    record: SubagentTaskRecord,
    *,
    extra: Mapping[str, Any] | None = None,
    emitted_at: str | None = None,
) -> SubagentProtocolEvent:
    return subagent_event(
        record,
        status=SubagentTaskStatus.RUNNING,
        extra=extra,
        emitted_at=emitted_at,
    )


def subagent_completed(
    record: SubagentTaskRecord,
    *,
    extra: Mapping[str, Any] | None = None,
    emitted_at: str | None = None,
) -> SubagentProtocolEvent:
    return subagent_event(
        record,
        status=SubagentTaskStatus.COMPLETED,
        extra=extra,
        emitted_at=emitted_at,
    )


def subagent_failed(
    record: SubagentTaskRecord,
    *,
    error: str = "",
    extra: Mapping[str, Any] | None = None,
    emitted_at: str | None = None,
) -> SubagentProtocolEvent:
    payload_extra: Dict[str, Any] = dict(extra or {})
    if str(error).strip():
        payload_extra["error"] = str(error)
    return subagent_event(
        record,
        status=SubagentTaskStatus.FAILED,
        extra=payload_extra,
        emitted_at=emitted_at,
    )


def subagent_timed_out(
    record: SubagentTaskRecord,
    *,
    timeout_reason: str = "timeout",
    extra: Mapping[str, Any] | None = None,
    emitted_at: str | None = None,
) -> SubagentProtocolEvent:
    payload_extra: Dict[str, Any] = dict(extra or {})
    payload_extra.setdefault("timeout_reason", str(timeout_reason or "timeout"))
    return subagent_event(
        record,
        status=SubagentTaskStatus.TIMED_OUT,
        extra=payload_extra,
        emitted_at=emitted_at,
    )


def subagent_adopted(
    record: SubagentTaskRecord,
    *,
    extra: Mapping[str, Any] | None = None,
    emitted_at: str | None = None,
) -> SubagentProtocolEvent:
    return subagent_event(
        record,
        status=SubagentTaskStatus.ADOPTED,
        extra=extra,
        emitted_at=emitted_at,
    )

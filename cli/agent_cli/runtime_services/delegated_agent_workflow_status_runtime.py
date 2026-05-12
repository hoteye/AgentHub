from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_delegation import events as subagent_events
from cli.agent_cli.runtime_delegation.models import SubagentTaskRecord, SubagentTaskStatus
from cli.agent_cli.runtime_delegation.protocol import terminal_state_from_status

ACTIVE_WORKFLOW_STATUSES = {"queued", "starting", "running", "closing"}
TERMINAL_WORKFLOW_STATUSES = {"completed", "failed", "closed"}


def normalized_status(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized or "queued"


def normalized_optional_text(value: Any) -> str:
    return str(value or "").strip()


def child_identity_payload(session: Any) -> dict[str, str]:
    agent_id = normalized_optional_text(getattr(session, "agent_id", ""))
    run_id = normalized_optional_text(getattr(session, "protocol_run_id", ""))
    parent_run_id = normalized_optional_text(getattr(session, "protocol_parent_run_id", ""))
    thread_id = normalized_optional_text(getattr(session, "protocol_thread_id", ""))
    return {
        "agent_id": agent_id,
        "run_id": run_id or f"delegated:{agent_id or 'unknown'}",
        "parent_run_id": parent_run_id,
        "thread_id": thread_id,
    }


def subagent_status_for_payload(
    *,
    status: str,
    timeout_hit: bool,
    adopted: bool,
) -> SubagentTaskStatus:
    normalized = normalized_status(status)
    if adopted:
        return SubagentTaskStatus.ADOPTED
    if timeout_hit:
        return SubagentTaskStatus.TIMED_OUT
    if normalized == "queued":
        return SubagentTaskStatus.QUEUED
    if normalized == "starting":
        return SubagentTaskStatus.STARTED
    if normalized in {"running", "closing"}:
        return SubagentTaskStatus.RUNNING
    if normalized == "completed":
        return SubagentTaskStatus.COMPLETED
    if normalized == "failed":
        return SubagentTaskStatus.FAILED
    if normalized == "closed":
        return SubagentTaskStatus.COMPLETED
    return SubagentTaskStatus.QUEUED


def subagent_protocol_payload(
    session: Any,
    *,
    status: str,
    timeout_hit: bool,
    adopted: bool,
    timeout_reason: str,
    error: str,
) -> dict[str, Any]:
    child_identity = child_identity_payload(session)
    run_id = normalized_optional_text(child_identity.get("run_id"))
    parent_run_id = normalized_optional_text(child_identity.get("parent_run_id"))
    thread_id = normalized_optional_text(child_identity.get("thread_id"))
    inferred_run_id = run_id or f"delegated:{normalized_optional_text(getattr(session, 'agent_id', '')) or 'unknown'}"
    inherited_context: dict[str, Any] = {}
    if thread_id:
        inherited_context["thread_id"] = thread_id

    status_enum = subagent_status_for_payload(
        status=status,
        timeout_hit=timeout_hit,
        adopted=adopted,
    )
    record = SubagentTaskRecord.create(
        agent_id=normalized_optional_text(getattr(session, "agent_id", "")),
        run_id=inferred_run_id,
        parent_run_id=parent_run_id or None,
        role=normalized_optional_text(getattr(session, "role", "")) or "subagent",
        inherited_context=inherited_context,
        timeout=getattr(session, "timeout", None),
    )

    if status_enum is SubagentTaskStatus.FAILED:
        event = subagent_events.subagent_failed(record, error=error)
    elif status_enum is SubagentTaskStatus.TIMED_OUT:
        event = subagent_events.subagent_timed_out(record, timeout_reason=timeout_reason or "timeout")
    elif status_enum is SubagentTaskStatus.ADOPTED:
        event = subagent_events.subagent_adopted(record)
    else:
        event = subagent_events.subagent_event(record, status=status_enum)

    terminal_state = terminal_state_from_status(status_enum)
    return {
        "event_type": event.event_type,
        "status": status_enum.value,
        "terminal_state": terminal_state,
        "terminal": bool(terminal_state),
        "adopted": status_enum is SubagentTaskStatus.ADOPTED,
        "task": dict(event.payload),
    }


def resolved_session_status(session: Any) -> str:
    normalized = normalized_status(getattr(session, "status", ""))
    if normalized in TERMINAL_WORKFLOW_STATUSES:
        return normalized
    if getattr(session, "active_input", None) is not None:
        return normalized
    if bool(getattr(session, "queued_inputs", None)):
        return normalized
    terminal_reason = str(getattr(session, "terminal_reason", "") or "").strip().lower()
    if terminal_reason in {"close_requested", "orphan_cleanup", "restore_resolution_failed", "role_override_changed"}:
        return "closed"
    if terminal_reason == "failed" or str(getattr(session, "error", "") or "").strip():
        return "failed"
    if terminal_reason == "completed":
        return "completed"
    if bool(getattr(session, "adopted", False)) or str(getattr(session, "assistant_text", "") or "").strip():
        return "completed"
    return normalized


def completion_state_for_status(
    *,
    status: str,
    adopted: bool,
    completion_policy: str,
) -> str:
    if adopted:
        return "adopted"
    if status in ACTIVE_WORKFLOW_STATUSES:
        return "pending"
    if status == "completed":
        if completion_policy == "must_join":
            return "awaiting_join"
        if completion_policy == "suggest_adopt":
            return "ready_to_adopt"
        return "completed"
    if status == "failed":
        return "failed"
    if status == "closed":
        return "closed"
    return "pending"


def result_state_for_status(
    *,
    status: str,
    completion_state: str,
    adopted: bool,
) -> str:
    if adopted:
        return "adopted"
    if completion_state in {"ready_to_adopt", "awaiting_join"}:
        return "pending_review"
    if status in TERMINAL_WORKFLOW_STATUSES:
        return "returned"
    return "pending"


def next_action_for_state(
    *,
    status: str,
    completion_state: str,
    adopted: bool,
) -> str:
    if status == "completed":
        if completion_state == "adopted":
            return "already_adopted"
        if completion_state == "ready_to_adopt":
            return "review_or_adopt_teammate_result"
        return "wait_agent_to_adopt"
    if status == "failed":
        return "failure_observed" if adopted else "inspect_error_or_retry"
    if status == "closed":
        return "already_adopted" if adopted else "resume_agent_to_continue"
    return "continue_main_thread_or_wait"


def resolved_result_artifact(
    *,
    status: str,
    assistant_text: str,
    error: str,
    current: Any,
) -> dict[str, Any]:
    if isinstance(current, dict):
        normalized_kind = str(current.get("kind") or "").strip().lower()
        if normalized_kind and normalized_kind != "pending":
            return dict(current)
    if status in ACTIVE_WORKFLOW_STATUSES:
        return {"kind": "pending"}
    if status == "failed":
        return {"kind": "failure", "error": error or "delegated agent failed"}
    if assistant_text:
        return {"kind": "text", "text": assistant_text}
    if error:
        return {"kind": "failure", "error": error}
    return {"kind": "empty"}

from __future__ import annotations

from typing import Any, Callable, Dict

from cli.agent_cli.runtime_services import delegated_agent_workflow_runtime_bridge_runtime_helpers
from cli.agent_cli.runtime_services.delegated_agent_workflow_runtime_time_helpers import (
    elapsed_ms,
    now_utc,
    parse_runtime_iso,
)


TIMEOUT_ERROR_HINTS = (
    "timed out",
    "timeout",
    "time out",
    "deadline exceeded",
    "request_timeout",
    "read timeout",
    "connect timeout",
)


def delegated_timeout_metadata(
    session: Any,
    *,
    timeout_error_hints: tuple[str, ...] = TIMEOUT_ERROR_HINTS,
) -> Dict[str, Any]:
    timeout_budget = getattr(session, "timeout", None)
    if timeout_budget in (None, ""):
        timeout_budget = None
    else:
        try:
            timeout_budget = int(timeout_budget)
        except (TypeError, ValueError):
            timeout_budget = None
    for event in list(session.last_tool_events or []):
        payload = getattr(event, "payload", None)
        if not isinstance(payload, dict) or not bool(payload.get("timed_out")):
            continue
        metadata: Dict[str, Any] = {
            "timeout_hit": True,
            "timeout_reason": "tool_timeout",
            "timeout_source": str(getattr(event, "name", "") or "tool"),
        }
        if timeout_budget is not None:
            metadata["timeout_budget_seconds"] = timeout_budget
        return metadata
    error_text = str(session.error or "").strip().lower()
    if error_text and any(hint in error_text for hint in timeout_error_hints):
        metadata = {
            "timeout_hit": True,
            "timeout_reason": "model_timeout" if timeout_budget is not None else "timeout",
            "timeout_source": "planner",
        }
        if timeout_budget is not None:
            metadata["timeout_budget_seconds"] = timeout_budget
        return metadata
    if timeout_budget is not None:
        return {"timeout_budget_seconds": timeout_budget}
    return {}


def delegated_last_wait_metadata(session: Any) -> Dict[str, Any]:
    metadata: Dict[str, Any] = {}
    if str(getattr(session, "last_wait_reason", "") or "").strip():
        metadata["last_wait_reason"] = str(session.last_wait_reason or "").strip()
    if str(getattr(session, "last_wait_decision", "") or "").strip():
        metadata["last_wait_decision"] = str(session.last_wait_decision or "").strip()
    if str(getattr(session, "last_wait_at", "") or "").strip():
        metadata["last_wait_at"] = str(session.last_wait_at or "").strip()
    if getattr(session, "last_wait_blocked_ms", None) not in (None, ""):
        metadata["last_wait_blocked_ms"] = int(session.last_wait_blocked_ms)
    if str(getattr(session, "last_wait_decision", "") or "").strip():
        metadata["last_wait_timed_out"] = bool(getattr(session, "last_wait_timed_out", False))
    return metadata


def delegated_parallel_group(task_shape: Any) -> str:
    normalized = str(task_shape or "").strip().lower()
    if normalized in {"workspace_mutating", "context_sensitive"}:
        return "serial"
    if normalized in {"long_running"}:
        return "long_running"
    return "read_only"


def delegated_parallel_limit(
    parallel_group: Any,
    *,
    max_active: int,
    read_only_max_active: int,
    long_running_max_active: int,
) -> int:
    normalized = str(parallel_group or "").strip().lower()
    if normalized == "serial":
        return 1
    if normalized == "long_running":
        return min(max_active, long_running_max_active)
    return min(max_active, read_only_max_active)


def delegated_resolved_parallel_group(
    *,
    parallel_group: Any,
    task_shape: Any,
    delegated_parallel_group_fn: Callable[[Any], str],
) -> str:
    normalized = str(parallel_group or "").strip().lower()
    if normalized in {"serial", "read_only", "long_running"}:
        return normalized
    fallback = str(delegated_parallel_group_fn(task_shape) or "").strip().lower()
    if fallback in {"serial", "read_only", "long_running"}:
        return fallback
    return "read_only"


def delegated_session_is_active(session: Any) -> bool:
    status = str(session.status or "").strip().lower()
    return bool(session.active_input is not None or status in {"starting", "running", "closing"})


def delegated_result_status(session: Any) -> str:
    status = str(session.status or "").strip().lower()
    if status in {"queued", "starting", "running", "closing", "completed", "failed", "closed"}:
        return status
    if str(session.error or "").strip():
        return "failed"
    if str(session.assistant_text or "").strip():
        return "completed"
    return "queued"


def delegated_completion_policy(
    *,
    role: Any,
    delegation_mode: Any,
    wait_required: Any,
) -> str:
    normalized_role = str(role or "").strip().lower()
    normalized_mode = str(delegation_mode or "").strip().lower()
    if normalized_role == "teammate" and normalized_mode == "background":
        if wait_required is True:
            return "must_join"
        return "suggest_adopt"
    return "silent"


def delegated_background_priority(
    *,
    role: Any,
    delegation_mode: Any,
    wait_required: Any,
) -> str:
    normalized_role = str(role or "").strip().lower()
    normalized_mode = str(delegation_mode or "").strip().lower()
    if normalized_mode != "background":
        return ""
    if normalized_role == "teammate" and wait_required is not True:
        return "low"
    return "normal"


def delegated_completion_state(
    *,
    status: Any,
    adopted: bool,
    completion_policy: str,
) -> str:
    if adopted:
        return "adopted"
    normalized_status = str(status or "").strip().lower() or "queued"
    if normalized_status in {"queued", "starting", "running", "closing"}:
        return "pending"
    if normalized_status == "completed":
        if completion_policy == "must_join":
            return "awaiting_join"
        if completion_policy == "suggest_adopt":
            return "ready_to_adopt"
        return "completed"
    if normalized_status == "failed":
        return "failed"
    if normalized_status == "closed":
        return "closed"
    return "pending"


def delegated_result_state(
    *,
    status: Any,
    completion_state: Any,
    adopted: bool,
) -> str:
    if adopted:
        return "adopted"
    normalized_completion = str(completion_state or "").strip().lower()
    if normalized_completion in {"ready_to_adopt", "awaiting_join"}:
        return "pending_review"
    normalized_status = str(status or "").strip().lower()
    if normalized_status in {"completed", "failed", "closed"}:
        return "returned"
    return "pending"


def delegated_terminal_state(
    *,
    status: Any,
    terminal_reason: Any,
    has_text: bool,
) -> str:
    return delegated_agent_workflow_runtime_bridge_runtime_helpers.delegated_terminal_state_impl(
        status=status,
        terminal_reason=terminal_reason,
        has_text=has_text,
    )


def delegated_result_state_metrics(
    runtime: Any,
    *,
    delegated_result_status_fn: Callable[[Any], str],
    delegated_completion_policy_fn: Callable[..., str],
    delegated_completion_state_fn: Callable[..., str],
    delegated_result_state_fn: Callable[..., str],
) -> Dict[str, int]:
    return delegated_agent_workflow_runtime_bridge_runtime_helpers.delegated_result_state_metrics_impl(
        runtime,
        delegated_result_status_fn=delegated_result_status_fn,
        delegated_completion_policy_fn=delegated_completion_policy_fn,
        delegated_completion_state_fn=delegated_completion_state_fn,
        delegated_result_state_fn=delegated_result_state_fn,
    )


def delegated_scheduler_decision(
    runtime: Any,
    session: Any,
    *,
    max_active: int,
    read_only_max_active: int,
    long_running_max_active: int,
    delegated_parallel_group_fn: Callable[[Any], str],
    delegated_parallel_limit_fn: Callable[..., int],
    delegated_session_is_active_fn: Callable[[Any], bool],
) -> Dict[str, Any]:
    parallel_group = delegated_resolved_parallel_group(
        parallel_group=getattr(session, "parallel_group", ""),
        task_shape=getattr(session, "task_shape", ""),
        delegated_parallel_group_fn=delegated_parallel_group_fn,
    )
    parallel_limit = delegated_parallel_limit_fn(
        parallel_group,
        max_active=max_active,
        read_only_max_active=read_only_max_active,
        long_running_max_active=long_running_max_active,
    )
    session_background_priority = str(getattr(session, "background_priority", "") or "").strip().lower()
    if not session_background_priority:
        session_background_priority = delegated_background_priority(
            role=getattr(session, "role", ""),
            delegation_mode=getattr(session, "delegation_mode", ""),
            wait_required=getattr(session, "wait_required", None),
        )
    active_total = 0
    group_active = 0
    serial_active = False
    higher_priority_background_pending = False
    for other in list(runtime._delegated_agents.values()):
        with other.condition:
            other_is_active = delegated_session_is_active_fn(other)
            other_parallel_group = delegated_resolved_parallel_group(
                parallel_group=getattr(other, "parallel_group", ""),
                task_shape=getattr(other, "task_shape", ""),
                delegated_parallel_group_fn=delegated_parallel_group_fn,
            )
            other_background_priority = str(getattr(other, "background_priority", "") or "").strip().lower()
            if not other_background_priority:
                other_background_priority = delegated_background_priority(
                    role=getattr(other, "role", ""),
                    delegation_mode=getattr(other, "delegation_mode", ""),
                    wait_required=getattr(other, "wait_required", None),
                )
            other_has_pending_work = bool(
                delegated_session_is_active_fn(other)
                or getattr(other, "active_input", None) is not None
                or list(getattr(other, "queued_inputs", []) or [])
            )
        if not other_is_active or other.agent_id == session.agent_id:
            if (
                other.agent_id != session.agent_id
                and session_background_priority == "low"
                and other_has_pending_work
                and str(getattr(other, "delegation_mode", "") or "").strip().lower() == "background"
                and other_background_priority != "low"
            ):
                higher_priority_background_pending = True
            continue
        active_total += 1
        if other_parallel_group == parallel_group:
            group_active += 1
        if other_parallel_group == "serial":
            serial_active = True
        if (
            session_background_priority == "low"
            and str(getattr(other, "delegation_mode", "") or "").strip().lower() == "background"
            and other_background_priority != "low"
        ):
            higher_priority_background_pending = True
    allowed = True
    reason = ""
    if session_background_priority == "low" and higher_priority_background_pending:
        allowed = False
        reason = "deferred_by_higher_priority_background_child"
    elif parallel_group == "serial":
        if active_total > 0:
            allowed = False
            reason = "serialized_by_active_child"
    else:
        if serial_active:
            allowed = False
            reason = "blocked_by_serial_child"
        elif active_total >= max_active:
            allowed = False
            reason = "delegated_active_limit_reached"
        elif group_active >= parallel_limit:
            allowed = False
            reason = (
                "long_running_parallel_limit_reached"
                if parallel_group == "long_running"
                else "read_only_parallel_limit_reached"
            )
    return {
        "allowed": allowed,
        "reason": reason,
        "parallel_group": parallel_group,
        "parallel_limit": parallel_limit,
        "background_priority": session_background_priority,
        "active_total": active_total,
        "group_active": group_active,
    }

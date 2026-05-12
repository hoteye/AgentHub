from __future__ import annotations

from typing import Any, Callable, List


def delegated_goal_text(runtime: Any, session: Any) -> str:
    active_input = runtime._normalized_delegated_queue_item(session.active_input)
    if active_input is not None:
        return str(active_input.get("message") or "")
    for item in list(session.queued_inputs or []):
        normalized = runtime._normalized_delegated_queue_item(item)
        if normalized is not None:
            return str(normalized.get("message") or "")
    if str(session.last_input_text or "").strip():
        return str(session.last_input_text or "").strip()
    return ""


def delegated_result_contract_sources(session: Any) -> List[Any]:
    return [
        *list(session.last_tool_events or []),
        *list(session.last_item_events or []),
        *list(session.last_turn_events or []),
    ]


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


def delegated_parallel_context(
    session: Any,
    *,
    max_active: int,
    read_only_max_active: int,
    long_running_max_active: int,
    delegated_parallel_group_fn: Callable[[Any], str],
    delegated_parallel_limit_fn: Callable[..., int],
) -> tuple[str, int]:
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
    return parallel_group, parallel_limit


def delegated_state_projection(
    session: Any,
    *,
    delegated_completion_policy_fn: Callable[..., str],
    delegated_completion_state_fn: Callable[..., str],
    delegated_result_state_fn: Callable[..., str],
    delegated_terminal_state_fn: Callable[..., str],
) -> tuple[str, str, str, str]:
    completion_policy = delegated_completion_policy_fn(
        role=session.role,
        delegation_mode=session.delegation_mode,
        wait_required=session.wait_required,
    )
    session_status = str(session.status or "").strip() or "queued"
    completion_state = delegated_completion_state_fn(
        status=session_status,
        adopted=bool(session.adopted),
        completion_policy=completion_policy,
    )
    result_state = delegated_result_state_fn(
        status=session_status,
        completion_state=completion_state,
        adopted=bool(session.adopted),
    )
    terminal_state = delegated_terminal_state_fn(
        status=session_status,
        terminal_reason=session.terminal_reason,
        has_text=bool(str(session.assistant_text or "").strip()),
    )
    return completion_policy, completion_state, result_state, terminal_state

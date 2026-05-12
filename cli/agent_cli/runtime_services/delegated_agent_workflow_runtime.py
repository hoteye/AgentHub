from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict

from cli.agent_cli.runtime_services import delegated_agent_workflow_runtime_bridge_helpers as _runtime_bridge


TIMEOUT_ERROR_HINTS = _runtime_bridge.TIMEOUT_ERROR_HINTS


def parse_runtime_iso(value: Any) -> datetime | None:
    return _runtime_bridge.parse_runtime_iso(value)


def now_utc() -> datetime:
    return _runtime_bridge.now_utc()


def elapsed_ms(started_at: Any, ended_at: Any = None) -> int | None:
    started = parse_runtime_iso(started_at)
    if started is None:
        return None
    ended = parse_runtime_iso(ended_at) if ended_at not in (None, "") else now_utc()
    if ended is None:
        ended = now_utc()
    return max(0, int((ended - started).total_seconds() * 1000))


def delegated_timeout_metadata(
    session: Any,
    *,
    timeout_error_hints: tuple[str, ...] = TIMEOUT_ERROR_HINTS,
) -> Dict[str, Any]:
    return _runtime_bridge.delegated_timeout_metadata(
        session,
        timeout_error_hints=timeout_error_hints,
    )


delegated_last_wait_metadata = _runtime_bridge.delegated_last_wait_metadata
delegated_parallel_group = _runtime_bridge.delegated_parallel_group
delegated_parallel_limit = _runtime_bridge.delegated_parallel_limit
delegated_resolved_parallel_group = _runtime_bridge.delegated_resolved_parallel_group
delegated_session_is_active = _runtime_bridge.delegated_session_is_active
delegated_result_status = _runtime_bridge.delegated_result_status
delegated_completion_policy = _runtime_bridge.delegated_completion_policy
delegated_background_priority = _runtime_bridge.delegated_background_priority
delegated_completion_state = _runtime_bridge.delegated_completion_state
delegated_result_state = _runtime_bridge.delegated_result_state
delegated_terminal_state = _runtime_bridge.delegated_terminal_state


def delegated_result_state_metrics(
    runtime: Any,
    *,
    delegated_result_status_fn: Callable[[Any], str],
    delegated_completion_policy_fn: Callable[..., str],
    delegated_completion_state_fn: Callable[..., str],
    delegated_result_state_fn: Callable[..., str],
) -> Dict[str, int]:
    return _runtime_bridge.delegated_result_state_metrics(
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
    return _runtime_bridge.delegated_scheduler_decision(
        runtime,
        session,
        max_active=max_active,
        read_only_max_active=read_only_max_active,
        long_running_max_active=long_running_max_active,
        delegated_parallel_group_fn=delegated_parallel_group_fn,
        delegated_parallel_limit_fn=delegated_parallel_limit_fn,
        delegated_session_is_active_fn=delegated_session_is_active_fn,
    )

from __future__ import annotations

from typing import Any, Callable, Dict, List

from cli.agent_cli.runtime_services import delegated_agent_result_contract_runtime
from cli.agent_cli.runtime_services import delegated_agent_workflow_payload_runtime
from cli.agent_cli.runtime_services import delegated_agent_workflow_runtime_adapters
from cli.agent_cli.runtime_services import delegated_agent_workflow_runtime
from cli.agent_cli.runtime_services import delegated_agent_workflow_render_runtime

_preview_text = delegated_agent_workflow_runtime_adapters._preview_text
_workspace_root = delegated_agent_workflow_runtime_adapters._workspace_root
_looks_like_windows_abs_path = delegated_agent_workflow_runtime_adapters._looks_like_windows_abs_path
_normalize_delegated_path = delegated_agent_workflow_runtime_adapters._normalize_delegated_path
_parse_structured_result = delegated_agent_workflow_runtime_adapters._parse_structured_result
_delegated_result_artifact = delegated_agent_workflow_runtime_adapters._delegated_result_artifact
_delegated_result_confidence = delegated_agent_workflow_runtime_adapters._delegated_result_confidence


_TIMEOUT_ERROR_HINTS = (
    "timed out",
    "timeout",
    "time out",
    "deadline exceeded",
    "request_timeout",
    "read timeout",
    "connect timeout",
)


_parse_runtime_iso = delegated_agent_workflow_runtime_adapters._parse_runtime_iso
_now_utc = delegated_agent_workflow_runtime_adapters._now_utc
_elapsed_ms = delegated_agent_workflow_runtime_adapters._elapsed_ms


def delegated_wall_time_ms(session: Any) -> int | None:
    status = str(session.status or "").strip().lower()
    terminal_ended_at = str(session.updated_at or "").strip() if status in {"completed", "failed", "closed"} else None
    return _elapsed_ms(session.created_at, terminal_ended_at)


def delegated_current_step_wall_time_ms(runtime: Any, session: Any) -> int | None:
    current_step_id = runtime._refresh_delegated_current_step_id(session)
    current_step = runtime._delegated_step(session, current_step_id)
    if not isinstance(current_step, dict):
        return None
    started_at = str(current_step.get("started_at") or "").strip()
    if not started_at:
        return None
    finished_at = str(current_step.get("finished_at") or "").strip()
    if finished_at:
        return _elapsed_ms(started_at, finished_at)
    if session.active_input is None and str(session.status or "").strip().lower() not in {"starting", "running", "closing"}:
        return None
    return _elapsed_ms(started_at)


def delegated_timeout_metadata(session: Any) -> Dict[str, Any]:
    return delegated_agent_workflow_runtime.delegated_timeout_metadata(
        session,
        timeout_error_hints=_TIMEOUT_ERROR_HINTS,
    )


def delegated_last_wait_metadata(session: Any) -> Dict[str, Any]:
    return delegated_agent_workflow_runtime.delegated_last_wait_metadata(session)


delegated_parallel_group = delegated_agent_workflow_runtime_adapters.delegated_parallel_group
delegated_parallel_limit = delegated_agent_workflow_runtime_adapters.delegated_parallel_limit
delegated_session_is_active = delegated_agent_workflow_runtime_adapters.delegated_session_is_active


def delegated_goal_text(runtime: Any, session: Any) -> str:
    return delegated_agent_workflow_payload_runtime.delegated_goal_text(runtime, session)


delegated_result_status = delegated_agent_workflow_runtime_adapters.delegated_result_status


delegated_completion_policy = delegated_agent_workflow_runtime_adapters.delegated_completion_policy
delegated_background_priority = delegated_agent_workflow_runtime_adapters.delegated_background_priority
delegated_completion_state = delegated_agent_workflow_runtime_adapters.delegated_completion_state
delegated_result_state = delegated_agent_workflow_runtime_adapters.delegated_result_state
delegated_terminal_state = delegated_agent_workflow_runtime_adapters.delegated_terminal_state


def delegated_result_state_metrics(runtime: Any) -> Dict[str, int]:
    return delegated_agent_workflow_runtime.delegated_result_state_metrics(
        runtime,
        delegated_result_status_fn=delegated_result_status,
        delegated_completion_policy_fn=delegated_completion_policy,
        delegated_completion_state_fn=delegated_completion_state,
        delegated_result_state_fn=delegated_result_state,
    )


collect_delegated_paths = delegated_agent_workflow_runtime_adapters.collect_delegated_paths


def delegated_result_contract_payload(
    runtime: Any,
    *,
    goal: str,
    status: str,
    assistant_text: str,
    error: str,
    adopted: bool,
    touched_sources: List[Any],
    role: str = "",
    delegation_mode: str = "",
    wait_required: bool | None = None,
) -> Dict[str, Any]:
    return delegated_agent_result_contract_runtime.delegated_result_contract_payload(
        runtime,
        goal=goal,
        status=status,
        assistant_text=assistant_text,
        error=error,
        adopted=adopted,
        touched_sources=touched_sources,
        role=role,
        delegation_mode=delegation_mode,
        wait_required=wait_required,
        delegated_completion_policy_fn=delegated_completion_policy,
        delegated_completion_state_fn=delegated_completion_state,
    )


def delegated_result_contract(runtime: Any, session: Any) -> Dict[str, Any]:
    return delegated_result_contract_payload(
        runtime,
        goal=delegated_goal_text(runtime, session),
        status=delegated_result_status(session),
        assistant_text=str(session.assistant_text or "").strip(),
        error=str(session.error or "").strip(),
        adopted=bool(session.adopted),
        touched_sources=delegated_agent_workflow_payload_runtime.delegated_result_contract_sources(session),
        role=str(session.role or "").strip(),
        delegation_mode=str(session.delegation_mode or "").strip(),
        wait_required=session.wait_required,
    )


def delegated_result_ready(runtime: Any, session: Any) -> bool:
    del runtime
    return delegated_result_status(session) in {"completed", "failed", "closed"}


def delegated_scheduler_decision(
    runtime: Any,
    session: Any,
    *,
    max_active: int,
    read_only_max_active: int,
    long_running_max_active: int,
) -> Dict[str, Any]:
    return delegated_agent_workflow_runtime.delegated_scheduler_decision(
        runtime,
        session,
        max_active=max_active,
        read_only_max_active=read_only_max_active,
        long_running_max_active=long_running_max_active,
        delegated_parallel_group_fn=delegated_parallel_group,
        delegated_parallel_limit_fn=delegated_parallel_limit,
        delegated_session_is_active_fn=delegated_session_is_active,
    )


def notify_delegated_scheduler(runtime: Any) -> None:
    with runtime._delegated_scheduler_condition:
        runtime._delegated_scheduler_condition.notify_all()


def wait_for_delegated_slot(
    runtime: Any,
    session: Any,
    *,
    max_active: int,
    read_only_max_active: int,
    long_running_max_active: int,
    now_iso_fn: Callable[[], str],
    timeout: float = 0.25,
) -> Dict[str, Any]:
    while True:
        with runtime._delegated_scheduler_condition:
            decision = delegated_scheduler_decision(
                runtime,
                session,
                max_active=max_active,
                read_only_max_active=read_only_max_active,
                long_running_max_active=long_running_max_active,
            )
            with session.condition:
                decision = delegated_agent_workflow_render_runtime.apply_scheduler_decision(
                    session,
                    decision,
                    now_iso_fn=now_iso_fn,
                )
            if decision["allowed"]:
                return decision
            runtime._delegated_scheduler_condition.wait(timeout=timeout)


def delegated_agent_payload(
    runtime: Any,
    session: Any,
    *,
    max_active: int,
    read_only_max_active: int,
    long_running_max_active: int,
) -> Dict[str, Any]:
    config = session.config
    parallel_group, parallel_limit = delegated_agent_workflow_payload_runtime.delegated_parallel_context(
        session,
        max_active=max_active,
        read_only_max_active=read_only_max_active,
        long_running_max_active=long_running_max_active,
        delegated_parallel_group_fn=delegated_parallel_group,
        delegated_parallel_limit_fn=delegated_parallel_limit,
    )
    wall_time_ms = delegated_wall_time_ms(session)
    if wall_time_ms is not None:
        pass
    current_step_wall_time_ms = delegated_current_step_wall_time_ms(runtime, session)
    completion_policy, completion_state, result_state, terminal_state = (
        delegated_agent_workflow_payload_runtime.delegated_state_projection(
            session,
            delegated_completion_policy_fn=delegated_completion_policy,
            delegated_completion_state_fn=delegated_completion_state,
            delegated_result_state_fn=delegated_result_state,
            delegated_terminal_state_fn=delegated_terminal_state,
        )
    )
    result_contract = delegated_result_contract(runtime, session)
    payload = delegated_agent_workflow_render_runtime.build_delegated_agent_payload(
        session,
        config=config,
        parallel_group=parallel_group,
        parallel_limit=parallel_limit,
        result_ready=delegated_result_ready(runtime, session),
        wall_time_ms=wall_time_ms,
        current_step_wall_time_ms=current_step_wall_time_ms,
        timeout_metadata=delegated_timeout_metadata(session),
        last_wait_metadata=delegated_last_wait_metadata(session),
        completion_policy=completion_policy,
        completion_state=completion_state,
        result_state=result_state,
        result_state_metrics=delegated_result_state_metrics(runtime),
        terminal_state=terminal_state,
        result_contract=result_contract,
        progress_payload=runtime._delegated_progress_summary(session),
    )
    active_input = runtime._normalized_delegated_queue_item(session.active_input)
    return delegated_agent_workflow_render_runtime.apply_optional_payload_fields(
        payload,
        active_input=active_input,
        assistant_text=str(session.assistant_text or "").strip(),
        error=str(session.error or "").strip(),
    )


def delegated_workflow_payload(
    runtime: Any,
    session: Any,
    *,
    max_active: int,
    read_only_max_active: int,
    long_running_max_active: int,
    steps_limit: int = 8,
    checkpoints_limit: int = 8,
) -> Dict[str, Any]:
    payload = delegated_agent_payload(
        runtime,
        session,
        max_active=max_active,
        read_only_max_active=read_only_max_active,
        long_running_max_active=long_running_max_active,
    )
    progress_payload = runtime._delegated_progress_summary(session, include_history=True)
    return delegated_agent_workflow_render_runtime.build_delegated_workflow_payload(
        payload,
        progress_payload=progress_payload,
        steps_limit=steps_limit,
        checkpoints_limit=checkpoints_limit,
    )


def delegated_workflow_text(payload: Dict[str, Any]) -> str:
    return delegated_agent_workflow_render_runtime.delegated_workflow_text(payload)


def delegated_agent_summary_text(
    runtime: Any,
    session: Any,
    *,
    max_active: int,
    read_only_max_active: int,
    long_running_max_active: int,
) -> str:
    payload = delegated_agent_payload(
        runtime,
        session,
        max_active=max_active,
        read_only_max_active=read_only_max_active,
        long_running_max_active=long_running_max_active,
    )
    return delegated_agent_workflow_render_runtime.delegated_agent_summary_text(payload)

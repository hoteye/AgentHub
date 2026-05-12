from __future__ import annotations

import threading
from typing import Any

from cli.agent_cli.models import (
    CommandExecutionResult,
    ToolEvent,
    generic_tool_call_item_events,
)
from cli.agent_cli.providers.delegation_policy import (
    infer_spawn_agent_metadata,
    normalize_spawn_agent_metadata,
    resolve_spawn_agent_async_mode,
)
from cli.agent_cli.runtime_services import (
    delegated_agent_adoption_runtime,
    delegated_agent_input_runtime,
    delegated_agent_recovery_runtime,
    delegated_agent_session_helpers_runtime,
    delegated_agent_session_operations_runtime,
    delegated_agent_session_payload_runtime,
)


def _runtime_now_iso() -> str:
    return delegated_agent_session_helpers_runtime.runtime_now_iso()


def _sync_delegated_run_record(
    runtime: Any,
    session: Any,
    *,
    forced_status: str | None = None,
    forced_summary: str | None = None,
) -> None:
    delegated_agent_session_operations_runtime.sync_delegated_run_record(
        runtime,
        session,
        forced_status=forced_status,
        forced_summary=forced_summary,
    )


def _resolved_delegation_metadata(
    metadata: dict[str, Any] | None,
    *,
    role: str,
    effective_async_mode: bool,
) -> dict[str, Any]:
    return delegated_agent_session_payload_runtime.resolved_delegation_metadata(
        metadata,
        role=role,
        effective_async_mode=effective_async_mode,
    )


def provider_config_with_model_timeout(config: Any, timeout: int | None) -> Any:
    return delegated_agent_session_operations_runtime.provider_config_with_model_timeout(
        config, timeout
    )


def delegated_planner(
    runtime: Any,
    config: Any,
    *,
    timeout: int | None = None,
    build_planner_fn: Any,
    current_host_platform_fn: Any,
) -> Any:
    return delegated_agent_session_operations_runtime.delegated_planner(
        runtime,
        config,
        timeout=timeout,
        build_planner_fn=build_planner_fn,
        current_host_platform_fn=current_host_platform_fn,
    )


def delegated_agent_id() -> str:
    return delegated_agent_session_helpers_runtime.delegated_agent_id()


def delegated_queue_item(
    message: str,
    *,
    interrupt: bool = False,
    step_id: str = "",
    input_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return delegated_agent_session_helpers_runtime.delegated_queue_item(
        message,
        interrupt=interrupt,
        step_id=step_id,
        input_items=input_items,
    )


def normalized_delegated_queue_item(item: Any) -> dict[str, Any] | None:
    return delegated_agent_session_helpers_runtime.normalized_delegated_queue_item(item)


def delegated_session(runtime: Any, agent_id: str) -> Any:
    normalized = str(agent_id or "").strip()
    if not normalized:
        raise ValueError("agent_id must be a non-empty string")
    with runtime._delegated_agents_lock:
        session = runtime._delegated_agents.get(normalized)
    if session is None:
        raise ValueError(f"unknown delegated agent: {normalized}")
    return session


def start_delegated_agent_worker(runtime: Any, session: Any) -> None:
    with session.condition:
        if session.worker is not None and session.worker.is_alive():
            return
        worker = threading.Thread(
            target=runtime._run_delegated_agent_worker,
            args=(session.agent_id,),
            daemon=True,
            name=f"delegated-agent-{session.agent_id}",
        )
        session.worker = worker
        worker.start()


def create_delegated_agent_session(
    runtime: Any,
    *,
    session_class: Any,
    task_text: str,
    role: str,
    resolution: Any,
    metadata: dict[str, Any] | None = None,
    input_items: list[dict[str, Any]] | None = None,
    fork_context: bool | None = None,
) -> Any:
    return delegated_agent_session_operations_runtime.create_delegated_agent_session(
        runtime,
        session_class=session_class,
        task_text=task_text,
        role=role,
        resolution=resolution,
        metadata=metadata,
        input_items=input_items,
        fork_context=fork_context,
        normalize_spawn_agent_metadata_fn=normalize_spawn_agent_metadata,
        sync_delegated_run_record_fn=_sync_delegated_run_record,
    )


normalized_recover_action = delegated_agent_recovery_runtime.normalized_recover_action
delegated_result_adoptable = delegated_agent_adoption_runtime.delegated_result_adoptable


def agent_workflow_result(
    runtime: Any,
    agent_id: str,
    *,
    steps_limit: int = 8,
    checkpoints_limit: int = 8,
) -> CommandExecutionResult:
    return delegated_agent_session_operations_runtime.agent_workflow_result(
        runtime,
        agent_id,
        steps_limit=steps_limit,
        checkpoints_limit=checkpoints_limit,
        tool_event_factory=ToolEvent,
        command_result_factory=CommandExecutionResult,
        generic_tool_call_item_events_fn=generic_tool_call_item_events,
    )


def recover_agent_result(
    runtime: Any,
    agent_id: str,
    *,
    action: str | None = None,
    step_id: str | None = None,
) -> CommandExecutionResult:
    return delegated_agent_recovery_runtime.recover_agent_result(
        runtime,
        agent_id,
        action=action,
        step_id=step_id,
        now_iso_fn=_runtime_now_iso,
        normalized_recover_action_fn=normalized_recover_action,
        resume_agent_result_fn=resume_agent_result,
        close_agent_result_fn=close_agent_result,
    )


def wait_agent_result(
    runtime: Any,
    agent_id: str,
    *,
    timeout_ms: Any = 30000,
    reason: str | None = None,
    wait_required: Any = None,
) -> CommandExecutionResult:
    return delegated_agent_adoption_runtime.wait_agent_result(
        runtime,
        agent_id,
        timeout_ms=timeout_ms,
        reason=reason,
        wait_required=wait_required,
    )


def wait_agents_result(
    runtime: Any,
    agent_ids: list[str],
    *,
    timeout_ms: Any = 30000,
    reason: str | None = None,
    wait_required: Any = None,
    codex_style: bool = False,
) -> CommandExecutionResult:
    return delegated_agent_adoption_runtime.wait_agents_result(
        runtime,
        agent_ids,
        timeout_ms=timeout_ms,
        reason=reason,
        wait_required=wait_required,
        codex_style=codex_style,
        wait_agent_result_fn=wait_agent_result,
    )


def send_input_result(
    runtime: Any,
    agent_id: str,
    *,
    message: str,
    interrupt: bool = False,
    input_items: list[dict[str, Any]] | None = None,
    codex_style: bool = False,
) -> CommandExecutionResult:
    return delegated_agent_input_runtime.send_input_result(
        runtime,
        agent_id,
        message=message,
        interrupt=interrupt,
        input_items=input_items,
        codex_style=codex_style,
        now_iso_fn=_runtime_now_iso,
    )


def mark_delegated_result_adopted(
    runtime: Any,
    session: Any,
    *,
    now_iso_fn: Any,
) -> None:
    delegated_agent_adoption_runtime.mark_delegated_result_adopted(
        runtime,
        session,
        now_iso_fn=now_iso_fn,
    )


def close_agent_result(
    runtime: Any,
    agent_id: str,
    *,
    codex_style: bool = False,
) -> CommandExecutionResult:
    return delegated_agent_session_operations_runtime.close_agent_result(
        runtime,
        agent_id,
        codex_style=codex_style,
        now_iso_fn=_runtime_now_iso,
        sync_delegated_run_record_fn=_sync_delegated_run_record,
        tool_event_factory=ToolEvent,
        command_result_factory=CommandExecutionResult,
        generic_tool_call_item_events_fn=generic_tool_call_item_events,
    )


def resume_agent_result(
    runtime: Any,
    agent_id: str,
    *,
    codex_style: bool = False,
) -> CommandExecutionResult:
    return delegated_agent_session_operations_runtime.resume_agent_result(
        runtime,
        agent_id,
        codex_style=codex_style,
        now_iso_fn=_runtime_now_iso,
        sync_delegated_run_record_fn=_sync_delegated_run_record,
        tool_event_factory=ToolEvent,
        command_result_factory=CommandExecutionResult,
        generic_tool_call_item_events_fn=generic_tool_call_item_events,
    )


def spawn_agent_result(
    runtime: Any,
    *,
    session_class: Any,
    task: str,
    role: str = "subagent",
    model: str | None = None,
    provider: str | None = None,
    reasoning_effort: str | None = None,
    timeout: Any = None,
    async_mode: bool | None = None,
    reason: str | None = None,
    mode: str | None = None,
    wait_required: Any = None,
    task_shape: str | None = None,
    subagent_type: str | None = None,
    input_items: list[dict[str, Any]] | None = None,
    fork_context: bool | None = None,
    codex_collab_payload: bool = False,
) -> CommandExecutionResult:
    return delegated_agent_session_operations_runtime.spawn_agent_result(
        runtime,
        session_class=session_class,
        task=task,
        role=role,
        model=model,
        provider=provider,
        reasoning_effort=reasoning_effort,
        timeout=timeout,
        async_mode=async_mode,
        reason=reason,
        mode=mode,
        wait_required=wait_required,
        task_shape=task_shape,
        subagent_type=subagent_type,
        input_items=input_items,
        fork_context=fork_context,
        codex_collab_payload=codex_collab_payload,
        infer_spawn_agent_metadata_fn=infer_spawn_agent_metadata,
        resolve_spawn_agent_async_mode_fn=resolve_spawn_agent_async_mode,
        resolved_delegation_metadata_fn=_resolved_delegation_metadata,
        create_delegated_agent_session_fn=create_delegated_agent_session,
        now_iso_fn=_runtime_now_iso,
        tool_event_factory=ToolEvent,
        command_result_factory=CommandExecutionResult,
        generic_tool_call_item_events_fn=generic_tool_call_item_events,
    )

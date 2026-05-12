from __future__ import annotations

from typing import Any

from cli.agent_cli import builtin_agent_profiles_runtime
from cli.agent_cli.models import CommandExecutionResult
from cli.agent_cli.runtime_services import (
    delegated_agent_session_operations_helpers_runtime,
    delegated_agent_session_payload_runtime,
    delegated_agent_session_runtime_runtime,
    delegated_agent_spawn_runtime,
)


def sync_delegated_run_record(
    runtime: Any,
    session: Any,
    *,
    forced_status: str | None = None,
    forced_summary: str | None = None,
) -> None:
    delegated_agent_session_operations_helpers_runtime.sync_delegated_run_record_impl(
        runtime,
        session,
        forced_status=forced_status,
        forced_summary=forced_summary,
    )


def provider_config_with_model_timeout(config: Any, timeout: int | None) -> Any:
    return (
        delegated_agent_session_operations_helpers_runtime.provider_config_with_model_timeout_impl(
            config,
            timeout,
        )
    )


def delegated_planner(
    runtime: Any,
    config: Any,
    *,
    timeout: int | None = None,
    build_planner_fn: Any,
    current_host_platform_fn: Any,
) -> Any:
    return delegated_agent_session_operations_helpers_runtime.delegated_planner_impl(
        runtime,
        config,
        timeout=timeout,
        build_planner_fn=build_planner_fn,
        current_host_platform_fn=current_host_platform_fn,
        provider_config_with_model_timeout_fn=provider_config_with_model_timeout,
    )


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
    normalize_spawn_agent_metadata_fn: Any,
    sync_delegated_run_record_fn: Any,
) -> Any:
    session = delegated_agent_session_payload_runtime.build_session(
        runtime=runtime,
        session_class=session_class,
        task_text=task_text,
        role=role,
        resolution=resolution,
        metadata=dict(metadata or {}),
        input_items=input_items,
        fork_context=fork_context,
        normalize_spawn_agent_metadata_fn=normalize_spawn_agent_metadata_fn,
    )
    with runtime._delegated_agents_lock:
        runtime._delegated_agents[session.agent_id] = session
    sync_delegated_run_record_fn(
        runtime,
        session,
        forced_status="created",
        forced_summary="delegated session queued",
    )
    runtime._notify_delegated_scheduler()
    runtime._start_delegated_agent_worker(session)
    return session


def agent_workflow_result(
    runtime: Any,
    agent_id: str,
    *,
    steps_limit: int = 8,
    checkpoints_limit: int = 8,
    tool_event_factory: Any,
    command_result_factory: Any,
    generic_tool_call_item_events_fn: Any,
) -> CommandExecutionResult:
    session = runtime._delegated_session(agent_id)
    with session.condition:
        payload = runtime._delegated_workflow_payload(
            session,
            steps_limit=max(1, int(steps_limit)),
            checkpoints_limit=max(1, int(checkpoints_limit)),
        )
    event = tool_event_factory(
        name="agent_workflow",
        ok=True,
        summary=f"workflow_state={payload.get('workflow_state') or 'idle'}",
        payload=payload,
    )
    return command_result_factory(
        assistant_text=runtime._delegated_workflow_text(payload),
        tool_events=[event],
        item_events=generic_tool_call_item_events_fn(
            tool_name="agent_workflow",
            arguments={
                "target": str(agent_id or "").strip(),
                "steps": max(1, int(steps_limit)),
                "checkpoints": max(1, int(checkpoints_limit)),
            },
            ok=True,
            summary=str(event.summary or ""),
            structured_content=dict(event.payload or {}),
        ),
    )


def close_agent_result(
    runtime: Any,
    agent_id: str,
    *,
    codex_style: bool = False,
    now_iso_fn: Any,
    sync_delegated_run_record_fn: Any,
    tool_event_factory: Any,
    command_result_factory: Any,
    generic_tool_call_item_events_fn: Any,
) -> CommandExecutionResult:
    session = runtime._delegated_session(agent_id)
    codex_status = None
    with session.condition:
        if codex_style:
            codex_status = (
                delegated_agent_session_payload_runtime.codex_agent_status_wire_for_session(session)
            )
        outcome = delegated_agent_session_runtime_runtime.close_session(
            session=session,
            now_iso_fn=now_iso_fn,
            refresh_current_step_id_fn=runtime._refresh_delegated_current_step_id,
            record_checkpoint_fn=runtime._record_delegated_checkpoint,
            delegated_agent_payload_fn=runtime._delegated_agent_payload,
        )
        session.condition.notify_all()
        payload = outcome["payload"]
    runtime._notify_delegated_scheduler()
    sync_delegated_run_record_fn(
        runtime,
        session,
        forced_status="cancelled",
        forced_summary="delegated session cancelled",
    )
    runtime._sync_delegated_background_task(session)
    if codex_style:
        return delegated_agent_session_payload_runtime.codex_collab_tool_result(
            tool_name="close_agent",
            payload=payload,
            function_output={"status": codex_status},
            assistant_text=f"delegated agent {session.agent_id} {payload['status']}",
            summary="close_agent completed",
            tool_event_factory=tool_event_factory,
            command_result_factory=command_result_factory,
        )
    return delegated_agent_session_payload_runtime.session_tool_result(
        tool_name="close_agent",
        target=agent_id,
        payload=payload,
        assistant_text=f"delegated agent {session.agent_id} {payload['status']}",
        summary="close_agent completed",
        tool_event_factory=tool_event_factory,
        command_result_factory=command_result_factory,
        generic_tool_call_item_events_fn=generic_tool_call_item_events_fn,
    )


def resume_agent_result(
    runtime: Any,
    agent_id: str,
    *,
    codex_style: bool = False,
    now_iso_fn: Any,
    sync_delegated_run_record_fn: Any,
    tool_event_factory: Any,
    command_result_factory: Any,
    generic_tool_call_item_events_fn: Any,
) -> CommandExecutionResult:
    session = runtime._delegated_session(agent_id)
    with session.condition:
        outcome = delegated_agent_session_runtime_runtime.resume_session(
            session=session,
            now_iso_fn=now_iso_fn,
            refresh_current_step_id_fn=runtime._refresh_delegated_current_step_id,
            record_checkpoint_fn=runtime._record_delegated_checkpoint,
            delegated_agent_payload_fn=runtime._delegated_agent_payload,
        )
        payload = outcome["payload"]
        session.condition.notify_all()
    if outcome["should_start"]:
        runtime._start_delegated_agent_worker(session)
    runtime._notify_delegated_scheduler()
    sync_delegated_run_record_fn(runtime, session, forced_summary="delegated session resumed")
    runtime._sync_delegated_background_task(session)
    if codex_style:
        return delegated_agent_session_payload_runtime.codex_collab_tool_result(
            tool_name="resume_agent",
            payload=payload,
            function_output={
                "status": delegated_agent_session_payload_runtime.codex_agent_status_wire_for_session(
                    session
                )
            },
            assistant_text=f"delegated agent {session.agent_id} resumed",
            summary="resume_agent completed",
            tool_event_factory=tool_event_factory,
            command_result_factory=command_result_factory,
        )
    return delegated_agent_session_payload_runtime.session_tool_result(
        tool_name="resume_agent",
        target=agent_id,
        payload=payload,
        assistant_text=f"delegated agent {session.agent_id} resumed",
        summary="resume_agent completed",
        tool_event_factory=tool_event_factory,
        command_result_factory=command_result_factory,
        generic_tool_call_item_events_fn=generic_tool_call_item_events_fn,
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
    infer_spawn_agent_metadata_fn: Any,
    resolve_spawn_agent_async_mode_fn: Any,
    resolved_delegation_metadata_fn: Any,
    create_delegated_agent_session_fn: Any,
    now_iso_fn: Any,
    tool_event_factory: Any,
    command_result_factory: Any,
    generic_tool_call_item_events_fn: Any,
) -> CommandExecutionResult:
    spawn_context = delegated_agent_session_runtime_runtime.resolved_spawn_context(
        task=task,
        role=role,
        async_mode=async_mode,
        reason=reason,
        mode=mode,
        wait_required=wait_required,
        task_shape=task_shape,
        subagent_type=subagent_type,
        codex_collab_payload=codex_collab_payload,
        infer_spawn_agent_metadata_fn=infer_spawn_agent_metadata_fn,
        resolve_spawn_agent_async_mode_fn=resolve_spawn_agent_async_mode_fn,
        resolved_delegation_metadata_fn=resolved_delegation_metadata_fn,
    )
    task_text = str(spawn_context["task_text"] or "")
    effective_async_mode = bool(spawn_context["effective_async_mode"])
    delegation_metadata = dict(spawn_context["delegation_metadata"] or {})
    normalized_subagent_type = str(delegation_metadata.get("subagent_type") or "").strip()
    effective_model = model
    if (
        not str(effective_model or "").strip()
        and not str(provider or "").strip()
        and normalized_subagent_type
    ):
        effective_model = builtin_agent_profiles_runtime.profile_default_model_selector(
            normalized_subagent_type
        )
    effective_fork_context = fork_context
    if (
        effective_fork_context is None
        and normalized_subagent_type
        and delegated_agent_spawn_runtime.profile_uses_fresh_context(normalized_subagent_type)
    ):
        effective_fork_context = False
    resolution = runtime.agent.resolve_delegate_execution(
        role,
        model=effective_model,
        provider=provider,
        reasoning_effort=reasoning_effort,
        timeout=timeout,
    )
    if resolution.config is None:
        raise RuntimeError(f"delegated agent unavailable for role: {role}")
    if effective_async_mode:
        session = create_delegated_agent_session_fn(
            runtime,
            session_class=session_class,
            task_text=task_text,
            role=role,
            resolution=resolution,
            metadata=delegation_metadata,
            input_items=input_items,
            fork_context=effective_fork_context,
        )
        runtime._sync_delegated_background_task(session)
        return delegated_agent_session_payload_runtime.async_spawn_result(
            session=session,
            task_text=task_text,
            role=role,
            model=model,
            provider=provider,
            reasoning_effort=reasoning_effort,
            timeout=timeout,
            delegation_metadata=delegation_metadata,
            input_items=input_items,
            fork_context=effective_fork_context,
            delegated_agent_payload_fn=runtime._delegated_agent_payload,
            tool_event_factory=tool_event_factory,
            command_result_factory=command_result_factory,
            generic_tool_call_item_events_fn=generic_tool_call_item_events_fn,
            codex_collab_payload=codex_collab_payload,
        )
    planner = runtime._delegated_planner(
        resolution.config,
        timeout=resolution.timeout,
    )
    plan_kwargs = delegated_agent_spawn_runtime.delegated_sync_plan_kwargs(
        runtime,
        planner,
        role=role,
        input_items=input_items,
        fork_context=effective_fork_context,
        subagent_type=normalized_subagent_type,
        task_text=task_text,
        description=str(delegation_metadata.get("description") or "").strip(),
    )
    intent = planner.plan(task_text, **plan_kwargs)
    result = runtime._execute_agent_intent_result(intent)
    completion = delegated_agent_spawn_runtime.delegated_sync_completion_payload(
        runtime,
        resolution=resolution,
        result=result,
        intent=intent,
        task_text=task_text,
        role=role,
        delegation_metadata=delegation_metadata,
        adopted_at=now_iso_fn(),
    )
    event = tool_event_factory(
        name="spawn_agent",
        ok=True,
        summary="spawn_agent completed",
        payload=completion["payload"],
    )
    return command_result_factory(
        assistant_text=str(completion["assistant_text"] or ""),
        tool_events=[event],
        item_events=generic_tool_call_item_events_fn(
            tool_name="spawn_agent",
            arguments=delegated_agent_session_payload_runtime.spawn_agent_arguments(
                task_text=task_text,
                role=role,
                model=model,
                provider=provider,
                reasoning_effort=reasoning_effort,
                timeout=timeout,
                effective_async_mode=bool(effective_async_mode),
                delegation_metadata=delegation_metadata,
                input_items=input_items,
                fork_context=effective_fork_context,
                source_message=task_text if codex_collab_payload else None,
                codex_collab_payload=codex_collab_payload,
            ),
            ok=True,
            summary="spawn_agent completed",
            structured_content=dict(event.payload or {}),
        ),
    )

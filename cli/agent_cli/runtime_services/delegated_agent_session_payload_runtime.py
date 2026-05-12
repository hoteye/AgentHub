from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli import builtin_agent_profiles_runtime
from cli.agent_cli.runtime_services import (
    delegated_agent_session_payload_projection_helpers_runtime,
    delegated_agent_session_payload_pure_helpers_runtime,
    delegated_agent_spawn_runtime,
)

_normalized_optional_bool = (
    delegated_agent_session_payload_pure_helpers_runtime.normalized_optional_bool
)
_normalized_optional_text = (
    delegated_agent_session_payload_pure_helpers_runtime.normalized_optional_text
)
_resolved_subagent_protocol_ids = (
    delegated_agent_session_payload_pure_helpers_runtime.resolved_subagent_protocol_ids
)
_normalize_async_started_payload = (
    delegated_agent_session_payload_pure_helpers_runtime.normalize_async_started_payload
)

codex_collab_function_output_text = (
    delegated_agent_session_payload_projection_helpers_runtime.codex_collab_function_output_text
)
codex_collab_event_payload = (
    delegated_agent_session_payload_projection_helpers_runtime.codex_collab_event_payload
)
codex_agent_status_wire = (
    delegated_agent_session_payload_projection_helpers_runtime.codex_agent_status_wire
)
codex_agent_status_wire_for_session = (
    delegated_agent_session_payload_projection_helpers_runtime.codex_agent_status_wire_for_session
)
spawn_agent_arguments = (
    delegated_agent_session_payload_projection_helpers_runtime.spawn_agent_arguments
)
resolved_delegation_metadata = (
    delegated_agent_session_payload_pure_helpers_runtime.resolved_delegation_metadata
)
session_tool_result = delegated_agent_session_payload_projection_helpers_runtime.session_tool_result
codex_collab_tool_result = (
    delegated_agent_session_payload_projection_helpers_runtime.codex_collab_tool_result
)
async_spawn_result = delegated_agent_session_payload_projection_helpers_runtime.async_spawn_result


def build_session(
    *,
    runtime: Any,
    session_class: Any,
    task_text: str,
    role: str,
    resolution: Any,
    metadata: dict[str, Any],
    input_items: list[dict[str, Any]] | None = None,
    fork_context: bool | None = None,
    normalize_spawn_agent_metadata_fn: Callable[..., dict[str, Any]],
) -> Any:
    agent_id = runtime._delegated_agent_id()
    normalized_metadata = normalize_spawn_agent_metadata_fn(metadata, async_mode=True, role=role)
    subagent_type = builtin_agent_profiles_runtime.normalize_subagent_type(
        normalized_metadata.get("subagent_type")
    )
    delegation_mode = str(normalized_metadata.get("delegation_mode") or "").strip() or "background"
    wait_required = None
    if "wait_required" in normalized_metadata:
        wait_required = _normalized_optional_bool(normalized_metadata.get("wait_required"))
    if delegation_mode.lower() == "background" and wait_required is None:
        wait_required = False
    protocol_ids = _resolved_subagent_protocol_ids(normalized_metadata)
    effective_fork_context = fork_context
    if (
        effective_fork_context is None
        and builtin_agent_profiles_runtime.profile_uses_fresh_context(subagent_type)
    ):
        effective_fork_context = False
    inherited_seed_input_items = (
        [dict(item) for item in runtime._delegated_planner_input_items() if isinstance(item, dict)]
        if effective_fork_context is not False
        else []
    )
    environment_seed_input_items = delegated_agent_spawn_runtime.profile_environment_input_items(
        runtime,
        subagent_type=subagent_type,
    )
    inherited_seed_history = (
        [
            dict(item)
            for item in runtime._planner_history_with_context_updates(
                planner_history=runtime._planner_history(),
            )
            if isinstance(item, dict)
        ]
        if effective_fork_context is not False
        else []
    )
    session = session_class(
        agent_id=agent_id,
        role=str(role or "").strip() or "subagent",
        config=resolution.config,
        timeout=resolution.timeout,
        source=str(resolution.source or ""),
        protocol_run_id=protocol_ids["run_id"],
        protocol_parent_run_id=protocol_ids["parent_run_id"],
        protocol_thread_id=protocol_ids["thread_id"],
        resume_source="spawn_agent",
        delegation_reason=str(normalized_metadata.get("delegation_reason") or ""),
        delegation_mode=delegation_mode,
        wait_required=wait_required,
        task_shape=str(normalized_metadata.get("task_shape") or ""),
        subagent_type=subagent_type,
        background_priority=runtime._delegated_background_priority(
            role=role,
            delegation_mode=delegation_mode,
            wait_required=wait_required,
        ),
        parallel_group=runtime._delegated_parallel_group(normalized_metadata.get("task_shape")),
        seed_input_items=[
            *list(environment_seed_input_items or []),
            *list(inherited_seed_input_items or []),
        ],
        seed_history=inherited_seed_history,
        queued_inputs=[],
        status="queued",
    )
    initial_step_id = runtime._queue_delegated_step(
        session, user_text=task_text, source="initial_task"
    )
    session.queued_inputs = [
        runtime._delegated_queue_item(
            task_text,
            step_id=initial_step_id,
            **({"input_items": input_items} if input_items is not None else {}),
        )
    ]
    runtime._refresh_delegated_current_step_id(session)
    return session

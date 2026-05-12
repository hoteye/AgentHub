from __future__ import annotations

import uuid
from typing import Any

from cli.agent_cli import builtin_agent_profiles_runtime
from cli.agent_cli.runtime_services import delegated_agent_event_forwarding_runtime


def _normalized_optional_bool(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


profile_uses_fresh_context = builtin_agent_profiles_runtime.profile_uses_fresh_context


def profile_environment_input_items(
    runtime: Any, *, subagent_type: str | None = None
) -> list[dict[str, Any]]:
    if not builtin_agent_profiles_runtime.profile_needs_environment_context(subagent_type):
        return []
    context_updater = getattr(runtime, "_environment_context_turn_update", None)
    history_projector = getattr(runtime, "_planner_message_history_input_items", None)
    if not callable(context_updater) or not callable(history_projector):
        return []
    try:
        environment_messages, _environment_snapshot = context_updater()
        return [
            dict(item)
            for item in list(history_projector(list(environment_messages or [])) or [])
            if isinstance(item, dict)
        ]
    except Exception:
        return []


def delegated_sync_plan_kwargs(
    runtime: Any,
    planner: Any,
    *,
    role: str,
    input_items: list[dict[str, Any]] | None = None,
    fork_context: bool | None = None,
    subagent_type: str | None = None,
    task_text: str = "",
    description: str = "",
) -> dict[str, Any]:
    effective_fork_context = fork_context
    if effective_fork_context is None and profile_uses_fresh_context(subagent_type):
        effective_fork_context = False
    if effective_fork_context is False:
        inherited_input_items: list[dict[str, Any]] = []
        inherited_history = []
    else:
        inherited_input_items = runtime._delegated_planner_input_items()
        inherited_history = runtime._planner_history()
    profile_items = builtin_agent_profiles_runtime.profile_instruction_items(subagent_type)
    environment_items = profile_environment_input_items(runtime, subagent_type=subagent_type)
    merged_input_items = [
        dict(item)
        for item in [
            *list(profile_items or []),
            *list(environment_items or []),
            *list(inherited_input_items or []),
            *list(input_items or []),
        ]
        if isinstance(item, dict)
    ]
    tool_executor = builtin_agent_profiles_runtime.profiled_tool_executor(
        runtime._structured_tool_executor,
        subagent_type=subagent_type,
    )
    task_id = f"delegate_{uuid.uuid4().hex[:12]}"
    delegated_agent_event_forwarding_runtime.emit_delegated_task_started(
        runtime,
        task_id=task_id,
        task_text=task_text,
        description=description,
        role=role,
        subagent_type=subagent_type,
    )
    turn_event_callback = (
        delegated_agent_event_forwarding_runtime.delegated_child_turn_event_callback(
            runtime,
            task_id=task_id,
            task_text=task_text,
            description=description,
            role=role,
            subagent_type=subagent_type,
        )
    )
    plan_kwargs = runtime._filter_handler_kwargs(
        planner.plan,
        {
            "history": inherited_history,
            "tool_executor": tool_executor,
            "attachments": [],
            "input_items": merged_input_items,
            "prompt_cache_key": f"{runtime.thread_id or 'adhoc'}:delegate:{role}",
            "subagent_type": subagent_type,
            "turn_event_callback": turn_event_callback,
        },
    )
    if "input_items" in plan_kwargs:
        if "history" in plan_kwargs:
            plan_kwargs["history"] = []
    elif "history" in plan_kwargs:
        plan_kwargs["history"] = runtime._planner_history_with_context_updates(
            planner_history=runtime._planner_history(),
        )
    return plan_kwargs


def delegated_sync_completion_payload(
    runtime: Any,
    *,
    resolution: Any,
    result: Any,
    intent: Any,
    task_text: str,
    role: str,
    delegation_metadata: dict[str, Any],
    adopted_at: str,
) -> dict[str, Any]:
    normalized_delegation_metadata = dict(delegation_metadata or {})
    if "wait_required" in normalized_delegation_metadata:
        wait_required = _normalized_optional_bool(
            normalized_delegation_metadata.get("wait_required")
        )
        normalized_delegation_metadata["wait_required"] = (
            wait_required if wait_required is not None else False
        )
    assistant_text = str(result.assistant_text or "").strip()
    if not assistant_text and result.turn_events:
        assistant_text = runtime._assistant_text_from_turn_events(result.turn_events)
    completion_policy = runtime._delegated_completion_policy(
        role=role,
        delegation_mode=normalized_delegation_metadata.get("delegation_mode"),
        wait_required=normalized_delegation_metadata.get("wait_required"),
    )
    result_contract = runtime._delegated_result_contract_payload(
        goal=task_text,
        status="completed",
        assistant_text=assistant_text,
        error="",
        adopted=True,
        touched_sources=[
            *list(result.tool_events or []),
            *list(result.item_events or []),
            *list(result.turn_events or []),
        ],
        role=str(role or "").strip(),
        delegation_mode=str(normalized_delegation_metadata.get("delegation_mode") or ""),
        wait_required=normalized_delegation_metadata.get("wait_required"),
    )
    payload = {
        "ok": True,
        "role": str(role or "").strip() or "subagent",
        "task": task_text,
        "provider_name": str(resolution.config.provider_name or ""),
        "base_url": str(resolution.config.base_url or ""),
        "model_key": str(resolution.config.model_key or ""),
        "planner_kind": str(resolution.config.planner_kind or ""),
        "wire_api": str(resolution.config.wire_api or ""),
        "model": str(resolution.config.model or ""),
        "reasoning_effort": str(resolution.config.reasoning_effort or ""),
        "source": str(resolution.source or ""),
        "timeout": resolution.timeout,
        "text": assistant_text,
        "parallel_group": "sync_inline",
        "parallel_limit": 1,
        "result_ready": True,
        "adopted": True,
        "adopted_at": adopted_at,
        "completion_policy": completion_policy,
        "completion_state": runtime._delegated_completion_state(
            status="completed",
            adopted=True,
            completion_policy=completion_policy,
        ),
        "background_priority": runtime._delegated_background_priority(
            role=role,
            delegation_mode=normalized_delegation_metadata.get("delegation_mode"),
            wait_required=normalized_delegation_metadata.get("wait_required"),
        ),
        "adoption_expectation": str(result_contract.get("next_action") or "").strip()
        or "already_adopted",
        "tool_event_count": len(list(result.tool_events or [])),
        "tool_names": [
            str(item.name or "")
            for item in list(result.tool_events or [])
            if str(item.name or "").strip()
        ],
        "result_contract": result_contract,
        "timings": dict(getattr(intent, "timings", {}) or {}),
        **normalized_delegation_metadata,
    }
    return {
        "assistant_text": assistant_text,
        "completion_policy": completion_policy,
        "result_contract": result_contract,
        "payload": payload,
    }

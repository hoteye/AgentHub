from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

_DELEGATION_TOOL_NAMES = {
    "spawn_agent",
    "request_orchestration",
    "spawn_child_tab",
    "send_child_tab",
    "wait_child_tasks",
    "send_input",
    "wait_agent",
    "agent_workflow",
    "recover_agent",
}


def build_planner_trace_summary(
    tool_calls: Iterable[Any],
    *,
    reason_codes: tuple[str, ...],
    wait_reason_codes: tuple[str, ...],
    recovery_action_values: tuple[str, ...],
    delegation_mode_values: tuple[str, ...],
    task_shapes: tuple[str, ...],
    role_values: tuple[str, ...],
    apply_planner_delegation_defaults_fn: Callable[..., dict[str, Any]],
    planner_tool_execution_target_fn: Callable[..., tuple[str, dict[str, Any]]],
    planner_defaulted_fields_fn: Callable[..., list[str]],
    planner_policy_basis_fn: Callable[..., str],
    resolve_spawn_agent_async_mode_fn: Callable[..., bool],
    timeout_budget_seconds_fn: Callable[[dict[str, Any]], int | float | None],
    wait_timeout_ms_fn: Callable[[dict[str, Any]], int | None],
) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []
    observed_tools: list[str] = []
    non_delegation_tools: list[str] = []
    saw_spawn = False
    saw_wait = False
    saw_wait_now = False
    saw_wait_later = False
    saw_recover = False
    for call in list(tool_calls or []):
        tool_name = str(getattr(call, "name", "") or "").strip()
        if tool_name:
            observed_tools.append(tool_name)
            if tool_name not in _DELEGATION_TOOL_NAMES:
                non_delegation_tools.append(tool_name)
        raw_arguments = getattr(call, "arguments", {}) or {}
        arguments = dict(raw_arguments) if isinstance(raw_arguments, dict) else {}
        enriched = apply_planner_delegation_defaults_fn(
            tool_name,
            arguments,
            reason_codes=reason_codes,
            wait_reason_codes=wait_reason_codes,
            recovery_action_values=recovery_action_values,
            delegation_mode_values=delegation_mode_values,
            task_shapes=task_shapes,
            role_values=role_values,
        )
        execution_tool_name, _ = planner_tool_execution_target_fn(
            tool_name,
            arguments,
            reason_codes=reason_codes,
            wait_reason_codes=wait_reason_codes,
            recovery_action_values=recovery_action_values,
            delegation_mode_values=delegation_mode_values,
            task_shapes=task_shapes,
            role_values=role_values,
        )
        if tool_name == "spawn_agent":
            saw_spawn = True
            defaulted_fields = planner_defaulted_fields_fn(
                arguments,
                enriched,
                field_names=("async", "reason", "mode", "wait_required", "task_shape"),
            )
            action_async_mode = resolve_spawn_agent_async_mode_fn(
                enriched,
                async_mode=None,
                role=str(enriched.get("role") or enriched.get("agent_type") or "").strip()
                or "subagent",
                delegation_mode_values=delegation_mode_values,
                role_values=role_values,
            )
            action: dict[str, Any] = {
                "tool_name": "spawn_agent",
                "role": str(enriched.get("role") or enriched.get("agent_type") or "").strip()
                or "subagent",
                "execution_tool": execution_tool_name,
                "planner_policy": "delegate_async" if action_async_mode else "delegate_sync",
                "delegation_control_action": "continue" if action_async_mode else "downgrade",
            }
            if "async" in enriched and enriched.get("async") is not None:
                action["async"] = bool(enriched.get("async"))
            if str(enriched.get("reason") or "").strip():
                action["delegation_reason"] = str(enriched.get("reason") or "").strip()
            if str(enriched.get("mode") or "").strip():
                action["delegation_mode"] = str(enriched.get("mode") or "").strip()
            if "wait_required" in enriched and enriched.get("wait_required") is not None:
                action["wait_required"] = bool(enriched.get("wait_required"))
            if str(enriched.get("task_shape") or "").strip():
                action["task_shape"] = str(enriched.get("task_shape") or "").strip()
            if str(enriched.get("model") or "").strip():
                action["model"] = str(enriched.get("model") or "").strip()
            if str(enriched.get("provider") or "").strip():
                action["provider"] = str(enriched.get("provider") or "").strip()
            spawn_timeout_budget_seconds = timeout_budget_seconds_fn(enriched)
            if spawn_timeout_budget_seconds is not None:
                action["timeout_budget_seconds"] = spawn_timeout_budget_seconds
            if defaulted_fields:
                action["defaulted_fields"] = list(defaulted_fields)
            action["policy_basis"] = planner_policy_basis_fn(
                tool_name, arguments, enriched, defaulted_fields=defaulted_fields
            )
            actions.append(action)
            continue
        if tool_name == "wait_agent":
            saw_wait = True
            defaulted_fields = planner_defaulted_fields_fn(
                arguments, enriched, field_names=("reason", "wait_required")
            )
            action: dict[str, Any] = {
                "tool_name": "wait_agent",
                "target": str(
                    enriched.get("target") or enriched.get("agent_id") or enriched.get("id") or ""
                ).strip(),
                "execution_tool": execution_tool_name,
            }
            if str(enriched.get("reason") or "").strip():
                action["wait_reason"] = str(enriched.get("reason") or "").strip()
            if "wait_required" in enriched and enriched.get("wait_required") is not None:
                action["wait_required"] = bool(enriched.get("wait_required"))
            wait_budget_ms = wait_timeout_ms_fn(enriched)
            if wait_budget_ms is not None:
                action["wait_timeout_ms"] = wait_budget_ms
            if bool(enriched.get("wait_required")):
                action["planner_policy"] = "wait_now"
                saw_wait_now = True
                action["delegation_control_action"] = "wait"
            else:
                action["planner_policy"] = "wait_later"
                saw_wait_later = True
                action["preferred_snapshot_tool"] = "agent_workflow"
                action["delegation_control_action"] = "continue"
            if defaulted_fields:
                action["defaulted_fields"] = list(defaulted_fields)
            action["policy_basis"] = planner_policy_basis_fn(
                tool_name, arguments, enriched, defaulted_fields=defaulted_fields
            )
            actions.append(action)
            continue
        if tool_name == "agent_workflow":
            saw_wait_later = True
            actions.append(
                {
                    "tool_name": "agent_workflow",
                    "target": str(
                        enriched.get("target")
                        or enriched.get("agent_id")
                        or enriched.get("id")
                        or ""
                    ).strip(),
                    "planner_policy": "wait_later",
                    "policy_basis": "explicit_arguments",
                    "execution_tool": execution_tool_name,
                    "delegation_control_action": "continue",
                }
            )
            continue
        if tool_name == "recover_agent":
            saw_recover = True
            defaulted_fields = planner_defaulted_fields_fn(
                arguments, enriched, field_names=("action",)
            )
            recovery_action = (
                str(enriched.get("action") or enriched.get("recovery_action") or "").strip()
                or "retry_step"
            )
            planner_policy = "retry_child"
            if recovery_action == "resume_session":
                planner_policy = "resume_child"
            elif recovery_action == "close_session":
                planner_policy = "close_child"
            action = {
                "tool_name": "recover_agent",
                "target": str(
                    enriched.get("target") or enriched.get("agent_id") or enriched.get("id") or ""
                ).strip(),
                "recovery_action": recovery_action,
                "planner_policy": planner_policy,
                "execution_tool": execution_tool_name,
                "delegation_control_action": (
                    "stop" if planner_policy == "close_child" else "continue"
                ),
            }
            if str(enriched.get("step_id") or "").strip():
                action["step_id"] = str(enriched.get("step_id") or "").strip()
            if defaulted_fields:
                action["defaulted_fields"] = list(defaulted_fields)
            action["policy_basis"] = planner_policy_basis_fn(
                tool_name, arguments, enriched, defaulted_fields=defaulted_fields
            )
            actions.append(action)

    if saw_recover:
        first_recover = next(
            (item for item in actions if item.get("tool_name") == "recover_agent"), None
        )
        decision = (
            str(first_recover.get("planner_policy") or "retry_child")
            if isinstance(first_recover, dict)
            else "retry_child"
        )
    elif saw_wait_now:
        decision = "wait_now"
    elif saw_spawn and saw_wait:
        decision = "delegate_and_wait"
    elif saw_spawn:
        decision = "delegate"
    elif saw_wait:
        decision = "wait"
    else:
        decision = "none"

    if saw_recover:
        policy_decision = decision
        policy_reason = "recover_agent"
    elif saw_wait_now:
        policy_decision = "wait_now"
        policy_reason = "wait_agent_blocking_join"
    elif saw_spawn:
        first_spawn = next(
            (item for item in actions if item.get("tool_name") == "spawn_agent"), None
        )
        policy_decision = (
            str(first_spawn.get("planner_policy") or "delegate_async")
            if isinstance(first_spawn, dict)
            else "delegate_async"
        )
        policy_reason = "spawn_agent"
    elif saw_wait_later or saw_wait:
        policy_decision = "wait_later"
        if any(
            isinstance(item, dict)
            and item.get("tool_name") == "wait_agent"
            and item.get("planner_policy") == "wait_later"
            for item in actions
        ):
            policy_reason = "wait_agent_non_blocking_snapshot"
        else:
            policy_reason = "agent_workflow_snapshot"
    else:
        policy_decision = "stay_local"
        policy_reason = "no_delegation_tools_observed"

    summary: dict[str, Any] = {
        "delegation_decision": decision,
        "delegation_policy_decision": policy_decision,
        "delegation_policy_source": "delegation_policy",
        "delegation_policy_reason": policy_reason,
        "delegation_policy_input_source": "tool_calls",
        "observed_tool_count": len(observed_tools),
        "observed_delegation_tool_count": len(observed_tools) - len(non_delegation_tools),
        "observed_non_delegation_tool_count": len(non_delegation_tools),
    }
    if observed_tools:
        summary["observed_tool_names"] = list(observed_tools)
    if non_delegation_tools:
        summary["observed_non_delegation_tool_names"] = list(non_delegation_tools)
    if saw_spawn and saw_wait:
        summary["delegation_multi_step_path"] = "spawn_then_wait"
        summary["delegation_multi_step_join"] = "blocking" if saw_wait_now else "non_blocking"
    if policy_decision == "stay_local":
        summary["delegation_stay_local_source"] = "planner_tool_calls"
        summary["delegation_stay_local_reason"] = (
            "non_delegation_tools_only" if non_delegation_tools else "no_tools_observed"
        )
        if non_delegation_tools:
            summary["delegation_stay_local_counterexamples"] = list(non_delegation_tools)
    if not actions:
        return summary
    summary["delegation_actions"] = actions
    first_spawn = next((item for item in actions if item.get("tool_name") == "spawn_agent"), None)
    first_wait = next((item for item in actions if item.get("tool_name") == "wait_agent"), None)
    first_recover = next(
        (item for item in actions if item.get("tool_name") == "recover_agent"), None
    )
    if isinstance(first_spawn, dict):
        if str(first_spawn.get("delegation_reason") or "").strip():
            summary["delegation_reason"] = str(first_spawn.get("delegation_reason") or "").strip()
        if str(first_spawn.get("delegation_mode") or "").strip():
            summary["delegation_mode"] = str(first_spawn.get("delegation_mode") or "").strip()
        if "wait_required" in first_spawn:
            summary["wait_required"] = bool(first_spawn.get("wait_required"))
        if str(first_spawn.get("task_shape") or "").strip():
            summary["task_shape"] = str(first_spawn.get("task_shape") or "").strip()
        if first_spawn.get("timeout_budget_seconds") not in (None, ""):
            summary["timeout_budget_seconds"] = first_spawn["timeout_budget_seconds"]
    if isinstance(first_wait, dict):
        if str(first_wait.get("wait_reason") or "").strip():
            summary["wait_reason"] = str(first_wait.get("wait_reason") or "").strip()
        if "wait_required" in first_wait:
            summary["wait_required"] = bool(first_wait.get("wait_required"))
        if first_wait.get("wait_timeout_ms") not in (None, ""):
            summary["wait_timeout_ms"] = int(first_wait["wait_timeout_ms"])
    if isinstance(first_recover, dict):
        if str(first_recover.get("recovery_action") or "").strip():
            summary["recovery_action"] = str(first_recover.get("recovery_action") or "").strip()
    budget_fields: list[str] = []
    if summary.get("timeout_budget_seconds") not in (None, ""):
        budget_fields.append("timeout_budget_seconds")
    if summary.get("wait_timeout_ms") not in (None, ""):
        budget_fields.append("wait_timeout_ms")
    if budget_fields:
        summary["delegation_budget_source"] = "planner_arguments"
        summary["delegation_budget_fields"] = budget_fields
    return summary

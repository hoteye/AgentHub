from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Tuple

from cli.agent_cli.providers import delegation_policy_mapping_helpers_runtime as delegation_policy_mapping_helpers_runtime_service
from cli.agent_cli.providers import delegation_policy_mapping_trace_helpers_runtime as delegation_policy_mapping_trace_helpers_runtime_service
from cli.agent_cli.providers import delegation_policy_planner_mapping_runtime
from cli.agent_cli.providers import delegation_policy_runtime as delegation_policy_runtime_service


def _normalized_trace_bool(value: Any) -> bool | None:
    return delegation_policy_mapping_trace_helpers_runtime_service.normalized_trace_bool(value)


def _canonical_planner_tool_name(tool_name: str) -> str:
    return delegation_policy_mapping_trace_helpers_runtime_service.canonical_planner_tool_name(tool_name)


def _canonicalized_tool_arguments(
    tool_name: str,
    arguments: Dict[str, Any] | None,
) -> Dict[str, Any]:
    return delegation_policy_mapping_trace_helpers_runtime_service.canonicalized_tool_arguments(tool_name, arguments)


def _canonicalized_tool_calls(tool_calls: Iterable[Any]) -> list[Any]:
    return delegation_policy_mapping_trace_helpers_runtime_service.canonicalized_tool_calls(tool_calls)


def _delegation_execution_mode_and_reason(summary: Dict[str, Any]) -> tuple[str, str]:
    return delegation_policy_mapping_trace_helpers_runtime_service.delegation_execution_mode_and_reason(summary)


def _action_execution_mode(action: Dict[str, Any]) -> str:
    return delegation_policy_mapping_trace_helpers_runtime_service.action_execution_mode(action)


def normalized_enum(value: Any, allowed: Tuple[str, ...]) -> str | None:
    return delegation_policy_mapping_helpers_runtime_service.normalized_enum(value, allowed)


def normalized_bool(value: Any) -> bool | None:
    return delegation_policy_mapping_helpers_runtime_service.normalized_bool(value)


def argument_is_supplied(payload: Dict[str, Any], key: str) -> bool:
    return delegation_policy_mapping_helpers_runtime_service.argument_is_supplied(payload, key)


def normalized_number(value: Any) -> int | float | None:
    return delegation_policy_mapping_helpers_runtime_service.normalized_number(value)


def normalized_int(value: Any) -> int | None:
    return delegation_policy_mapping_helpers_runtime_service.normalized_int(value)


def timeout_budget_seconds(payload: Dict[str, Any]) -> int | float | None:
    return delegation_policy_mapping_helpers_runtime_service.timeout_budget_seconds(payload)


def wait_timeout_ms(payload: Dict[str, Any]) -> int | None:
    return delegation_policy_mapping_helpers_runtime_service.wait_timeout_ms(payload)


def normalize_spawn_agent_role(value: Any, *, role_values: Tuple[str, ...]) -> str:
    return delegation_policy_mapping_helpers_runtime_service.normalize_spawn_agent_role(value, role_values=role_values)


def resolve_spawn_agent_async_mode(
    arguments: Dict[str, Any] | None,
    *,
    async_mode: bool | None = None,
    role: str | None = None,
    delegation_mode_values: Tuple[str, ...],
    role_values: Tuple[str, ...],
) -> bool:
    return delegation_policy_mapping_helpers_runtime_service.resolve_spawn_agent_async_mode(
        arguments,
        async_mode=async_mode,
        role=role,
        delegation_mode_values=delegation_mode_values,
        role_values=role_values,
    )


def normalize_spawn_agent_metadata(
    arguments: Dict[str, Any] | None,
    *,
    async_mode: bool | None = None,
    role: str | None = None,
    reason_codes: Tuple[str, ...],
    delegation_mode_values: Tuple[str, ...],
    task_shapes: Tuple[str, ...],
    role_values: Tuple[str, ...],
) -> Dict[str, Any]:
    return delegation_policy_mapping_helpers_runtime_service.normalize_spawn_agent_metadata(
        arguments,
        async_mode=async_mode,
        role=role,
        reason_codes=reason_codes,
        delegation_mode_values=delegation_mode_values,
        task_shapes=task_shapes,
        role_values=role_values,
    )


def normalize_wait_agent_metadata(
    arguments: Dict[str, Any] | None,
    *,
    wait_reason_codes: Tuple[str, ...],
) -> Dict[str, Any]:
    return delegation_policy_mapping_helpers_runtime_service.normalize_wait_agent_metadata(
        arguments,
        wait_reason_codes=wait_reason_codes,
    )


def normalize_recover_agent_metadata(
    arguments: Dict[str, Any] | None,
    *,
    recovery_action_values: Tuple[str, ...],
) -> Dict[str, Any]:
    return delegation_policy_mapping_helpers_runtime_service.normalize_recover_agent_metadata(
        arguments,
        recovery_action_values=recovery_action_values,
    )


def infer_spawn_agent_metadata(
    arguments: Dict[str, Any] | None,
    *,
    async_mode: bool | None = None,
    role: str | None = None,
    reason_codes: Tuple[str, ...],
    delegation_mode_values: Tuple[str, ...],
    task_shapes: Tuple[str, ...],
    role_values: Tuple[str, ...],
) -> Dict[str, Any]:
    return delegation_policy_planner_mapping_runtime.infer_spawn_agent_metadata(
        arguments,
        async_mode=async_mode,
        role=role,
        reason_codes=reason_codes,
        delegation_mode_values=delegation_mode_values,
        task_shapes=task_shapes,
        role_values=role_values,
        normalize_spawn_agent_role_fn=normalize_spawn_agent_role,
        spawn_task_text_fn=delegation_policy_runtime_service.spawn_task_text,
        argument_is_supplied_fn=argument_is_supplied,
        resolve_spawn_agent_async_mode_fn=resolve_spawn_agent_async_mode,
        normalize_spawn_agent_metadata_fn=normalize_spawn_agent_metadata,
        infer_task_shape_fn=delegation_policy_runtime_service.infer_task_shape,
        infer_task_reason_fn=delegation_policy_runtime_service.infer_task_reason,
    )


def apply_planner_delegation_defaults(
    tool_name: str,
    arguments: Dict[str, Any] | None,
    *,
    reason_codes: Tuple[str, ...],
    wait_reason_codes: Tuple[str, ...],
    recovery_action_values: Tuple[str, ...],
    delegation_mode_values: Tuple[str, ...],
    task_shapes: Tuple[str, ...],
    role_values: Tuple[str, ...],
) -> Dict[str, Any]:
    canonical_tool_name = _canonical_planner_tool_name(tool_name)
    canonical_arguments = _canonicalized_tool_arguments(tool_name, arguments)
    return delegation_policy_planner_mapping_runtime.apply_planner_delegation_defaults(
        canonical_tool_name,
        canonical_arguments,
        reason_codes=reason_codes,
        wait_reason_codes=wait_reason_codes,
        recovery_action_values=recovery_action_values,
        delegation_mode_values=delegation_mode_values,
        task_shapes=task_shapes,
        role_values=role_values,
        normalize_spawn_agent_role_fn=normalize_spawn_agent_role,
        normalized_bool_fn=normalized_bool,
        argument_is_supplied_fn=argument_is_supplied,
        infer_spawn_agent_metadata_fn=infer_spawn_agent_metadata,
        resolve_spawn_agent_async_mode_fn=resolve_spawn_agent_async_mode,
        normalize_wait_agent_metadata_fn=normalize_wait_agent_metadata,
        normalize_recover_agent_metadata_fn=normalize_recover_agent_metadata,
    )


def planner_tool_execution_target(
    tool_name: str,
    arguments: Dict[str, Any] | None,
    *,
    reason_codes: Tuple[str, ...],
    wait_reason_codes: Tuple[str, ...],
    recovery_action_values: Tuple[str, ...],
    delegation_mode_values: Tuple[str, ...],
    task_shapes: Tuple[str, ...],
    role_values: Tuple[str, ...],
) -> tuple[str, Dict[str, Any]]:
    canonical_tool_name = _canonical_planner_tool_name(tool_name)
    canonical_arguments = _canonicalized_tool_arguments(tool_name, arguments)
    return delegation_policy_planner_mapping_runtime.planner_tool_execution_target(
        canonical_tool_name,
        canonical_arguments,
        reason_codes=reason_codes,
        wait_reason_codes=wait_reason_codes,
        recovery_action_values=recovery_action_values,
        delegation_mode_values=delegation_mode_values,
        task_shapes=task_shapes,
        role_values=role_values,
        apply_planner_delegation_defaults_fn=apply_planner_delegation_defaults,
        normalize_wait_agent_metadata_fn=normalize_wait_agent_metadata,
    )


def planner_trace_delegation_summary(
    tool_calls: Iterable[Any],
    *,
    reason_codes: Tuple[str, ...],
    wait_reason_codes: Tuple[str, ...],
    recovery_action_values: Tuple[str, ...],
    delegation_mode_values: Tuple[str, ...],
    task_shapes: Tuple[str, ...],
    role_values: Tuple[str, ...],
    planner_defaulted_fields_fn: Callable[..., list[str]],
    planner_policy_basis_fn: Callable[..., str],
) -> Dict[str, Any]:
    summary = delegation_policy_planner_mapping_runtime.planner_trace_delegation_summary(
        _canonicalized_tool_calls(tool_calls),
        reason_codes=reason_codes,
        wait_reason_codes=wait_reason_codes,
        recovery_action_values=recovery_action_values,
        delegation_mode_values=delegation_mode_values,
        task_shapes=task_shapes,
        role_values=role_values,
        apply_planner_delegation_defaults_fn=apply_planner_delegation_defaults,
        planner_tool_execution_target_fn=planner_tool_execution_target,
        planner_defaulted_fields_fn=planner_defaulted_fields_fn,
        planner_policy_basis_fn=planner_policy_basis_fn,
        resolve_spawn_agent_async_mode_fn=resolve_spawn_agent_async_mode,
        timeout_budget_seconds_fn=timeout_budget_seconds,
        wait_timeout_ms_fn=wait_timeout_ms,
    )
    actions = summary.get("delegation_actions")
    if isinstance(actions, list):
        for item in actions:
            if not isinstance(item, dict):
                continue
            execution_mode = _action_execution_mode(item)
            if execution_mode and not str(item.get("execution_mode") or "").strip():
                item["execution_mode"] = execution_mode
    execution_mode, execution_reason = _delegation_execution_mode_and_reason(summary)
    if execution_mode and not str(summary.get("delegation_execution_mode") or "").strip():
        summary["delegation_execution_mode"] = execution_mode
    if execution_reason and not str(summary.get("delegation_execution_reason") or "").strip():
        summary["delegation_execution_reason"] = execution_reason
    return summary


__all__ = [
    "normalized_enum",
    "normalized_bool",
    "argument_is_supplied",
    "normalized_number",
    "normalized_int",
    "timeout_budget_seconds",
    "wait_timeout_ms",
    "normalize_spawn_agent_role",
    "resolve_spawn_agent_async_mode",
    "normalize_spawn_agent_metadata",
    "normalize_wait_agent_metadata",
    "normalize_recover_agent_metadata",
    "infer_spawn_agent_metadata",
    "apply_planner_delegation_defaults",
    "planner_tool_execution_target",
    "planner_trace_delegation_summary",
]

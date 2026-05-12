from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from .delegation_policy_planner_mapping_helpers import build_planner_trace_summary


def infer_spawn_agent_metadata(
    arguments: dict[str, Any] | None,
    *,
    async_mode: bool | None,
    role: str | None,
    reason_codes: tuple[str, ...],
    delegation_mode_values: tuple[str, ...],
    task_shapes: tuple[str, ...],
    role_values: tuple[str, ...],
    normalize_spawn_agent_role_fn: Callable[..., str],
    spawn_task_text_fn: Callable[[dict[str, Any] | None], str],
    argument_is_supplied_fn: Callable[[dict[str, Any], str], bool],
    resolve_spawn_agent_async_mode_fn: Callable[..., bool],
    normalize_spawn_agent_metadata_fn: Callable[..., dict[str, Any]],
    infer_task_shape_fn: Callable[[str], str],
    infer_task_reason_fn: Callable[[str, str], str],
) -> dict[str, Any]:
    payload = dict(arguments or {})
    normalized_role = normalize_spawn_agent_role_fn(
        role or payload.get("role") or payload.get("agent_type"),
        role_values=role_values,
    )
    task_text = spawn_task_text_fn(payload)
    explicit_async_supplied = async_mode is not None or argument_is_supplied_fn(payload, "async")
    explicit_mode_supplied = argument_is_supplied_fn(payload, "mode") or argument_is_supplied_fn(
        payload, "delegation_mode"
    )
    effective_async_mode = resolve_spawn_agent_async_mode_fn(
        payload,
        async_mode=async_mode,
        role=normalized_role,
        delegation_mode_values=delegation_mode_values,
        role_values=role_values,
    )
    if not task_text:
        return normalize_spawn_agent_metadata_fn(
            payload,
            async_mode=async_mode,
            role=normalized_role,
            reason_codes=reason_codes,
            delegation_mode_values=delegation_mode_values,
            task_shapes=task_shapes,
            role_values=role_values,
        )

    inferred_shape = infer_task_shape_fn(task_text)
    inferred_reason = infer_task_reason_fn(task_text, inferred_shape)
    if not explicit_async_supplied and not explicit_mode_supplied:
        if inferred_shape in {"workspace_mutating", "context_sensitive"}:
            effective_async_mode = False
        elif inferred_shape == "long_running":
            effective_async_mode = True

    return normalize_spawn_agent_metadata_fn(
        {
            "reason": payload.get("reason") or payload.get("delegation_reason") or inferred_reason,
            "mode": payload.get("mode")
            or payload.get("delegation_mode")
            or ("background" if effective_async_mode else "sync"),
            "wait_required": (
                payload.get("wait_required")
                if argument_is_supplied_fn(payload, "wait_required")
                else False
            ),
            "task_shape": payload.get("task_shape") or inferred_shape,
            "subagent_type": payload.get("subagent_type"),
        },
        async_mode=effective_async_mode,
        role=normalized_role,
        reason_codes=reason_codes,
        delegation_mode_values=delegation_mode_values,
        task_shapes=task_shapes,
        role_values=role_values,
    )


def apply_planner_delegation_defaults(
    tool_name: str,
    arguments: dict[str, Any] | None,
    *,
    reason_codes: tuple[str, ...],
    wait_reason_codes: tuple[str, ...],
    recovery_action_values: tuple[str, ...],
    delegation_mode_values: tuple[str, ...],
    task_shapes: tuple[str, ...],
    role_values: tuple[str, ...],
    normalize_spawn_agent_role_fn: Callable[..., str],
    normalized_bool_fn: Callable[[Any], bool | None],
    argument_is_supplied_fn: Callable[[dict[str, Any], str], bool],
    infer_spawn_agent_metadata_fn: Callable[..., dict[str, Any]],
    resolve_spawn_agent_async_mode_fn: Callable[..., bool],
    normalize_wait_agent_metadata_fn: Callable[..., dict[str, Any]],
    normalize_recover_agent_metadata_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    payload = dict(arguments or {})
    normalized_name = str(tool_name or "").strip()
    if normalized_name == "spawn_agent":
        normalized_role = normalize_spawn_agent_role_fn(
            payload.get("role") or payload.get("agent_type"), role_values=role_values
        )
        explicit_async_mode = (
            normalized_bool_fn(payload.get("async")) if "async" in payload else None
        )
        explicit_mode_supplied = argument_is_supplied_fn(
            payload, "mode"
        ) or argument_is_supplied_fn(payload, "delegation_mode")
        metadata = infer_spawn_agent_metadata_fn(
            payload,
            async_mode=explicit_async_mode,
            role=normalized_role,
            reason_codes=reason_codes,
            delegation_mode_values=delegation_mode_values,
            task_shapes=task_shapes,
            role_values=role_values,
        )
        if explicit_async_mode is not None:
            effective_async_mode = explicit_async_mode
        elif explicit_mode_supplied:
            effective_async_mode = resolve_spawn_agent_async_mode_fn(
                payload,
                async_mode=None,
                role=normalized_role,
                delegation_mode_values=delegation_mode_values,
                role_values=role_values,
            )
        else:
            effective_async_mode = (
                str(metadata.get("delegation_mode") or "").strip() == "background"
            )
        if explicit_async_mode is not None:
            payload["async"] = explicit_async_mode
        elif "async" not in payload and not explicit_mode_supplied and effective_async_mode:
            payload["async"] = True
        if metadata.get("delegation_reason") and not str(payload.get("reason") or "").strip():
            payload["reason"] = metadata["delegation_reason"]
        if metadata.get("delegation_mode") and not str(payload.get("mode") or "").strip():
            payload["mode"] = metadata["delegation_mode"]
        if "wait_required" in metadata and (
            "wait_required" not in payload or payload.get("wait_required") is None
        ):
            payload["wait_required"] = metadata["wait_required"]
        if metadata.get("task_shape") and not str(payload.get("task_shape") or "").strip():
            payload["task_shape"] = metadata["task_shape"]
        if metadata.get("subagent_type") and not str(payload.get("subagent_type") or "").strip():
            payload["subagent_type"] = metadata["subagent_type"]
        return payload
    if normalized_name == "wait_agent":
        metadata = normalize_wait_agent_metadata_fn(payload, wait_reason_codes=wait_reason_codes)
        if not metadata.get("wait_reason"):
            metadata["wait_reason"] = "wait_for_child_result"
        if metadata.get("wait_reason") and not str(payload.get("reason") or "").strip():
            payload["reason"] = metadata["wait_reason"]
        if "wait_required" in metadata and (
            "wait_required" not in payload or payload.get("wait_required") is None
        ):
            payload["wait_required"] = metadata["wait_required"]
        return payload
    if normalized_name in {"agent_workflow", "recover_agent"}:
        target = str(
            payload.get("target") or payload.get("agent_id") or payload.get("id") or ""
        ).strip()
        if target and not str(payload.get("target") or "").strip():
            payload["target"] = target
        if normalized_name == "recover_agent":
            metadata = normalize_recover_agent_metadata_fn(
                payload, recovery_action_values=recovery_action_values
            )
            if metadata.get("recovery_action") and not str(payload.get("action") or "").strip():
                payload["action"] = metadata["recovery_action"]
            if metadata.get("step_id") and not str(payload.get("step_id") or "").strip():
                payload["step_id"] = metadata["step_id"]
        return payload
    return payload


def planner_tool_execution_target(
    tool_name: str,
    arguments: dict[str, Any] | None,
    *,
    reason_codes: tuple[str, ...],
    wait_reason_codes: tuple[str, ...],
    recovery_action_values: tuple[str, ...],
    delegation_mode_values: tuple[str, ...],
    task_shapes: tuple[str, ...],
    role_values: tuple[str, ...],
    apply_planner_delegation_defaults_fn: Callable[..., dict[str, Any]],
    normalize_wait_agent_metadata_fn: Callable[..., dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    normalized_name = str(tool_name or "").strip()
    payload = apply_planner_delegation_defaults_fn(
        normalized_name,
        arguments,
        reason_codes=reason_codes,
        wait_reason_codes=wait_reason_codes,
        recovery_action_values=recovery_action_values,
        delegation_mode_values=delegation_mode_values,
        task_shapes=task_shapes,
        role_values=role_values,
    )
    if normalized_name == "wait_agent":
        metadata = normalize_wait_agent_metadata_fn(payload, wait_reason_codes=wait_reason_codes)
        target = str(
            payload.get("target") or payload.get("agent_id") or payload.get("id") or ""
        ).strip()
        if target and metadata.get("wait_required") is False:
            return ("agent_workflow", {"target": target})
    return (normalized_name, payload)


def planner_trace_delegation_summary(
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
    return build_planner_trace_summary(
        tool_calls,
        reason_codes=reason_codes,
        wait_reason_codes=wait_reason_codes,
        recovery_action_values=recovery_action_values,
        delegation_mode_values=delegation_mode_values,
        task_shapes=task_shapes,
        role_values=role_values,
        apply_planner_delegation_defaults_fn=apply_planner_delegation_defaults_fn,
        planner_tool_execution_target_fn=planner_tool_execution_target_fn,
        planner_defaulted_fields_fn=planner_defaulted_fields_fn,
        planner_policy_basis_fn=planner_policy_basis_fn,
        resolve_spawn_agent_async_mode_fn=resolve_spawn_agent_async_mode_fn,
        timeout_budget_seconds_fn=timeout_budget_seconds_fn,
        wait_timeout_ms_fn=wait_timeout_ms_fn,
    )

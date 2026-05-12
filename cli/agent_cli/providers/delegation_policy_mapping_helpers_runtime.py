from __future__ import annotations

from typing import Any

from cli.agent_cli import builtin_agent_profiles_runtime


def _normalized_trace_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def _orchestration_execution_mode_and_reason(summary: dict[str, Any]) -> tuple[str, str]:
    decision = (
        str(
            summary.get("delegation_policy_decision") or summary.get("orchestration_decision") or ""
        )
        .strip()
        .lower()
    )
    if not decision or decision in {"stay_local", "none"}:
        return ("", "")
    task_shape = str(summary.get("task_shape") or "").strip().lower()
    if task_shape in {"workspace_mutating", "context_sensitive"}:
        return ("serial", f"task_shape:{task_shape}")
    if task_shape in {"long_running", "read_only"}:
        return ("parallel", f"task_shape:{task_shape}")
    wait_required = _normalized_trace_bool(summary.get("wait_required"))
    if wait_required is True:
        return ("serial", "wait_required:true")
    if wait_required is False and decision in {"wait_later", "delegate_async", "delegate"}:
        return ("parallel", "wait_required:false")
    delegation_mode = str(summary.get("delegation_mode") or "").strip().lower()
    if delegation_mode == "sync":
        return ("serial", "delegation_mode:sync")
    if delegation_mode == "background":
        return ("parallel", "delegation_mode:background")
    if decision in {
        "delegate_sync",
        "wait_now",
        "delegate_and_wait",
        "resume_child",
        "close_child",
    }:
        return ("serial", f"decision:{decision}")
    if decision in {"delegate_async", "wait_later", "delegate", "wait", "retry_child"}:
        return ("parallel", f"decision:{decision}")
    return ("", "")


def _action_execution_mode(action: dict[str, Any]) -> str:
    tool_name = str(action.get("tool_name") or "").strip().lower()
    if tool_name == "spawn_agent":
        async_mode = _normalized_trace_bool(action.get("async"))
        if async_mode is not None:
            return "parallel" if async_mode else "serial"
        planner_policy = str(action.get("planner_policy") or "").strip().lower()
        if planner_policy == "delegate_sync":
            return "serial"
        if planner_policy in {"delegate_async", "delegate"}:
            return "parallel"
        return ""
    if tool_name == "wait_agent":
        wait_required = _normalized_trace_bool(action.get("wait_required"))
        if wait_required is not None:
            return "serial" if wait_required else "parallel"
        planner_policy = str(action.get("planner_policy") or "").strip().lower()
        if planner_policy == "wait_now":
            return "serial"
        if planner_policy == "wait_later":
            return "parallel"
        return ""
    if tool_name == "agent_workflow":
        return "parallel"
    if tool_name == "recover_agent":
        return "serial"
    return ""


def normalized_enum(value: Any, allowed: tuple[str, ...]) -> str | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    return text if text in allowed else None


def normalized_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def argument_is_supplied(payload: dict[str, Any], key: str) -> bool:
    if key not in payload:
        return False
    value = payload.get(key)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def normalized_number(value: Any) -> int | float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
    if number != number:
        return None
    if number.is_integer():
        return int(number)
    return number


def normalized_int(value: Any) -> int | None:
    number = normalized_number(value)
    if number is None:
        return None
    try:
        return int(number)
    except (TypeError, ValueError):
        return None


def timeout_budget_seconds(payload: dict[str, Any]) -> int | float | None:
    for field_name in ("timeout_budget_seconds", "timeout_seconds", "timeout_sec", "timeout"):
        value = normalized_number(payload.get(field_name))
        if value is not None:
            return value
    return None


def wait_timeout_ms(payload: dict[str, Any]) -> int | None:
    for field_name in ("wait_timeout_ms", "timeout_ms"):
        value = normalized_int(payload.get(field_name))
        if value is not None:
            return value
    return None


def normalize_spawn_agent_role(value: Any, *, role_values: tuple[str, ...]) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in role_values else "subagent"


def resolve_spawn_agent_async_mode(
    arguments: dict[str, Any] | None,
    *,
    async_mode: bool | None = None,
    role: str | None = None,
    delegation_mode_values: tuple[str, ...],
    role_values: tuple[str, ...],
) -> bool:
    if async_mode is not None:
        return bool(async_mode)
    payload = dict(arguments or {})
    if bool(payload.get("codex_collab_payload")):
        return True
    explicit_async = normalized_bool(payload.get("async"))
    if explicit_async is not None:
        return explicit_async
    explicit_mode = normalized_enum(
        payload.get("mode") or payload.get("delegation_mode"),
        delegation_mode_values,
    )
    if explicit_mode == "background":
        return True
    if explicit_mode == "sync":
        return False
    normalized_role = normalize_spawn_agent_role(
        role or payload.get("role") or payload.get("agent_type"),
        role_values=role_values,
    )
    return normalized_role == "teammate"


def normalize_spawn_agent_metadata(
    arguments: dict[str, Any] | None,
    *,
    async_mode: bool | None = None,
    role: str | None = None,
    reason_codes: tuple[str, ...],
    delegation_mode_values: tuple[str, ...],
    task_shapes: tuple[str, ...],
    role_values: tuple[str, ...],
) -> dict[str, Any]:
    payload = dict(arguments or {})
    metadata: dict[str, Any] = {}
    normalized_role = normalize_spawn_agent_role(
        role or payload.get("role") or payload.get("agent_type"),
        role_values=role_values,
    )
    effective_async_mode = resolve_spawn_agent_async_mode(
        payload,
        async_mode=async_mode,
        role=normalized_role,
        delegation_mode_values=delegation_mode_values,
        role_values=role_values,
    )
    reason = normalized_enum(
        payload.get("reason") or payload.get("delegation_reason"), reason_codes
    )
    mode = normalized_enum(
        payload.get("mode") or payload.get("delegation_mode"),
        delegation_mode_values,
    )
    task_shape = normalized_enum(payload.get("task_shape"), task_shapes)
    subagent_type = builtin_agent_profiles_runtime.normalize_subagent_type(
        payload.get("subagent_type")
    )
    wait_required = normalized_bool(payload.get("wait_required"))
    if mode is None:
        mode = "background" if effective_async_mode else "sync"
    if reason:
        metadata["delegation_reason"] = reason
    if mode:
        metadata["delegation_mode"] = mode
    if task_shape:
        metadata["task_shape"] = task_shape
    if subagent_type:
        metadata["subagent_type"] = subagent_type
    if wait_required is not None:
        metadata["wait_required"] = wait_required
    elif mode == "sync" or normalized_role == "teammate":
        metadata["wait_required"] = False
    return metadata


def normalize_wait_agent_metadata(
    arguments: dict[str, Any] | None,
    *,
    wait_reason_codes: tuple[str, ...],
) -> dict[str, Any]:
    payload = dict(arguments or {})
    metadata: dict[str, Any] = {}
    reason = normalized_enum(payload.get("reason") or payload.get("wait_reason"), wait_reason_codes)
    wait_required = normalized_bool(payload.get("wait_required"))
    if reason:
        metadata["wait_reason"] = reason
    if wait_required is not None:
        metadata["wait_required"] = wait_required
    else:
        metadata["wait_required"] = True
    return metadata


def normalize_recover_agent_metadata(
    arguments: dict[str, Any] | None,
    *,
    recovery_action_values: tuple[str, ...],
) -> dict[str, Any]:
    payload = dict(arguments or {})
    metadata: dict[str, Any] = {}
    action = normalized_enum(
        payload.get("action") or payload.get("recovery_action"),
        recovery_action_values,
    )
    metadata["recovery_action"] = action or "retry_step"
    step_id = str(payload.get("step_id") or payload.get("step") or "").strip()
    if step_id:
        metadata["step_id"] = step_id
    return metadata

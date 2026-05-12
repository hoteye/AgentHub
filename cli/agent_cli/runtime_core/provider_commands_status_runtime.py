from __future__ import annotations

from typing import Any


def status_text(status: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(status.get(key) or "").strip()
        if value and value != "-":
            return value
    return ""


def status_bool(status: dict[str, Any], key: str) -> bool | None:
    if key not in status:
        return None
    value = status.get(key)
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def infer_execution_mode(status: dict[str, Any]) -> str:
    explicit = status_text(status, "delegation_execution_mode", "orchestration_execution_mode")
    if explicit:
        return explicit
    task_shape = status_text(status, "task_shape").lower()
    if task_shape in {"workspace_mutating", "context_sensitive"}:
        return "serial"
    if task_shape in {"long_running", "read_only"}:
        return "parallel"
    wait_required = status_bool(status, "wait_required")
    if wait_required is True:
        return "serial"
    if wait_required is False:
        return "parallel"
    delegation_mode = status_text(status, "delegation_mode").lower()
    if delegation_mode == "sync":
        return "serial"
    if delegation_mode == "background":
        return "parallel"
    decision = status_text(status, "delegation_policy_decision", "orchestration_decision").lower()
    if decision in {"delegate_sync", "wait_now", "delegate_and_wait", "resume_child", "close_child"}:
        return "serial"
    if decision in {"delegate_async", "wait_later", "delegate", "wait", "retry_child"}:
        return "parallel"
    return ""


def orchestration_reason_surface(status: dict[str, Any]) -> str:
    decision = status_text(status, "delegation_policy_decision", "orchestration_decision")
    policy_reason = status_text(status, "delegation_policy_reason", "orchestration_policy_reason")
    execution_mode = infer_execution_mode(status)
    execution_reason = status_text(status, "delegation_execution_reason", "orchestration_execution_reason")
    delegation_reason = status_text(status, "delegation_reason")
    wait_reason = status_text(status, "wait_reason", "last_wait_reason")
    scheduler_reason = status_text(status, "scheduler_reason")
    task_shape = status_text(status, "task_shape")
    wait_required = status_bool(status, "wait_required")
    parts: list[str] = []
    if decision:
        parts.append(f"decision={decision}")
    if execution_mode:
        parts.append(f"execution={execution_mode}")
    if policy_reason:
        parts.append(f"policy_reason={policy_reason}")
    if execution_reason and execution_reason != policy_reason:
        parts.append(f"mode_reason={execution_reason}")
    if delegation_reason:
        parts.append(f"delegation_reason={delegation_reason}")
    if wait_reason:
        parts.append(f"wait_reason={wait_reason}")
    if scheduler_reason:
        parts.append(f"scheduler_reason={scheduler_reason}")
    if task_shape:
        parts.append(f"task_shape={task_shape}")
    if wait_required is not None:
        parts.append(f"wait_required={'true' if wait_required else 'false'}")
    return "; ".join(parts)


def orchestration_budget_surface(status: dict[str, Any]) -> str:
    strategy = status_text(status, "delegation_strategy", "orchestration_strategy")
    strategy_reason = status_text(status, "delegation_strategy_reason", "orchestration_strategy_reason")
    strategy_source = status_text(status, "delegation_strategy_source", "orchestration_strategy_source")
    budget_source = status_text(status, "delegation_budget_source", "orchestration_budget_source")
    observation_source = status_text(status, "delegation_observation_source", "orchestration_observation_source")
    timeout_reason = status_text(status, "delegation_timeout_reason", "orchestration_timeout_reason", "timeout_reason")
    timeout_budget_seconds = status_text(status, "timeout_budget_seconds")
    wait_timeout_ms = status_text(status, "wait_timeout_ms")
    wait_observed_ms = status_text(status, "delegation_wait_observed_ms", "orchestration_wait_observed_ms")
    budget_snapshot = status.get("delegation_budget_snapshot")
    if not isinstance(budget_snapshot, dict):
        budget_snapshot = status.get("orchestration_budget_snapshot")
    if isinstance(budget_snapshot, dict):
        if not timeout_budget_seconds:
            timeout_budget_seconds = str(budget_snapshot.get("timeout_budget_seconds") or "").strip()
        if not wait_timeout_ms:
            wait_timeout_ms = str(budget_snapshot.get("wait_timeout_ms") or "").strip()
        if not wait_observed_ms:
            wait_observed_ms = str(budget_snapshot.get("wait_observed_ms") or "").strip()
    continue_main_thread = status_bool(status, "delegation_continue_main_thread")
    if continue_main_thread is None:
        continue_main_thread = status_bool(status, "orchestration_continue_delegation")
    budget_hit = status_bool(status, "delegation_budget_hit")
    if budget_hit is None:
        budget_hit = status_bool(status, "orchestration_budget_hit")
    parts: list[str] = []
    if strategy:
        parts.append(f"strategy={strategy}")
    if strategy_reason:
        parts.append(f"reason={strategy_reason}")
    if strategy_source:
        parts.append(f"strategy_source={strategy_source}")
    if budget_source:
        parts.append(f"budget_source={budget_source}")
    if observation_source:
        parts.append(f"observation_source={observation_source}")
    if timeout_reason:
        parts.append(f"timeout_reason={timeout_reason}")
    if timeout_budget_seconds:
        parts.append(f"timeout_budget_seconds={timeout_budget_seconds}")
    if wait_timeout_ms:
        parts.append(f"wait_timeout_ms={wait_timeout_ms}")
    if wait_observed_ms:
        parts.append(f"wait_observed_ms={wait_observed_ms}")
    if continue_main_thread is not None:
        parts.append(f"continue_main_thread={'true' if continue_main_thread else 'false'}")
    if budget_hit is not None:
        parts.append(f"budget_hit={'true' if budget_hit else 'false'}")
    return "; ".join(parts)

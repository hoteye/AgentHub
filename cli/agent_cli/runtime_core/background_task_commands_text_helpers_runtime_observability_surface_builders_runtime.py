from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_core.background_task_commands_text_helpers_runtime_observability_budget_surface_runtime import (
    orchestration_budget_surface_impl,
)
from cli.agent_cli.runtime_core.background_task_commands_text_helpers_runtime_observability_trace_values_runtime import (
    observability_value_impl,
    trace_bool_impl,
)

__all__ = [
    "infer_execution_mode_impl",
    "orchestration_budget_surface_impl",
    "orchestration_reason_surface_impl",
]


def infer_execution_mode_impl(
    *,
    artifact: dict[str, Any],
    payload: dict[str, Any],
    trace_payload: dict[str, Any],
) -> str:
    explicit = observability_value_impl(
        "delegation_execution_mode",
        artifact=artifact,
        payload=payload,
        trace_payload=trace_payload,
    ) or observability_value_impl(
        "orchestration_execution_mode",
        artifact=artifact,
        payload=payload,
        trace_payload=trace_payload,
    )
    explicit_text = str(explicit or "").strip()
    if explicit_text:
        return explicit_text
    task_shape = (
        str(
            observability_value_impl(
                "task_shape",
                artifact=artifact,
                payload=payload,
                trace_payload=trace_payload,
            )
            or ""
        )
        .strip()
        .lower()
    )
    if task_shape in {"workspace_mutating", "context_sensitive"}:
        return "serial"
    if task_shape in {"long_running", "read_only"}:
        return "parallel"
    wait_required = trace_bool_impl(
        observability_value_impl(
            "wait_required",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
    )
    if wait_required is True:
        return "serial"
    if wait_required is False:
        return "parallel"
    delegation_mode = (
        str(
            observability_value_impl(
                "delegation_mode",
                artifact=artifact,
                payload=payload,
                trace_payload=trace_payload,
            )
            or ""
        )
        .strip()
        .lower()
    )
    if delegation_mode == "sync":
        return "serial"
    if delegation_mode == "background":
        return "parallel"
    decision = (
        str(
            observability_value_impl(
                "delegation_policy_decision",
                artifact=artifact,
                payload=payload,
                trace_payload=trace_payload,
            )
            or observability_value_impl(
                "orchestration_decision",
                artifact=artifact,
                payload=payload,
                trace_payload=trace_payload,
            )
            or ""
        )
        .strip()
        .lower()
    )
    if decision in {
        "delegate_sync",
        "wait_now",
        "delegate_and_wait",
        "resume_child",
        "close_child",
    }:
        return "serial"
    if decision in {"delegate_async", "wait_later", "delegate", "wait", "retry_child"}:
        return "parallel"
    return ""


def orchestration_reason_surface_impl(
    *,
    artifact: dict[str, Any],
    payload: dict[str, Any],
    trace_payload: dict[str, Any],
) -> str:
    decision = str(
        observability_value_impl(
            "delegation_policy_decision",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or observability_value_impl(
            "orchestration_decision",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or ""
    ).strip()
    policy_reason = str(
        observability_value_impl(
            "delegation_policy_reason",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or observability_value_impl(
            "orchestration_policy_reason",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or ""
    ).strip()
    execution_mode = infer_execution_mode_impl(
        artifact=artifact, payload=payload, trace_payload=trace_payload
    )
    execution_reason = str(
        observability_value_impl(
            "delegation_execution_reason",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or observability_value_impl(
            "orchestration_execution_reason",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or ""
    ).strip()
    delegation_reason = str(
        observability_value_impl(
            "delegation_reason",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or ""
    ).strip()
    wait_reason = str(
        observability_value_impl(
            "wait_reason",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or observability_value_impl(
            "last_wait_reason",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or ""
    ).strip()
    scheduler_reason = str(
        observability_value_impl(
            "scheduler_reason",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or ""
    ).strip()
    task_shape = str(
        observability_value_impl(
            "task_shape",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or ""
    ).strip()
    wait_required = trace_bool_impl(
        observability_value_impl(
            "wait_required",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
    )
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

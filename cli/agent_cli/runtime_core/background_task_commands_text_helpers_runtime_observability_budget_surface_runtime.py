from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_core.background_task_commands_text_helpers_runtime_observability_trace_values_runtime import (
    observability_value_impl,
    trace_bool_impl,
)


def orchestration_budget_surface_impl(
    *,
    artifact: dict[str, Any],
    payload: dict[str, Any],
    trace_payload: dict[str, Any],
) -> str:
    strategy = str(
        observability_value_impl(
            "delegation_strategy",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or observability_value_impl(
            "orchestration_strategy",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or ""
    ).strip()
    strategy_reason = str(
        observability_value_impl(
            "delegation_strategy_reason",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or observability_value_impl(
            "orchestration_strategy_reason",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or ""
    ).strip()
    strategy_source = str(
        observability_value_impl(
            "delegation_strategy_source",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or observability_value_impl(
            "orchestration_strategy_source",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or ""
    ).strip()
    budget_source = str(
        observability_value_impl(
            "delegation_budget_source",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or observability_value_impl(
            "orchestration_budget_source",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or ""
    ).strip()
    observation_source = str(
        observability_value_impl(
            "delegation_observation_source",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or observability_value_impl(
            "orchestration_observation_source",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or ""
    ).strip()
    timeout_reason = str(
        observability_value_impl(
            "delegation_timeout_reason",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or observability_value_impl(
            "orchestration_timeout_reason",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or observability_value_impl(
            "timeout_reason",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or ""
    ).strip()
    timeout_budget_seconds = str(
        observability_value_impl(
            "timeout_budget_seconds",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or ""
    ).strip()
    wait_timeout_ms = str(
        observability_value_impl(
            "wait_timeout_ms",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or ""
    ).strip()
    wait_observed_ms = str(
        observability_value_impl(
            "delegation_wait_observed_ms",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or observability_value_impl(
            "orchestration_wait_observed_ms",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
        or ""
    ).strip()
    budget_snapshot = observability_value_impl(
        "delegation_budget_snapshot",
        artifact=artifact,
        payload=payload,
        trace_payload=trace_payload,
    )
    if not isinstance(budget_snapshot, dict):
        budget_snapshot = observability_value_impl(
            "orchestration_budget_snapshot",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
    if isinstance(budget_snapshot, dict):
        if not timeout_budget_seconds:
            timeout_budget_seconds = str(
                budget_snapshot.get("timeout_budget_seconds") or ""
            ).strip()
        if not wait_timeout_ms:
            wait_timeout_ms = str(budget_snapshot.get("wait_timeout_ms") or "").strip()
        if not wait_observed_ms:
            wait_observed_ms = str(budget_snapshot.get("wait_observed_ms") or "").strip()
    continue_main_thread = trace_bool_impl(
        observability_value_impl(
            "delegation_continue_main_thread",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
    )
    if continue_main_thread is None:
        continue_main_thread = trace_bool_impl(
            observability_value_impl(
                "orchestration_continue_delegation",
                artifact=artifact,
                payload=payload,
                trace_payload=trace_payload,
            )
        )
    budget_hit = trace_bool_impl(
        observability_value_impl(
            "delegation_budget_hit",
            artifact=artifact,
            payload=payload,
            trace_payload=trace_payload,
        )
    )
    if budget_hit is None:
        budget_hit = trace_bool_impl(
            observability_value_impl(
                "orchestration_budget_hit",
                artifact=artifact,
                payload=payload,
                trace_payload=trace_payload,
            )
        )
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

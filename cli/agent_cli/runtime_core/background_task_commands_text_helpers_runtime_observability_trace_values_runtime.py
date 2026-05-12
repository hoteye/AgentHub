from __future__ import annotations

from typing import Any


_OBSERVABILITY_KEY_FALLBACKS: dict[str, tuple[str, ...]] = {
    "delegation_policy_decision": ("orchestration_decision",),
    "delegation_policy_source": ("orchestration_policy_source",),
    "delegation_policy_reason": ("orchestration_policy_reason",),
    "delegation_execution_mode": ("orchestration_execution_mode",),
    "delegation_execution_reason": ("orchestration_execution_reason",),
    "delegation_strategy": ("orchestration_strategy",),
    "delegation_strategy_reason": ("orchestration_strategy_reason",),
    "delegation_strategy_source": ("orchestration_strategy_source",),
    "delegation_budget_source": ("orchestration_budget_source",),
    "delegation_observation_source": ("orchestration_observation_source",),
    "delegation_outcome": ("orchestration_outcome",),
    "delegation_timeout_reason": ("orchestration_timeout_reason",),
    "delegation_failure_reason": ("orchestration_failure_reason",),
    "delegation_continue_main_thread": ("orchestration_continue_delegation",),
    "delegation_budget_hit": ("orchestration_budget_hit",),
    "delegation_timeout_hit": ("orchestration_timeout_hit",),
    "delegation_cancelled": ("orchestration_cancelled",),
    "delegation_failed": ("orchestration_failed",),
    "delegation_outcomes": ("orchestration_outcomes",),
    "delegation_budget_fields": ("orchestration_budget_fields",),
    "delegation_budget_snapshot": ("orchestration_budget_snapshot",),
    "delegation_wait_observed_ms": ("orchestration_wait_observed_ms",),
}


def trace_bool_impl(value: Any) -> bool | None:
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


def observability_trace_from_route_report_impl(artifact: dict[str, Any]) -> dict[str, Any]:
    route_report = artifact.get("route_report")
    if isinstance(route_report, dict):
        for key in ("planning_trace", "orchestration_trace", "trace"):
            value = route_report.get(key)
            if isinstance(value, list):
                for item in reversed(value):
                    if isinstance(item, dict):
                        return dict(item)
            if isinstance(value, dict):
                return dict(value)
        if any(
            key in route_report
            for key in (
                "delegation_policy_decision",
                "delegation_strategy",
                "orchestration_decision",
                "orchestration_strategy",
                "delegation_decision",
            )
        ):
            return dict(route_report)
    if isinstance(route_report, list):
        for item in reversed(route_report):
            if isinstance(item, dict) and any(
                key in item
                for key in (
                    "delegation_policy_decision",
                    "delegation_strategy",
                    "orchestration_decision",
                    "orchestration_strategy",
                    "delegation_decision",
                )
            ):
                return dict(item)
    return {}


def observability_value_impl(
    key: str,
    *,
    artifact: dict[str, Any],
    payload: dict[str, Any],
    trace_payload: dict[str, Any],
) -> Any:
    candidate_keys = (key, *_OBSERVABILITY_KEY_FALLBACKS.get(key, ()))
    for source in (artifact, payload, trace_payload):
        if not isinstance(source, dict):
            continue
        for candidate_key in candidate_keys:
            if candidate_key in source:
                return source.get(candidate_key)
    return None

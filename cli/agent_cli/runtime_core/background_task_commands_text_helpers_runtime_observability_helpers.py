from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_core.background_task_commands_text_helpers_runtime_observability_surfaces_helpers import (
    append_observability_surface_lines_impl as _append_observability_surface_lines_impl,
    command_policy_surface_impl as _command_policy_surface_impl,
    infer_execution_mode_impl as _infer_execution_mode_impl,
    observability_trace_from_route_report_impl as _observability_trace_from_route_report_impl,
    observability_value_impl as _observability_value_impl,
    orchestration_budget_surface_impl as _orchestration_budget_surface_impl,
    orchestration_reason_surface_impl as _orchestration_reason_surface_impl,
    trace_bool_impl as _trace_bool_impl,
)


def trace_bool_impl(value: Any) -> bool | None:
    return _trace_bool_impl(value)


def observability_trace_from_route_report_impl(artifact: dict[str, Any]) -> dict[str, Any]:
    return _observability_trace_from_route_report_impl(artifact)


def observability_value_impl(
    key: str,
    *,
    artifact: dict[str, Any],
    payload: dict[str, Any],
    trace_payload: dict[str, Any],
) -> Any:
    return _observability_value_impl(
        key,
        artifact=artifact,
        payload=payload,
        trace_payload=trace_payload,
    )


def infer_execution_mode_impl(
    *,
    artifact: dict[str, Any],
    payload: dict[str, Any],
    trace_payload: dict[str, Any],
) -> str:
    return _infer_execution_mode_impl(
        artifact=artifact,
        payload=payload,
        trace_payload=trace_payload,
    )


def orchestration_reason_surface_impl(
    *,
    artifact: dict[str, Any],
    payload: dict[str, Any],
    trace_payload: dict[str, Any],
) -> str:
    return _orchestration_reason_surface_impl(
        artifact=artifact,
        payload=payload,
        trace_payload=trace_payload,
    )


def orchestration_budget_surface_impl(
    *,
    artifact: dict[str, Any],
    payload: dict[str, Any],
    trace_payload: dict[str, Any],
) -> str:
    return _orchestration_budget_surface_impl(
        artifact=artifact,
        payload=payload,
        trace_payload=trace_payload,
    )


def command_policy_surface_impl(value: Any) -> tuple[int, int, int, str]:
    return _command_policy_surface_impl(value)


def append_observability_surface_lines_impl(
    lines: list[str],
    *,
    artifact: dict[str, Any],
    payload: dict[str, Any],
    trace_payload: dict[str, Any],
) -> None:
    _append_observability_surface_lines_impl(
        lines,
        artifact=artifact,
        payload=payload,
        trace_payload=trace_payload,
    )

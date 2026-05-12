from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_core.background_task_commands_text_helpers_runtime_format_helpers import (
    append_bootstrap_lines_impl,
    append_lifecycle_lines_impl,
)
from cli.agent_cli.runtime_core.background_task_commands_text_helpers_runtime_observability_helpers import (
    append_observability_surface_lines_impl,
    command_policy_surface_impl,
    infer_execution_mode_impl,
    observability_trace_from_route_report_impl,
    observability_value_impl,
    orchestration_budget_surface_impl,
    orchestration_reason_surface_impl,
    trace_bool_impl,
)


def trace_bool(value: Any) -> bool | None:
    return trace_bool_impl(value)


def observability_trace_from_route_report(artifact: dict[str, Any]) -> dict[str, Any]:
    return observability_trace_from_route_report_impl(artifact)


def observability_value(
    key: str,
    *,
    artifact: dict[str, Any],
    payload: dict[str, Any],
    trace_payload: dict[str, Any],
) -> Any:
    return observability_value_impl(
        key,
        artifact=artifact,
        payload=payload,
        trace_payload=trace_payload,
    )


def _infer_execution_mode(
    *,
    artifact: dict[str, Any],
    payload: dict[str, Any],
    trace_payload: dict[str, Any],
) -> str:
    return infer_execution_mode_impl(
        artifact=artifact,
        payload=payload,
        trace_payload=trace_payload,
    )


def orchestration_reason_surface(
    *,
    artifact: dict[str, Any],
    payload: dict[str, Any],
    trace_payload: dict[str, Any],
) -> str:
    return orchestration_reason_surface_impl(
        artifact=artifact,
        payload=payload,
        trace_payload=trace_payload,
    )


def orchestration_budget_surface(
    *,
    artifact: dict[str, Any],
    payload: dict[str, Any],
    trace_payload: dict[str, Any],
) -> str:
    return orchestration_budget_surface_impl(
        artifact=artifact,
        payload=payload,
        trace_payload=trace_payload,
    )


def command_policy_surface(value: Any) -> tuple[int, int, int, str]:
    return command_policy_surface_impl(value)


def append_observability_surface_lines(
    lines: list[str],
    *,
    artifact: dict[str, Any],
    payload: dict[str, Any],
    trace_payload: dict[str, Any],
) -> None:
    append_observability_surface_lines_impl(
        lines,
        artifact=artifact,
        payload=payload,
        trace_payload=trace_payload,
    )


def append_lifecycle_lines(
    lines: list[str],
    *,
    lifecycle: dict[str, Any],
    payload: dict[str, Any],
    artifact: dict[str, Any],
) -> None:
    append_lifecycle_lines_impl(lines, lifecycle=lifecycle, payload=payload, artifact=artifact)


def append_bootstrap_lines(lines: list[str], *, bootstrap: dict[str, Any]) -> None:
    append_bootstrap_lines_impl(lines, bootstrap=bootstrap)

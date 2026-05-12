from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_core.background_task_commands_text_helpers_runtime_observability_surface_builders_runtime import (
    infer_execution_mode_impl,
    orchestration_budget_surface_impl,
    orchestration_reason_surface_impl,
)
from cli.agent_cli.runtime_core.background_task_commands_text_helpers_runtime_observability_trace_values_runtime import (
    observability_trace_from_route_report_impl,
    observability_value_impl,
    trace_bool_impl,
)


def command_policy_surface_impl(value: Any) -> tuple[int, int, int, str]:
    from cli.agent_cli.runtime_core.background_task_commands_text_helpers_runtime_observability_surfaces_lines_runtime import command_policy_surface_impl as _impl

    return _impl(value)


def append_observability_surface_lines_impl(
    lines: list[str], *, artifact: dict[str, Any], payload: dict[str, Any], trace_payload: dict[str, Any]
) -> None:
    from cli.agent_cli.runtime_core.background_task_commands_text_helpers_runtime_observability_surfaces_lines_runtime import append_observability_surface_lines_impl as _impl

    _impl(lines, artifact=artifact, payload=payload, trace_payload=trace_payload)

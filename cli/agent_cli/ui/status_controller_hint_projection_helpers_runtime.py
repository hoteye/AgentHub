from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.ui import status_controller_hint_surface_helpers_runtime as surface_hint_runtime
from cli.agent_cli.ui import status_controller_operator_runtime as operator_runtime


def projected_operator_surface_status(status_data: dict[str, Any]) -> dict[str, str]:
    projected = operator_runtime.merged_operator_key_values(status_data)
    evidence_snapshot = operator_runtime.operator_evidence_snapshot(projected)
    projected.update(
        {
            key: value
            for key, value in evidence_snapshot.items()
            if key in operator_runtime.OPERATOR_EVIDENCE_KEYS and value not in {"", "-"}
        }
    )
    primary_state = operator_runtime.normalized_status(
        projected.get("operator_evidence_lifecycle_state")
        or operator_runtime.operator_primary_state_from_mapping(projected)
    )
    workflow_state = operator_runtime.normalized_status(projected.get("workflow_state"))
    completion_state = operator_runtime.normalized_status(projected.get("completion_state"))
    adoption_expectation = operator_runtime.normalized_status(projected.get("adoption_expectation"))
    if workflow_state in {"completed", "failed", "cancelled", "timed_out"} and primary_state not in {
        "",
        workflow_state,
    }:
        projected["workflow_state"] = "-"
    if completion_state and primary_state in {"adopted", "blocked", "failed", "cancelled", "timed_out"}:
        if completion_state != primary_state:
            projected["completion_state"] = "-"
    if adoption_expectation and primary_state not in {"", "returned", "completed"}:
        projected["adoption_expectation"] = "-"
    return projected


def single_operator_result_hint(
    command_name: str,
    *,
    key_values: dict[str, str],
    tool_label_fn: Callable[[str], str],
    boolish_status_fn: Callable[[Any], bool | None],
    tenant_scope_parts_fn: Callable[..., list[str]],
    review_projection_state_fn: Callable[..., str],
) -> str:
    return surface_hint_runtime.single_operator_result_hint(
        command_name,
        key_values=projected_operator_surface_status(key_values),
        tool_label_fn=tool_label_fn,
        boolish_status_fn=boolish_status_fn,
        tenant_scope_parts_fn=tenant_scope_parts_fn,
        review_projection_state_fn=review_projection_state_fn,
    )


def build_projected_operator_surface_hint(
    status_data: dict[str, Any],
    *,
    width: int,
    short_fn: Callable[[str, int], str],
    crop_one_line_fn: Callable[[str, int], str],
    tool_label_fn: Callable[[str], str],
    boolish_status_fn: Callable[[Any], bool | None],
    tenant_scope_parts_fn: Callable[..., list[str]],
    review_projection_state_fn: Callable[..., str],
) -> str:
    return surface_hint_runtime.build_operator_surface_hint(
        projected_operator_surface_status(status_data),
        width=width,
        short_fn=short_fn,
        crop_one_line_fn=crop_one_line_fn,
        tool_label_fn=tool_label_fn,
        boolish_status_fn=boolish_status_fn,
        tenant_scope_parts_fn=tenant_scope_parts_fn,
        review_projection_state_fn=review_projection_state_fn,
    )

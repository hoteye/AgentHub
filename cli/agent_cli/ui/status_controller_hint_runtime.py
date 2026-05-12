from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.ui import status_controller_hint_normalization_helpers_runtime as normalization_hint_runtime
from cli.agent_cli.ui import status_controller_hint_projection_helpers_runtime as projection_hint_runtime
from cli.agent_cli.ui import status_controller_hint_pure_helpers_runtime as pure_hint_runtime
from cli.agent_cli.ui import status_controller_operator_runtime as operator_runtime
from cli.agent_cli.ui import status_controller_hint_helpers_runtime as hint_helpers
from cli.agent_cli.ui import (
    status_controller_hint_surface_helpers_runtime as surface_hint_runtime,
)
from cli.agent_cli.ui import status_controller_hint_workflows_runtime as workflow_hint_runtime

operator_hint_title = hint_helpers.operator_hint_title
_count_compact = hint_helpers.count_compact
_string_items_compact = hint_helpers.string_items_compact
_card_ids_compact = hint_helpers.card_ids_compact
_preview_items = hint_helpers.preview_items
_operator_next_command = hint_helpers.operator_next_command
_tenant_scope_parts = hint_helpers.tenant_scope_parts
_count_from_key_values = hint_helpers.count_from_key_values


def _workflows_orchestration_review_hint(
    assistant_text: Any, *, tool_label_fn: Callable[[str], str]
) -> str:
    return pure_hint_runtime.workflows_orchestration_review_hint(
        assistant_text,
        tool_label_fn=tool_label_fn,
        count_compact_fn=_count_compact,
        string_items_compact_fn=_string_items_compact,
        card_ids_compact_fn=_card_ids_compact,
        preview_items_fn=_preview_items,
        operator_next_command_fn=_operator_next_command,
        orchestration_next_command_fn=normalization_hint_runtime.orchestration_next_command,
    )


def _workflows_result_contract_hint(
    key_values: dict[str, str],
    *,
    normalized_count_fn: Callable[[Any], str],
) -> str:
    return workflow_hint_runtime.workflows_result_contract_hint(
        key_values,
        normalized_count_fn=normalized_count_fn,
        count_from_key_values_fn=_count_from_key_values,
    )


def _workflows_execution_projection_hint(
    key_values: dict[str, str],
    *,
    normalized_count_fn: Callable[[Any], str],
) -> str:
    return workflow_hint_runtime.workflows_execution_projection_hint(
        key_values,
        normalized_count_fn=normalized_count_fn,
        count_from_key_values_fn=_count_from_key_values,
    )


def _review_projection_state(
    *,
    result_state: Any,
    completion_state: Any,
    final_apply_state: Any,
) -> str:
    return normalization_hint_runtime.review_projection_state(
        result_state=result_state,
        completion_state=completion_state,
        final_apply_state=final_apply_state,
    )


def _single_operator_result_hint(
    command_name: str,
    *,
    key_values: dict[str, str],
    tool_label_fn: Callable[[str], str],
    boolish_status_fn: Callable[[Any], bool | None],
) -> str:
    return projection_hint_runtime.single_operator_result_hint(
        command_name,
        key_values=key_values,
        tool_label_fn=tool_label_fn,
        boolish_status_fn=boolish_status_fn,
        tenant_scope_parts_fn=_tenant_scope_parts,
        review_projection_state_fn=_review_projection_state,
    )


def operator_hint_from_command(
    command_name: str,
    *,
    key_values: dict[str, str],
    assistant_text: Any,
    normalized_count_fn: Callable[[Any], str],
    tool_label_fn: Callable[[str], str],
    flag_label_fn: Callable[[str], str],
) -> str:
    if command_name == "workflows":
        return pure_hint_runtime.workflows_command_hint(
            key_values=key_values,
            normalized_count_fn=normalized_count_fn,
            flag_label_fn=flag_label_fn,
            result_contract_hint=_workflows_result_contract_hint(
                key_values, normalized_count_fn=normalized_count_fn
            ),
            review_hint=_workflows_orchestration_review_hint(
                assistant_text, tool_label_fn=tool_label_fn
            ),
            execution_projection_hint=_workflows_execution_projection_hint(
                key_values, normalized_count_fn=normalized_count_fn
            ),
        )
    if command_name == "background_tasks":
        return pure_hint_runtime.background_tasks_command_hint(
            key_values=key_values,
            normalized_count_fn=normalized_count_fn,
            tool_label_fn=tool_label_fn,
            flag_label_fn=flag_label_fn,
        )
    if command_name == "background_worker_status":
        return pure_hint_runtime.background_worker_status_command_hint(
            key_values=key_values,
            tool_label_fn=tool_label_fn,
        )
    if command_name == "background_worker_run_once":
        return pure_hint_runtime.background_worker_run_once_command_hint(
            key_values=key_values,
            assistant_text=assistant_text,
            normalized_count_fn=normalized_count_fn,
            tool_label_fn=tool_label_fn,
            operator_hint_title_fn=operator_hint_title,
        )
    if command_name in {"background_worker_start", "background_worker_stop"}:
        return pure_hint_runtime.background_worker_lifecycle_command_hint(
            key_values=key_values,
            assistant_text=assistant_text,
            tool_label_fn=tool_label_fn,
            operator_hint_title_fn=operator_hint_title,
        )
    if command_name in operator_runtime.OPERATOR_COMMANDS:
        return _single_operator_result_hint(
            command_name,
            key_values=key_values,
            tool_label_fn=tool_label_fn,
            boolish_status_fn=operator_runtime.boolish_status,
        )
    return ""


def format_elapsed_compact(total_seconds: int) -> str:
    return surface_hint_runtime.format_elapsed_compact(total_seconds)


def pending_approval_count(status_data: dict[str, Any]) -> int:
    return surface_hint_runtime.pending_approval_count(status_data)


def build_operator_surface_hint(
    status_data: dict[str, Any],
    *,
    width: int,
    short_fn: Callable[[str, int], str],
    crop_one_line_fn: Callable[[str, int], str],
    tool_label_fn: Callable[[str], str],
    boolish_status_fn: Callable[[Any], bool | None],
) -> str:
    return projection_hint_runtime.build_projected_operator_surface_hint(
        status_data,
        width=width,
        short_fn=short_fn,
        crop_one_line_fn=crop_one_line_fn,
        tool_label_fn=tool_label_fn,
        boolish_status_fn=boolish_status_fn,
        tenant_scope_parts_fn=_tenant_scope_parts,
        review_projection_state_fn=_review_projection_state,
    )


def busy_label_for_queued_request(
    text: str,
    *,
    queued_request_busy_label_keys: dict[str, str],
    translate_fn: Callable[[str], str],
) -> str:
    return surface_hint_runtime.busy_label_for_queued_request(
        text,
        queued_request_busy_label_keys=queued_request_busy_label_keys,
        translate_fn=translate_fn,
    )

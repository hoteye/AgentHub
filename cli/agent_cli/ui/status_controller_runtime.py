from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.ui import status_line_summary_runtime as status_line_summary_runtime_service
from cli.agent_cli.ui import status_controller_hint_runtime as hint_runtime
from cli.agent_cli.ui import status_controller_operator_runtime as operator_runtime


OPERATOR_STATUS_KEYS = operator_runtime.OPERATOR_STATUS_KEYS
OPERATOR_HINT_KEYS = operator_runtime.OPERATOR_HINT_KEYS
OPERATOR_PAYLOAD_KEYS = operator_runtime.OPERATOR_PAYLOAD_KEYS
OPERATOR_COMMANDS = operator_runtime.OPERATOR_COMMANDS
OPERATOR_AGGREGATE_COMMANDS = operator_runtime.OPERATOR_AGGREGATE_COMMANDS
OPERATOR_TEXT_COMMANDS = operator_runtime.OPERATOR_TEXT_COMMANDS


status_text = operator_runtime.status_text
boolish_status = operator_runtime.boolish_status
normalized_status = operator_runtime.normalized_status
operator_primary_state = operator_runtime.operator_primary_state
status_from_response = operator_runtime.status_from_response
operator_status_from_response = operator_runtime.operator_status_from_response
operator_status_from_mapping = operator_runtime.operator_status_from_mapping
operator_command_name = operator_runtime.operator_command_name
key_value_lines = operator_runtime.key_value_lines
operator_status_from_text = operator_runtime.operator_status_from_text
normalized_count = operator_runtime.normalized_count


def operator_hint_title(assistant_text: Any) -> str:
    return hint_runtime.operator_hint_title(assistant_text)


def operator_hint_from_command(
    command_name: str,
    *,
    key_values: dict[str, str],
    assistant_text: Any,
    normalized_count_fn: Callable[[Any], str],
    tool_label_fn: Callable[[str], str],
    flag_label_fn: Callable[[str], str],
) -> str:
    return hint_runtime.operator_hint_from_command(
        command_name,
        key_values=key_values,
        assistant_text=assistant_text,
        normalized_count_fn=normalized_count_fn,
        tool_label_fn=tool_label_fn,
        flag_label_fn=flag_label_fn,
    )


format_elapsed_compact = hint_runtime.format_elapsed_compact
pending_approval_count = hint_runtime.pending_approval_count
build_operator_surface_hint = hint_runtime.build_operator_surface_hint
busy_label_for_queued_request = hint_runtime.busy_label_for_queued_request
tool_label = operator_runtime.tool_label
build_provider_summary_text = status_line_summary_runtime_service.build_provider_summary_text
build_status_summary_text = status_line_summary_runtime_service.build_status_summary_text
summary_segments = status_line_summary_runtime_service.summary_segments

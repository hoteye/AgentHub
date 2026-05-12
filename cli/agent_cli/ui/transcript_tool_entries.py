from __future__ import annotations

from typing import Callable

from cli.agent_cli.command_execution_summary_runtime import command_display_text_from_mapping
from cli.agent_cli.models import ActivityEvent, ToolEvent
from cli.agent_cli.ui.transcript_history import TranscriptEntry
from cli.agent_cli.ui import transcript_tool_entries_command_runtime
from cli.agent_cli.ui import transcript_tool_entries_mcp_runtime
from cli.agent_cli.ui.transcript_shell_exploration import (
    ParsedShellCommandSummary,
    command_execution_exploration_activity as _command_execution_exploration_activity,
    command_execution_exploration_entry as _command_execution_exploration_entry,
    command_execution_exploration_summaries,
    unwrap_shell_wrapped_command,
)
from cli.agent_cli.ui import transcript_tool_entries_runtime as transcript_tool_entries_runtime_service

COMMAND_OUTPUT_MAX_LINES_DEFAULT = 5


def is_exploration_mcp_tool(item: dict[str, object]) -> bool:
    return transcript_tool_entries_runtime_service.is_exploration_mcp_tool(item)


def format_mcp_invocation_text(item: dict[str, object]) -> str:
    return transcript_tool_entries_runtime_service.format_mcp_invocation_text(item)


def turn_tool_item_payload(item: dict[str, object]) -> dict[str, object]:
    return transcript_tool_entries_runtime_service.turn_tool_item_payload(item)


def image_artifact_details(item: dict[str, object]) -> tuple[str, int]:
    return transcript_tool_entries_runtime_service.image_artifact_details(item)


def input_image_output_details(item: dict[str, object]) -> tuple[str, int]:
    return transcript_tool_entries_runtime_service.input_image_output_details(item)


def input_image_output_transport_details(item: dict[str, object]) -> tuple[str, int, str, str]:
    return transcript_tool_entries_runtime_service.input_image_output_transport_details(item)


def view_document_extraction_details(item: dict[str, object]) -> tuple[str, str, str]:
    return transcript_tool_entries_runtime_service.view_document_extraction_details(item)


def document_output_projection_details(item: dict[str, object]) -> tuple[str, str, str]:
    return transcript_tool_entries_runtime_service.document_output_projection_details(item)


def is_local_exec_like_mcp_tool(item: dict[str, object]) -> bool:
    return transcript_tool_entries_runtime_service.is_local_exec_like_mcp_tool(item)


def is_shell_approval_payload(payload: dict[str, object]) -> bool:
    return transcript_tool_entries_runtime_service.is_shell_approval_payload(payload)


def local_exec_like_mcp_tool_entry(
    item: dict[str, object],
    *,
    item_key: str | None,
    scope_activity_key: Callable[[str | None], str | None],
    command_output_max_lines: int = COMMAND_OUTPUT_MAX_LINES_DEFAULT,
) -> TranscriptEntry | None:
    return transcript_tool_entries_mcp_runtime.local_exec_like_mcp_tool_entry(
        item,
        item_key=item_key,
        scope_activity_key=scope_activity_key,
        command_output_max_lines=command_output_max_lines,
        is_local_exec_like_mcp_tool_fn=is_local_exec_like_mcp_tool,
        turn_tool_item_payload_fn=turn_tool_item_payload,
        unwrap_shell_wrapped_command_fn=unwrap_shell_wrapped_command,
        turn_event_result_text_fn=turn_event_result_text,
        command_execution_entry_fn=command_execution_entry,
    )


def mcp_tool_call_entry(
    item: dict[str, object],
    *,
    item_key: str | None,
    scope_activity_key: Callable[[str | None], str | None],
) -> TranscriptEntry:
    return transcript_tool_entries_mcp_runtime.mcp_tool_call_entry(
        item,
        item_key=item_key,
        scope_activity_key=scope_activity_key,
        format_mcp_invocation_text_fn=format_mcp_invocation_text,
        turn_event_result_text_fn=turn_event_result_text,
    )


def view_image_mcp_tool_entry(
    item: dict[str, object],
    *,
    item_key: str | None,
    scope_activity_key: Callable[[str | None], str | None],
) -> TranscriptEntry | None:
    return transcript_tool_entries_mcp_runtime.view_image_mcp_tool_entry(
        item,
        item_key=item_key,
        scope_activity_key=scope_activity_key,
        image_artifact_details_fn=image_artifact_details,
    )


def view_document_mcp_tool_entry(
    item: dict[str, object],
    *,
    item_key: str | None,
    scope_activity_key: Callable[[str | None], str | None],
) -> TranscriptEntry | None:
    return transcript_tool_entries_mcp_runtime.view_document_mcp_tool_entry(
        item,
        item_key=item_key,
        scope_activity_key=scope_activity_key,
        view_document_extraction_details_fn=view_document_extraction_details,
    )


def input_image_output_entry(
    item: dict[str, object],
    *,
    item_key: str | None,
    scope_activity_key: Callable[[str | None], str | None],
) -> TranscriptEntry | None:
    return transcript_tool_entries_mcp_runtime.input_image_output_entry(
        item,
        item_key=item_key,
        scope_activity_key=scope_activity_key,
        input_image_output_transport_details_fn=input_image_output_transport_details,
    )


def document_output_entry(
    item: dict[str, object],
    *,
    item_key: str | None,
    scope_activity_key: Callable[[str | None], str | None],
) -> TranscriptEntry | None:
    return transcript_tool_entries_mcp_runtime.document_output_entry(
        item,
        item_key=item_key,
        scope_activity_key=scope_activity_key,
        document_output_projection_details_fn=document_output_projection_details,
    )


def todo_list_entry(
    item: dict[str, object],
    *,
    item_key: str | None,
    scope_activity_key: Callable[[str | None], str | None],
) -> TranscriptEntry:
    return transcript_tool_entries_command_runtime.todo_list_entry(
        item,
        item_key=item_key,
        scope_activity_key=scope_activity_key,
    )


def command_output_preview_lines(
    aggregated_output: str,
    *,
    command_output_max_lines: int = COMMAND_OUTPUT_MAX_LINES_DEFAULT,
) -> list[str]:
    return transcript_tool_entries_command_runtime.command_output_preview_lines(
        aggregated_output,
        command_output_max_lines=command_output_max_lines,
    )


def command_execution_entry(
    item: dict[str, object],
    *,
    item_key: str | None,
    scope_activity_key: Callable[[str | None], str | None],
    command_output_max_lines: int = COMMAND_OUTPUT_MAX_LINES_DEFAULT,
) -> TranscriptEntry:
    return transcript_tool_entries_command_runtime.command_execution_entry(
        item,
        item_key=item_key,
        scope_activity_key=scope_activity_key,
        command_output_max_lines=command_output_max_lines,
        command_display_text_from_mapping_fn=command_display_text_from_mapping,
        unwrap_shell_wrapped_command_fn=unwrap_shell_wrapped_command,
        command_output_preview_lines_fn=command_output_preview_lines,
    )


def command_execution_exploration_entry(
    item: dict[str, object],
    *,
    item_key: str | None,
    event_type: str | None = None,
) -> TranscriptEntry | None:
    return transcript_tool_entries_command_runtime.command_execution_exploration_entry(
        item,
        item_key=item_key,
        event_type=event_type,
        exploration_entry_fn=_command_execution_exploration_entry,
    )


def command_execution_exploration_activity(
    item: dict[str, object],
    *,
    event_type: str | None = None,
) -> ActivityEvent | None:
    return transcript_tool_entries_command_runtime.command_execution_exploration_activity(
        item,
        event_type=event_type,
        exploration_activity_fn=_command_execution_exploration_activity,
    )


def turn_event_result_text(result: object) -> str:
    return transcript_tool_entries_runtime_service.turn_event_result_text(result)


def turn_event_running_tool_detail(item: dict[str, object]) -> str:
    return transcript_tool_entries_runtime_service.turn_event_running_tool_detail(item)


def turn_event_command_text(item: dict[str, object]) -> str:
    return transcript_tool_entries_runtime_service.turn_event_command_text(item)


def turn_event_command_detail(item: dict[str, object]) -> str:
    return transcript_tool_entries_runtime_service.turn_event_command_detail(item)


def tool_event_from_turn_tool_item(item: dict[str, object]) -> ToolEvent | None:
    return transcript_tool_entries_mcp_runtime.tool_event_from_turn_tool_item(
        item,
        runtime_service=transcript_tool_entries_runtime_service,
    )

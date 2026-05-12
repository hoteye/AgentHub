from __future__ import annotations

from typing import Any

from cli.agent_cli.command_execution_summary_runtime import (
    command_activity_params,
    command_display_text_from_mapping,
)
from cli.agent_cli.models import ActivityEvent, ToolEvent
from cli.agent_cli.ui import (
    TranscriptEntry,
    activity_entry,
)
from cli.agent_cli.ui.app_turn_event_activity_helpers_runtime import (
    expert_review_activity as _expert_review_activity,
    native_web_search_activity as _native_web_search_activity,
    observable_turn_item as _observable_turn_item,
    reference_visible_reasoning_text as _reference_visible_reasoning_text,
)
from cli.agent_cli.ui.app_turn_event_projection_helpers_runtime import (
    turn_event_activity as _turn_event_activity,
    turn_event_entry as _turn_event_entry,
)
from cli.agent_cli.ui.transcript_tool_entries import (
    command_execution_entry as _command_execution_entry,
    command_execution_exploration_activity as _command_execution_exploration_activity,
    command_execution_exploration_entry as _command_execution_exploration_entry,
    document_output_entry as _document_output_entry,
    input_image_output_entry as _input_image_output_entry,
    is_exploration_mcp_tool as _is_exploration_mcp_tool,
    is_local_exec_like_mcp_tool as _is_local_exec_like_mcp_tool,
    is_shell_approval_payload as _is_shell_approval_payload,
    local_exec_like_mcp_tool_entry as _local_exec_like_mcp_tool_entry,
    mcp_tool_call_entry as _mcp_tool_call_entry,
    todo_list_entry as _todo_list_entry,
    tool_event_from_turn_tool_item as _tool_event_from_turn_tool_item,
    turn_event_command_detail as _turn_event_command_detail,
    turn_event_command_text as _turn_event_command_text,
    turn_event_result_text as _turn_event_result_text,
    turn_event_running_tool_detail as _turn_event_running_tool_detail,
    turn_tool_item_payload as _turn_tool_item_payload,
    view_document_mcp_tool_entry as _view_document_mcp_tool_entry,
    view_image_mcp_tool_entry as _view_image_mcp_tool_entry,
)


def is_exploration_mcp_tool(item: dict[str, object]) -> bool:
    return _is_exploration_mcp_tool(item)


def turn_tool_item_payload(item: dict[str, object]) -> dict[str, object]:
    return _turn_tool_item_payload(item)


def is_local_exec_like_mcp_tool(item: dict[str, object]) -> bool:
    return _is_local_exec_like_mcp_tool(item)


def is_shell_approval_payload(payload: dict[str, object]) -> bool:
    return _is_shell_approval_payload(payload)


def local_exec_like_mcp_tool_entry(
    app: Any,
    item: dict[str, object],
    *,
    item_key: str | None,
) -> TranscriptEntry | None:
    return _local_exec_like_mcp_tool_entry(
        item,
        item_key=item_key,
        scope_activity_key=app._scope_activity_key,
        command_output_max_lines=app.COMMAND_OUTPUT_MAX_LINES,
    )


def mcp_tool_call_entry(
    app: Any,
    item: dict[str, object],
    *,
    item_key: str | None,
) -> TranscriptEntry:
    return _mcp_tool_call_entry(
        item,
        item_key=item_key,
        scope_activity_key=app._scope_activity_key,
    )


def view_image_mcp_tool_entry(
    app: Any,
    item: dict[str, object],
    *,
    item_key: str | None,
) -> TranscriptEntry | None:
    return _view_image_mcp_tool_entry(
        item,
        item_key=item_key,
        scope_activity_key=app._scope_activity_key,
    )


def view_document_mcp_tool_entry(
    app: Any,
    item: dict[str, object],
    *,
    item_key: str | None,
) -> TranscriptEntry | None:
    return _view_document_mcp_tool_entry(
        item,
        item_key=item_key,
        scope_activity_key=app._scope_activity_key,
    )


def input_image_output_entry(
    app: Any,
    item: dict[str, object],
    *,
    item_key: str | None,
) -> TranscriptEntry | None:
    return _input_image_output_entry(
        item,
        item_key=item_key,
        scope_activity_key=app._scope_activity_key,
    )


def document_output_entry(
    app: Any,
    item: dict[str, object],
    *,
    item_key: str | None,
) -> TranscriptEntry | None:
    return _document_output_entry(
        item,
        item_key=item_key,
        scope_activity_key=app._scope_activity_key,
    )


def todo_list_entry(
    app: Any,
    item: dict[str, object],
    *,
    item_key: str | None,
) -> TranscriptEntry:
    return _todo_list_entry(
        item,
        item_key=item_key,
        scope_activity_key=app._scope_activity_key,
    )


def command_execution_entry(
    app: Any,
    item: dict[str, object],
    *,
    item_key: str | None,
) -> TranscriptEntry:
    return _command_execution_entry(
        item,
        item_key=item_key,
        scope_activity_key=app._scope_activity_key,
        command_output_max_lines=app.COMMAND_OUTPUT_MAX_LINES,
    )


def turn_event_result_text(result: object) -> str:
    return _turn_event_result_text(result)


def turn_event_running_tool_detail(item: dict[str, object]) -> str:
    return _turn_event_running_tool_detail(item)


def turn_event_command_text(item: dict[str, object]) -> str:
    return _turn_event_command_text(item)


def turn_event_command_detail(item: dict[str, object]) -> str:
    return _turn_event_command_detail(item)


def command_execution_exploration_entry(
    item: dict[str, object],
    *,
    item_key: str | None,
    event_type: str | None = None,
) -> TranscriptEntry | None:
    return _command_execution_exploration_entry(item, item_key=item_key, event_type=event_type)


def command_execution_exploration_activity(
    item: dict[str, object],
    *,
    event_type: str | None = None,
) -> ActivityEvent | None:
    return _command_execution_exploration_activity(item, event_type=event_type)


def tool_event_from_turn_tool_item(
    item: dict[str, object],
) -> ToolEvent | None:
    return _tool_event_from_turn_tool_item(item)


def turn_event_activity(app: Any, event: dict[str, object]) -> ActivityEvent | None:
    return _turn_event_activity(
        app,
        event,
        observable_turn_item_fn=_observable_turn_item,
        command_execution_exploration_activity_fn=command_execution_exploration_activity,
        command_activity_params_fn=command_activity_params,
        command_display_text_from_mapping_fn=command_display_text_from_mapping,
        turn_event_command_text_fn=turn_event_command_text,
        turn_event_command_detail_fn=turn_event_command_detail,
        turn_event_running_tool_detail_fn=turn_event_running_tool_detail,
        native_web_search_activity_fn=_native_web_search_activity,
        expert_review_activity_fn=_expert_review_activity,
        tool_event_from_turn_tool_item_fn=tool_event_from_turn_tool_item,
    )


def turn_event_entry(
    app: Any,
    event: dict[str, object],
    *,
    activity: ActivityEvent | None = None,
) -> TranscriptEntry | None:
    return _turn_event_entry(
        app,
        event,
        activity=activity,
        observable_turn_item_fn=_observable_turn_item,
        reference_visible_reasoning_text_fn=_reference_visible_reasoning_text,
        command_execution_exploration_entry_fn=command_execution_exploration_entry,
        command_execution_entry_fn=command_execution_entry,
        todo_list_entry_fn=todo_list_entry,
        activity_entry_fn=activity_entry,
        tool_event_from_turn_tool_item_fn=tool_event_from_turn_tool_item,
        local_exec_like_mcp_tool_entry_fn=local_exec_like_mcp_tool_entry,
        view_image_mcp_tool_entry_fn=view_image_mcp_tool_entry,
        view_document_mcp_tool_entry_fn=view_document_mcp_tool_entry,
        is_exploration_mcp_tool_fn=is_exploration_mcp_tool,
        mcp_tool_call_entry_fn=mcp_tool_call_entry,
        input_image_output_entry_fn=input_image_output_entry,
        document_output_entry_fn=document_output_entry,
    )

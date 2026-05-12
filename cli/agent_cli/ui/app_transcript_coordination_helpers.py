from __future__ import annotations

from typing import TYPE_CHECKING

from cli.agent_cli.models import ActivityEvent, ToolEvent
from cli.agent_cli.ui import app_turn_event_runtime
from cli.agent_cli.ui.transcript_history import TranscriptEntry

if TYPE_CHECKING:
    from cli.agent_cli.app import AgentCliApp


def is_exploration_mcp_tool(item: dict[str, object]) -> bool:
    return app_turn_event_runtime.is_exploration_mcp_tool(item)


def turn_tool_item_payload(item: dict[str, object]) -> dict[str, object]:
    return app_turn_event_runtime.turn_tool_item_payload(item)


def is_local_exec_like_mcp_tool(item: dict[str, object]) -> bool:
    return app_turn_event_runtime.is_local_exec_like_mcp_tool(item)


def is_shell_approval_payload(payload: dict[str, object]) -> bool:
    return app_turn_event_runtime.is_shell_approval_payload(payload)


def local_exec_like_mcp_tool_entry(
    app: "AgentCliApp",
    item: dict[str, object],
    *,
    item_key: str | None,
) -> TranscriptEntry | None:
    return app_turn_event_runtime.local_exec_like_mcp_tool_entry(
        app,
        item,
        item_key=item_key,
    )


def mcp_tool_call_entry(
    app: "AgentCliApp",
    item: dict[str, object],
    *,
    item_key: str | None,
) -> TranscriptEntry:
    return app_turn_event_runtime.mcp_tool_call_entry(
        app,
        item,
        item_key=item_key,
    )


def todo_list_entry(
    app: "AgentCliApp",
    item: dict[str, object],
    *,
    item_key: str | None,
) -> TranscriptEntry:
    return app_turn_event_runtime.todo_list_entry(
        app,
        item,
        item_key=item_key,
    )


def command_execution_entry(
    app: "AgentCliApp",
    item: dict[str, object],
    *,
    item_key: str | None,
) -> TranscriptEntry:
    return app_turn_event_runtime.command_execution_entry(
        app,
        item,
        item_key=item_key,
    )


def turn_event_result_text(result: object) -> str:
    return app_turn_event_runtime.turn_event_result_text(result)


def turn_event_running_tool_detail(item: dict[str, object]) -> str:
    return app_turn_event_runtime.turn_event_running_tool_detail(item)


def turn_event_command_text(item: dict[str, object]) -> str:
    return app_turn_event_runtime.turn_event_command_text(item)


def turn_event_command_detail(item: dict[str, object]) -> str:
    return app_turn_event_runtime.turn_event_command_detail(item)


def command_execution_exploration_entry(
    item: dict[str, object],
    *,
    item_key: str | None,
) -> TranscriptEntry | None:
    return app_turn_event_runtime.command_execution_exploration_entry(item, item_key=item_key)


def command_execution_exploration_activity(item: dict[str, object]) -> ActivityEvent | None:
    return app_turn_event_runtime.command_execution_exploration_activity(item)


def tool_event_from_turn_tool_item(item: dict[str, object]) -> ToolEvent | None:
    return app_turn_event_runtime.tool_event_from_turn_tool_item(item)


def turn_event_activity(app: "AgentCliApp", event: dict[str, object]) -> ActivityEvent | None:
    return app_turn_event_runtime.turn_event_activity(app, event)


def turn_event_entry(
    app: "AgentCliApp",
    event: dict[str, object],
    *,
    activity: ActivityEvent | None = None,
) -> TranscriptEntry | None:
    return app_turn_event_runtime.turn_event_entry(
        app,
        event,
        activity=activity,
    )

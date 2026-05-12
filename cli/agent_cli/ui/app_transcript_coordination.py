from __future__ import annotations

from typing import TYPE_CHECKING

from cli.agent_cli.models import ActivityEvent, PromptResponse, ToolEvent
from cli.agent_cli.ui import (
    activity_entry,
    activity_signature,
    file_reference_matches,
    format_activity_detail_lines,
    format_activity_summary,
    format_plan_steps,
    format_transcript_block,
    should_render_assistant_reply,
)
from cli.agent_cli.ui import app_transcript_coordination_runtime
from cli.agent_cli.ui import app_transcript_coordination_helpers
from cli.agent_cli.ui.app_transcript_coordination_helpers import (
    command_execution_exploration_activity,
    command_execution_exploration_entry,
    is_exploration_mcp_tool,
    is_local_exec_like_mcp_tool,
    is_shell_approval_payload,
    mcp_tool_call_entry,
    tool_event_from_turn_tool_item,
    turn_event_activity,
    turn_event_command_detail,
    turn_event_command_text,
    turn_event_result_text,
    turn_event_running_tool_detail,
    turn_tool_item_payload,
)
from cli.agent_cli.ui.transcript_history import TranscriptEntry
from cli.agent_cli.ui.transcript_tool_entries import (
    ParsedShellCommandSummary,
    command_output_preview_lines,
    command_execution_exploration_summaries,
    format_mcp_invocation_text,
    unwrap_shell_wrapped_command,
)

if TYPE_CHECKING:
    from cli.agent_cli.app import AgentCliApp


def format_transcript_block_lines(
    content: str,
    *,
    first_prefix: str,
    continuation_prefix: str,
) -> list[str]:
    return format_transcript_block(
        content,
        first_prefix=first_prefix,
        continuation_prefix=continuation_prefix,
    )


def write_activity_event(app: "AgentCliApp", event: ActivityEvent) -> None:
    app._note_work_activity_from_activity(event)
    app._note_pending_approval_activity(event)
    entry = activity_entry(event)
    if entry is not None:
        app._append_transcript_entry(app._scope_transcript_entry(entry))


def strip_activity_prefix(title: str, prefix: str) -> str:
    stripped = title.strip()
    if stripped.lower().startswith(prefix.lower()):
        return stripped[len(prefix) :].strip()
    return stripped


def local_exec_like_mcp_tool_entry(
    app: "AgentCliApp",
    item: dict[str, object],
    *,
    item_key: str | None,
) -> TranscriptEntry | None:
    return app_transcript_coordination_helpers.local_exec_like_mcp_tool_entry(
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
    return app_transcript_coordination_helpers.todo_list_entry(
        app,
        item,
        item_key=item_key,
    )


def command_output_preview(aggregated_output: str, *, command_output_max_lines: int) -> list[str]:
    return command_output_preview_lines(
        aggregated_output,
        command_output_max_lines=command_output_max_lines,
    )


def command_execution_entry(
    app: "AgentCliApp",
    item: dict[str, object],
    *,
    item_key: str | None,
) -> TranscriptEntry:
    return app_transcript_coordination_helpers.command_execution_entry(
        app,
        item,
        item_key=item_key,
    )


def turn_event_entry(
    app: "AgentCliApp",
    event: dict[str, object],
    *,
    activity: ActivityEvent | None = None,
) -> TranscriptEntry | None:
    return app_transcript_coordination_helpers.turn_event_entry(
        app,
        event,
        activity=activity,
    )


__all__ = [
    "ParsedShellCommandSummary",
    "activity_signature",
    "command_execution_entry",
    "command_execution_exploration_activity",
    "command_execution_exploration_entry",
    "command_execution_exploration_summaries",
    "command_output_preview",
    "format_activity_detail_lines",
    "format_activity_summary",
    "format_mcp_invocation_text",
    "format_plan_steps",
    "format_transcript_block_lines",
    "is_exploration_mcp_tool",
    "is_local_exec_like_mcp_tool",
    "is_shell_approval_payload",
    "local_exec_like_mcp_tool_entry",
    "mcp_tool_call_entry",
    "should_render_assistant_reply",
    "strip_activity_prefix",
    "todo_list_entry",
    "tool_event_from_turn_tool_item",
    "turn_event_activity",
    "turn_event_command_detail",
    "turn_event_command_text",
    "turn_event_entry",
    "turn_event_result_text",
    "turn_event_running_tool_detail",
    "turn_tool_item_payload",
    "unwrap_shell_wrapped_command",
    "write_activity_event",
    "AppTranscriptCoordinationMixin",
]


class AppTranscriptCoordinationMixin:
    @staticmethod
    def _format_transcript_block(content: str, *, first_prefix: str, continuation_prefix: str) -> list[str]:
        return format_transcript_block_lines(
            content,
            first_prefix=first_prefix,
            continuation_prefix=continuation_prefix,
        )

    def _write_activity_event(self, event: ActivityEvent) -> None:
        write_activity_event(self, event)

    @staticmethod
    def _format_plan_steps(detail: str) -> list[str]:
        return format_plan_steps(detail)

    @staticmethod
    def _format_activity_detail_lines(detail: str, *, stream: str = "stdout") -> list[str]:
        return format_activity_detail_lines(detail, stream=stream)

    @staticmethod
    def _strip_activity_prefix(title: str, prefix: str) -> str:
        return strip_activity_prefix(title, prefix)

    def _format_activity_summary(self, event: ActivityEvent) -> str:
        return format_activity_summary(event)

    @staticmethod
    def _activity_signature(event: ActivityEvent) -> tuple[str, str, str, str, str]:
        return activity_signature(event)

    @staticmethod
    def _is_exploration_mcp_tool(item: dict[str, object]) -> bool:
        return is_exploration_mcp_tool(item)

    @staticmethod
    def _format_mcp_invocation_text(item: dict[str, object]) -> str:
        return format_mcp_invocation_text(item)

    @staticmethod
    def _turn_tool_item_payload(item: dict[str, object]) -> dict[str, object]:
        return turn_tool_item_payload(item)

    @classmethod
    def _is_local_exec_like_mcp_tool(cls, item: dict[str, object]) -> bool:
        del cls
        return is_local_exec_like_mcp_tool(item)

    @staticmethod
    def _is_shell_approval_payload(payload: dict[str, object]) -> bool:
        return is_shell_approval_payload(payload)

    def _local_exec_like_mcp_tool_entry(self, item: dict[str, object], *, item_key: str | None) -> TranscriptEntry | None:
        return local_exec_like_mcp_tool_entry(
            self,
            item,
            item_key=item_key,
        )

    def _mcp_tool_call_entry(self, item: dict[str, object], *, item_key: str | None) -> TranscriptEntry:
        return mcp_tool_call_entry(
            self,
            item,
            item_key=item_key,
        )

    def _todo_list_entry(self, item: dict[str, object], *, item_key: str | None) -> TranscriptEntry:
        return todo_list_entry(
            self,
            item,
            item_key=item_key,
        )

    @classmethod
    def _command_output_preview_lines(cls, aggregated_output: str) -> list[str]:
        return command_output_preview(
            aggregated_output,
            command_output_max_lines=cls.COMMAND_OUTPUT_MAX_LINES,
        )

    def _command_execution_entry(self, item: dict[str, object], *, item_key: str | None) -> TranscriptEntry:
        return command_execution_entry(
            self,
            item,
            item_key=item_key,
        )

    @staticmethod
    def _turn_event_result_text(result: object) -> str:
        return turn_event_result_text(result)

    @staticmethod
    def _turn_event_running_tool_detail(item: dict[str, object]) -> str:
        return turn_event_running_tool_detail(item)

    @staticmethod
    def _turn_event_command_text(item: dict[str, object]) -> str:
        return turn_event_command_text(item)

    @staticmethod
    def _turn_event_command_detail(item: dict[str, object]) -> str:
        return turn_event_command_detail(item)

    @staticmethod
    def _unwrap_shell_wrapped_command(command_text: str) -> str:
        return unwrap_shell_wrapped_command(command_text)

    @classmethod
    def _command_execution_exploration_summaries(cls, item: dict[str, object]) -> list[ParsedShellCommandSummary] | None:
        return command_execution_exploration_summaries(item)

    @classmethod
    def _command_execution_exploration_entry(cls, item: dict[str, object], *, item_key: str | None) -> TranscriptEntry | None:
        del cls
        return command_execution_exploration_entry(item, item_key=item_key)

    @classmethod
    def _command_execution_exploration_activity(cls, item: dict[str, object]) -> ActivityEvent | None:
        del cls
        return command_execution_exploration_activity(item)

    def _tool_event_from_turn_tool_item(self, item: dict[str, object]) -> ToolEvent | None:
        del self
        return tool_event_from_turn_tool_item(item)

    def _turn_event_activity(self, event: dict[str, object]) -> ActivityEvent | None:
        return turn_event_activity(self, event)

    def _turn_event_entry(
        self,
        event: dict[str, object],
        *,
        activity: ActivityEvent | None = None,
    ) -> TranscriptEntry | None:
        return turn_event_entry(
            self,
            event,
            activity=activity,
        )

    @staticmethod
    def _should_render_assistant_reply(response: PromptResponse) -> bool:
        return should_render_assistant_reply(response)

    def _file_query(self) -> str | None:
        return app_transcript_coordination_runtime.file_query_for_app(self)

    def _active_prefixed_token(self, prefix: str, *, allow_empty: bool) -> tuple[str, int, int] | None:
        return app_transcript_coordination_runtime.active_prefixed_token_for_app(
            self,
            prefix,
            allow_empty=allow_empty,
        )

    def _insert_selected_file_reference(self) -> bool:
        return app_transcript_coordination_runtime.insert_selected_file_reference(self)

    def _workspace_files(self) -> list[str]:
        return app_transcript_coordination_runtime.workspace_files(self)

    def _file_reference_matches(self, query: str) -> list[dict[str, str]]:
        return file_reference_matches(
            self._workspace_files(),
            query,
            limit=self.FILE_POPUP_MATCH_LIMIT,
        )

    def _refresh_prompt_composer(self) -> None:
        app_transcript_coordination_runtime.refresh_prompt_composer(self)

from __future__ import annotations

from cli.agent_cli.models import ActivityEvent
from cli.agent_cli.command_execution_summary_runtime import (
    CommandExecutionSummary as ParsedShellCommandSummary,
    command_execution_summaries_from_mapping,
)
from cli.agent_cli.ui.transcript_formatting import (
    merge_exploration_detail_items,
    render_exploration_entry_lines,
)
from cli.agent_cli.ui import transcript_shell_exploration_runtime
from cli.agent_cli.ui import transcript_shell_exploration_command_runtime
from cli.agent_cli.ui.transcript_history import TranscriptEntry

def unwrap_shell_wrapped_command(command_text: str) -> str:
    return transcript_shell_exploration_command_runtime.unwrap_shell_wrapped_command(command_text)


def command_execution_exploration_summaries(item: dict[str, object]) -> list[ParsedShellCommandSummary] | None:
    summaries = command_execution_summaries_from_mapping(dict(item or {}))
    if not summaries:
        return None
    return list(summaries)


def _command_execution_running_status(status_text: str, *, event_type: str | None = None) -> bool:
    normalized_event_type = str(event_type or "").strip()
    if normalized_event_type in {"item.started", "item.updated"}:
        return True
    return status_text in {"in_progress", "running"}


def command_execution_exploration_entry(
    item: dict[str, object],
    *,
    item_key: str | None,
    event_type: str | None = None,
) -> TranscriptEntry | None:
    status_text = str(item.get("status") or "").strip().lower()
    exit_code = item.get("exit_code")
    if status_text == "failed" or (status_text == "completed" and exit_code not in {0, "0", None}):
        return None
    summaries = command_execution_exploration_summaries(item)
    if not summaries:
        return None
    details = transcript_shell_exploration_runtime.merged_exploration_details(
        summaries,
        merge_exploration_detail_items_fn=merge_exploration_detail_items,
    )
    if not details:
        return None
    status = "running" if _command_execution_running_status(status_text, event_type=event_type) else "success"
    lines = render_exploration_entry_lines(details, status=status)
    return TranscriptEntry(
        kind="activity",
        layer="tool",
        lines=lines,
        status=status,
        activity_key=item_key,
        exploration_details=details,
        render_mode="plain",
    )


def command_execution_exploration_activity(
    item: dict[str, object],
    *,
    event_type: str | None = None,
) -> ActivityEvent | None:
    status_text = str(item.get("status") or "").strip().lower()
    exit_code = item.get("exit_code")
    if status_text == "failed" or (status_text == "completed" and exit_code not in {0, "0", None}):
        return None
    summaries = command_execution_exploration_summaries(item)
    if not summaries:
        return None
    projected_status_text = "in_progress" if _command_execution_running_status(status_text, event_type=event_type) else status_text
    return transcript_shell_exploration_runtime.exploration_activity_event(summaries, status_text=projected_status_text)

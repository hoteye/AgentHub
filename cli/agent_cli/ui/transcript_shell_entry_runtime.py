from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.models import ActivityEvent
from cli.agent_cli.ui.transcript_history import TranscriptEntry


def command_execution_exploration_entry(
    item: dict[str, object],
    *,
    item_key: str | None,
    command_execution_exploration_summaries_fn: Callable[[dict[str, object]], list[Any] | None],
    merge_exploration_detail_items_fn: Callable[[list[tuple[str, str]], tuple[str, str]], list[tuple[str, str]]],
    render_exploration_entry_lines_fn: Callable[[list[tuple[str, str]], str], list[str]],
) -> TranscriptEntry | None:
    status_text = str(item.get("status") or "").strip().lower()
    exit_code = item.get("exit_code")
    if status_text == "failed" or (status_text == "completed" and exit_code not in {0, "0", None}):
        return None
    summaries = command_execution_exploration_summaries_fn(item)
    if not summaries:
        return None
    details: list[tuple[str, str]] = []
    for summary in summaries:
        detail = summary.exploration_detail()
        if detail is not None:
            details = merge_exploration_detail_items_fn(details, detail)
    if not details:
        return None
    status = "running" if status_text == "in_progress" else "success"
    lines = render_exploration_entry_lines_fn(details, status=status)
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
    command_execution_exploration_summaries_fn: Callable[[dict[str, object]], list[Any] | None],
) -> ActivityEvent | None:
    status_text = str(item.get("status") or "").strip().lower()
    exit_code = item.get("exit_code")
    if status_text == "failed" or (status_text == "completed" and exit_code not in {0, "0", None}):
        return None
    summaries = command_execution_exploration_summaries_fn(item)
    if not summaries:
        return None
    primary = summaries[0]
    if primary.kind == "list":
        title = "Running list_dir" if status_text == "in_progress" else "Listed directory"
        detail = f"dir_path={primary.path or '.'}"
        code = "dir.list"
        params = {"path": primary.path or ".", "tool_name": "list_dir"}
    elif primary.kind == "search":
        title = "Running grep_files" if status_text == "in_progress" else "Searched files"
        detail_parts = []
        if primary.query:
            detail_parts.append(f"query={primary.query}")
        if primary.path:
            detail_parts.append(f"path={primary.path}")
        detail = "\n".join(detail_parts)
        code = "dir.search"
        params = {
            "query": primary.query or "",
            "path": primary.path or "",
            "tool_name": "grep_files",
        }
    else:
        title = "Running read_file" if status_text == "in_progress" else "Read file"
        detail = f"path={primary.name or primary.path or ''}"
        code = "file.read"
        params = {
            "path": primary.path or "",
            "file_path": primary.name or primary.path or "",
            "tool_name": "read_file",
        }
    return ActivityEvent(
        title=title,
        status="running" if status_text == "in_progress" else "success",
        detail=detail,
        kind="tool",
        code=code,
        params=params,
    )

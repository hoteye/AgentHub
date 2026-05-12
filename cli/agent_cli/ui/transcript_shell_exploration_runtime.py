from __future__ import annotations

from typing import Callable, Protocol

from cli.agent_cli.models import ActivityEvent


class ExplorationSummary(Protocol):
    kind: str
    path: str | None
    query: str | None
    name: str | None

    def exploration_detail(self) -> tuple[str, str] | None: ...


def merged_exploration_details(
    summaries: list[ExplorationSummary],
    *,
    merge_exploration_detail_items_fn: Callable[[list[tuple[str, str]], tuple[str, str]], list[tuple[str, str]]],
) -> list[tuple[str, str]]:
    details: list[tuple[str, str]] = []
    for summary in summaries:
        detail = summary.exploration_detail()
        if detail is not None:
            details = merge_exploration_detail_items_fn(details, detail)
    return details


def exploration_activity_event(
    summaries: list[ExplorationSummary],
    *,
    status_text: str,
) -> ActivityEvent | None:
    if not summaries:
        return None
    primary = summaries[0]
    status = "running" if status_text == "in_progress" else "success"
    if primary.kind == "list":
        return ActivityEvent(
            title="Running list_dir" if status == "running" else "Listed directory",
            status=status,
            detail=f"dir_path={primary.path or '.'}",
            kind="tool",
            code="dir.list",
            params={"path": primary.path or ".", "tool_name": "list_dir"},
        )
    if primary.kind == "search":
        detail_parts: list[str] = []
        if primary.query:
            detail_parts.append(f"query={primary.query}")
        if primary.path:
            detail_parts.append(f"path={primary.path}")
        return ActivityEvent(
            title="Running grep_files" if status == "running" else "Searched files",
            status=status,
            detail="\n".join(detail_parts),
            kind="tool",
            code="dir.search",
            params={
                "query": primary.query or "",
                "path": primary.path or "",
                "tool_name": "grep_files",
            },
        )
    return ActivityEvent(
        title="Running read_file" if status == "running" else "Read file",
        status=status,
        detail=f"path={primary.name or primary.path or ''}",
        kind="tool",
        code="file.read",
        params={
            "path": primary.path or "",
            "file_path": primary.name or primary.path or "",
            "tool_name": "read_file",
        },
    )

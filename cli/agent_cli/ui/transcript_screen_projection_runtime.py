from __future__ import annotations

from cli.agent_cli.ui.transcript_history import TranscriptEntry
from cli.agent_cli.ui.transcript_screen_projection_groups_runtime import (
    collapsible_tool_group_key,
    summarize_tool_group,
)


def entries_for_screen(
    entries: list[TranscriptEntry],
    *,
    screen_mode: str,
) -> list[TranscriptEntry]:
    if str(screen_mode or "").strip().lower() == "transcript":
        return list(entries)
    return build_prompt_projection(entries)


def build_prompt_projection(entries: list[TranscriptEntry]) -> list[TranscriptEntry]:
    projected: list[TranscriptEntry] = []
    tool_group: list[TranscriptEntry] = []
    tool_group_key: str | None = None

    def flush_tool_group() -> None:
        nonlocal tool_group, tool_group_key
        if not tool_group:
            return
        if len(tool_group) == 1:
            projected.append(tool_group[0])
            tool_group = []
            tool_group_key = None
            return
        projected.append(summarize_tool_group(tool_group, group_key=str(tool_group_key or "tool")))
        tool_group = []
        tool_group_key = None

    for entry in list(entries or []):
        next_group_key = collapsible_tool_group_key(entry)
        if next_group_key is not None:
            if tool_group and tool_group_key != next_group_key:
                flush_tool_group()
            tool_group.append(entry)
            tool_group_key = next_group_key
            continue
        flush_tool_group()
        projected.append(entry)
    flush_tool_group()
    return projected

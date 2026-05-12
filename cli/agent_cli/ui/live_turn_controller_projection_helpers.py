from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from cli.agent_cli.ui.transcript_history import TranscriptEntry

_TOOL_LIKE_TURN_ITEM_TYPES = frozenset(
    {
        "mcp_tool_call",
        "command_execution",
        "todo_list",
        "expert_review",
        "function_call",
        "custom_tool_call",
        "shell_call",
        "local_shell_call",
    }
)


@dataclass(frozen=True)
class LiveTurnItemProjection:
    tool_sequence: int | None = None
    completed_text: str = ""
    has_completed_agent_message: bool = False
    completed_agent_message_key: str | None = None
    completed_agent_message_sequence: int = -1


def compact_blank_transcript_entries(entries: list[TranscriptEntry]) -> list[TranscriptEntry]:
    compacted_entries: list[TranscriptEntry] = []
    for entry in list(entries):
        if entry.kind == "blank" and (
            not compacted_entries or compacted_entries[-1].kind == "blank"
        ):
            continue
        compacted_entries.append(entry)
    while compacted_entries and compacted_entries[-1].kind == "blank":
        compacted_entries.pop()
    return compacted_entries


def drop_live_turn_todo_entries(
    entries: list[TranscriptEntry],
    *,
    active_transcript_turn_key: str,
) -> list[TranscriptEntry] | None:
    turn_prefix = f"{active_transcript_turn_key}:"
    filtered_entries: list[TranscriptEntry] = []
    changed = False
    for entry in list(entries):
        if entry.render_mode == "todo_list" and str(entry.activity_key or "").startswith(
            turn_prefix
        ):
            changed = True
            continue
        filtered_entries.append(entry)
    if not changed:
        return None
    return compact_blank_transcript_entries(filtered_entries)


def project_live_turn_item(
    *,
    item: dict[str, object],
    event_type: str,
    live_turn_event_sequence: int,
    entry_activity_key: str | None,
) -> LiveTurnItemProjection:
    item_type = str(item.get("type") or "").strip()
    text = str(item.get("text") or "").strip()
    completed_agent_message = item_type == "agent_message" and event_type == "item.completed"
    return LiveTurnItemProjection(
        tool_sequence=live_turn_event_sequence if item_type in _TOOL_LIKE_TURN_ITEM_TYPES else None,
        completed_text=text if text and event_type == "item.completed" else "",
        has_completed_agent_message=completed_agent_message,
        completed_agent_message_key=entry_activity_key,
        completed_agent_message_sequence=(
            live_turn_event_sequence if completed_agent_message else -1
        ),
    )


def should_finalize_live_turn_items(
    activity_key: str,
    *,
    live_turn_last_tool_sequence: int,
    live_turn_last_agent_message_sequence: int,
) -> bool:
    normalized_activity_key = str(activity_key or "").strip()
    if not normalized_activity_key:
        return False
    if live_turn_last_tool_sequence < 0:
        return True
    return live_turn_last_agent_message_sequence > live_turn_last_tool_sequence


@dataclass(frozen=True)
class DemotedLiveTurnEntryUpdate:
    entries: list[TranscriptEntry]
    separator_removed: bool = False


def demote_final_agent_message_before_late_tool(
    entries: list[TranscriptEntry],
    *,
    activity_key: str,
) -> DemotedLiveTurnEntryUpdate | None:
    normalized_activity_key = str(activity_key or "").strip()
    if not normalized_activity_key:
        return None
    for index in range(len(entries) - 1, -1, -1):
        candidate = entries[index]
        if candidate.activity_key != normalized_activity_key:
            continue
        if candidate.layer != "final" or candidate.status == "commentary":
            return None
        updated_entries = list(entries)
        updated_entries[index] = replace(
            candidate,
            layer="commentary",
            status="commentary",
        )
        separator_removed = False
        if index > 0:
            previous = updated_entries[index - 1]
            if previous.kind == "separator" and previous.layer == "separator":
                del updated_entries[index - 1]
                separator_removed = True
        return DemotedLiveTurnEntryUpdate(
            entries=updated_entries,
            separator_removed=separator_removed,
        )
    return None


def finalized_live_turn_entry_update(
    entries: list[TranscriptEntry],
    *,
    activity_key: str,
    is_interrupt_terminal_message_fn: Callable[[str], bool],
    format_transcript_block_fn: Callable[..., list[str]],
) -> tuple[int, TranscriptEntry] | None:
    for index in range(len(entries) - 1, -1, -1):
        candidate = entries[index]
        if candidate.activity_key != activity_key:
            continue
        if candidate.status == "commentary":
            return None
        content_text = str(candidate.raw_content or "").strip()
        if not content_text or is_interrupt_terminal_message_fn(content_text):
            return None
        return index, replace(
            candidate,
            layer="final",
            kind="assistant",
            raw_content=content_text,
            lines=format_transcript_block_fn(
                content_text,
                first_prefix="• ",
                continuation_prefix="  ",
            ),
        )
    return None

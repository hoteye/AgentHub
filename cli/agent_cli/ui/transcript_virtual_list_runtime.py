from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

from cli.agent_cli.ui.transcript_history import TranscriptEntry
from cli.agent_cli.ui.transcript_visual_rendering import should_insert_layer_gap


@dataclass(slots=True, frozen=True)
class TranscriptDisplayItem:
    kind: str
    entry: TranscriptEntry | None = None
    signature: tuple[object, ...] | None = None
    estimated_height: int = 1


def build_display_items(entries: list[TranscriptEntry]) -> list[TranscriptDisplayItem]:
    items: list[TranscriptDisplayItem] = []
    pending_blank = False
    previous_visible: TranscriptEntry | None = None
    for entry in list(entries or []):
        if entry.kind == "blank":
            pending_blank = previous_visible is not None
            continue
        if previous_visible is not None and (pending_blank or should_insert_layer_gap(previous_visible, entry)):
            items.append(TranscriptDisplayItem(kind="gap", estimated_height=1))
        items.append(
            TranscriptDisplayItem(
                kind="entry",
                entry=entry,
                signature=entry_signature(entry),
                estimated_height=estimate_entry_height(entry),
            )
        )
        previous_visible = entry
        pending_blank = False
    return items


def entry_signature(entry: TranscriptEntry) -> tuple[object, ...]:
    visible_lines = tuple(
        str(line)
        for line in (entry.expanded_lines if entry.expanded and entry.expanded_lines else entry.lines)
    )
    return (
        str(entry.kind or ""),
        str(entry.layer or ""),
        str(entry.status or ""),
        str(entry.activity_key or ""),
        str(entry.render_mode or ""),
        bool(entry.expanded),
        visible_lines,
        tuple(tuple(detail) for detail in list(entry.exploration_details or [])),
        str(entry.raw_content or ""),
    )


def estimate_entry_height(entry: TranscriptEntry) -> int:
    visible_lines = entry.expanded_lines if entry.expanded and entry.expanded_lines else entry.lines
    return max(1, len(list(visible_lines or [])))


def cumulative_offsets(heights: list[int]) -> tuple[list[int], int]:
    offsets: list[int] = []
    total = 0
    for height in list(heights or []):
        offsets.append(total)
        total += max(1, int(height))
    return offsets, total


def item_index_for_row(
    offsets: list[int],
    heights: list[int],
    row: int,
) -> int:
    if not offsets:
        return 0
    target = max(0, int(row))
    index = bisect_right(offsets, target) - 1
    index = max(0, min(index, len(offsets) - 1))
    while index + 1 < len(offsets) and target >= offsets[index] + max(1, int(heights[index])):
        index += 1
    return index


def visible_item_range(
    offsets: list[int],
    heights: list[int],
    *,
    start_row: int,
    end_row: int,
    overscan: int = 1,
) -> tuple[int, int]:
    if not offsets:
        return 0, 0
    start_index = item_index_for_row(offsets, heights, start_row)
    end_index = item_index_for_row(offsets, heights, max(start_row, end_row)) + 1
    return (
        max(0, start_index - max(0, int(overscan))),
        min(len(offsets), end_index + max(0, int(overscan))),
    )


def item_index_for_entry_id(items: list[TranscriptDisplayItem], entry_id: str) -> int | None:
    normalized_entry_id = str(entry_id or "").strip()
    if not normalized_entry_id:
        return None
    for index, item in enumerate(list(items or [])):
        if item.kind != "entry" or item.entry is None:
            continue
        if str(item.entry.entry_id or "").strip() == normalized_entry_id:
            return index
    return None

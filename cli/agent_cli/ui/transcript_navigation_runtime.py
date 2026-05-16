from __future__ import annotations

from dataclasses import replace

from cli.agent_cli.ui.transcript_history import TranscriptEntry


def expandable_entry_ids(entries: list[TranscriptEntry]) -> tuple[str, ...]:
    ids: list[str] = []
    for entry in list(entries or []):
        entry_id = str(entry.entry_id or "").strip()
        if entry_id and is_expandable_entry(entry):
            ids.append(entry_id)
    return tuple(ids)


def is_expandable_entry(entry: TranscriptEntry) -> bool:
    if entry.expanded_lines:
        return True
    payload = entry.structured
    if not isinstance(payload, dict):
        return False
    if str(payload.get("type") or "").strip() != "tool":
        return False
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return False
    return bool(metadata.get("output_truncated"))


def toggle_entry_expansion(
    entries: list[TranscriptEntry],
    entry_id: str,
) -> tuple[list[TranscriptEntry], bool]:
    target_id = str(entry_id or "").strip()
    if not target_id:
        return list(entries or []), False
    updated: list[TranscriptEntry] = []
    toggled = False
    for entry in list(entries or []):
        if (
            not toggled
            and str(entry.entry_id or "").strip() == target_id
            and is_expandable_entry(entry)
        ):
            updated.append(replace(entry, expanded=not bool(entry.expanded)))
            toggled = True
            continue
        updated.append(entry)
    return updated, toggled


def latest_expandable_entry_id(entries: list[TranscriptEntry]) -> str | None:
    for entry in reversed(list(entries or [])):
        entry_id = str(entry.entry_id or "").strip()
        if entry_id and is_expandable_entry(entry):
            return entry_id
    return None


def navigable_entry_ids(entries: list[TranscriptEntry], *, kind: str) -> tuple[str, ...]:
    normalized_kind = str(kind or "").strip().lower()
    if normalized_kind == "tool":
        return _entry_ids_matching(entries, _is_tool_entry)
    if normalized_kind == "user":
        return _entry_ids_matching(entries, lambda entry: entry.kind == "user")
    if normalized_kind == "assistant":
        return _entry_ids_matching(
            entries,
            lambda entry: entry.kind in {"assistant", "turn_item"} and entry.layer == "final",
        )
    return ()


def next_navigable_entry_id(
    entries: list[TranscriptEntry],
    *,
    current_entry_id: str | None,
    kind: str,
) -> str | None:
    ids = navigable_entry_ids(entries, kind=kind)
    if not ids:
        return None
    current = str(current_entry_id or "").strip()
    if current not in ids:
        return ids[0]
    index = ids.index(current) + 1
    if index >= len(ids):
        index = 0
    return ids[index]


def previous_navigable_entry_id(
    entries: list[TranscriptEntry],
    *,
    current_entry_id: str | None,
    kind: str,
) -> str | None:
    ids = navigable_entry_ids(entries, kind=kind)
    if not ids:
        return None
    current = str(current_entry_id or "").strip()
    if current not in ids:
        return ids[-1]
    index = ids.index(current) - 1
    if index < 0:
        index = len(ids) - 1
    return ids[index]


def _entry_ids_matching(entries: list[TranscriptEntry], predicate) -> tuple[str, ...]:
    ids: list[str] = []
    for entry in list(entries or []):
        entry_id = str(entry.entry_id or "").strip()
        if entry_id and predicate(entry):
            ids.append(entry_id)
    return tuple(ids)


def _is_tool_entry(entry: TranscriptEntry) -> bool:
    if entry.kind != "activity":
        return False
    if entry.layer in {"tool", "web"}:
        return True
    payload = entry.structured
    return isinstance(payload, dict) and str(payload.get("type") or "").strip() == "tool"

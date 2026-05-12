from __future__ import annotations

from dataclasses import dataclass

from cli.agent_cli.ui.transcript_history import TranscriptEntry


@dataclass(slots=True, frozen=True)
class TranscriptBrowsingState:
    query: str = ""
    match_entry_ids: tuple[str, ...] = ()
    active_match_index: int = -1
    anchor_entry_id: str | None = None
    sticky_task_hint: str = ""

    @property
    def active_match_entry_id(self) -> str | None:
        if 0 <= int(self.active_match_index) < len(self.match_entry_ids):
            return str(self.match_entry_ids[self.active_match_index] or "").strip() or None
        return None


@dataclass(slots=True, frozen=True)
class TranscriptSearchIndex:
    texts_by_entry_id: dict[str, str]


def build_transcript_search_index(entries: list[TranscriptEntry]) -> dict[str, str]:
    index: dict[str, str] = {}
    for entry in list(entries or []):
        entry_id = str(entry.entry_id or "").strip()
        if not entry_id:
            continue
        text = str(entry.search_text or "").strip()
        if not text and entry.lines:
            text = "\n".join(str(line or "") for line in entry.lines).strip()
        index[entry_id] = text.casefold()
    return index


def build_search_index(entries: list[TranscriptEntry]) -> TranscriptSearchIndex:
    return TranscriptSearchIndex(texts_by_entry_id=build_transcript_search_index(entries))


def find_transcript_matches(entries: list[TranscriptEntry], query: str) -> list[str]:
    return find_transcript_matches_in_index(build_search_index(entries), query)


def find_transcript_matches_in_index(index: TranscriptSearchIndex, query: str) -> list[str]:
    normalized_query = str(query or "").strip().casefold()
    if not normalized_query:
        return []
    matches: list[str] = []
    for entry_id, search_text in dict(index.texts_by_entry_id or {}).items():
        if normalized_query in search_text:
            matches.append(entry_id)
    return matches


def refresh_transcript_browsing_state(
    entries: list[TranscriptEntry],
    state: TranscriptBrowsingState | None,
) -> TranscriptBrowsingState:
    current = state or TranscriptBrowsingState()
    normalized_query = str(current.query or "").strip()
    if not normalized_query:
        return TranscriptBrowsingState(
            query="",
            match_entry_ids=(),
            active_match_index=-1,
            anchor_entry_id=current.anchor_entry_id,
            sticky_task_hint=current.sticky_task_hint,
        )
    matches = tuple(find_transcript_matches(entries, normalized_query))
    active_entry_id = current.active_match_entry_id
    if active_entry_id and active_entry_id in matches:
        active_index = matches.index(active_entry_id)
    elif matches:
        active_index = 0
    else:
        active_index = -1
    return TranscriptBrowsingState(
        query=normalized_query,
        match_entry_ids=matches,
        active_match_index=active_index,
        anchor_entry_id=current.anchor_entry_id,
        sticky_task_hint=current.sticky_task_hint,
    )


def next_match(state: TranscriptBrowsingState) -> TranscriptBrowsingState:
    if not state.match_entry_ids:
        return state
    next_index = int(state.active_match_index) + 1
    if next_index >= len(state.match_entry_ids):
        next_index = 0
    return TranscriptBrowsingState(
        query=state.query,
        match_entry_ids=tuple(state.match_entry_ids),
        active_match_index=next_index,
        anchor_entry_id=state.anchor_entry_id,
        sticky_task_hint=state.sticky_task_hint,
    )


def prev_match(state: TranscriptBrowsingState) -> TranscriptBrowsingState:
    if not state.match_entry_ids:
        return state
    previous_index = int(state.active_match_index) - 1
    if previous_index < 0:
        previous_index = len(state.match_entry_ids) - 1
    return TranscriptBrowsingState(
        query=state.query,
        match_entry_ids=tuple(state.match_entry_ids),
        active_match_index=previous_index,
        anchor_entry_id=state.anchor_entry_id,
        sticky_task_hint=state.sticky_task_hint,
    )

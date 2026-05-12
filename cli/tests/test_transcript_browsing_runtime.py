from __future__ import annotations

from cli.agent_cli.ui.transcript_browsing_runtime import (
    TranscriptBrowsingState,
    find_transcript_matches,
    refresh_transcript_browsing_state,
    next_match,
    prev_match,
)
from cli.agent_cli.ui.transcript_history import assistant_message_entry, user_message_entry


def test_find_transcript_matches_uses_entry_search_text() -> None:
    entries = [
        user_message_entry("first prompt"),
        assistant_message_entry("login timeout root cause"),
        assistant_message_entry("another answer"),
    ]
    entries[0].entry_id = "entry:1"
    entries[1].entry_id = "entry:2"
    entries[2].entry_id = "entry:3"

    assert find_transcript_matches(entries, "timeout") == ["entry:2"]


def test_refresh_transcript_browsing_state_selects_first_match() -> None:
    entries = [
        user_message_entry("alpha task"),
        assistant_message_entry("beta answer"),
        assistant_message_entry("beta followup"),
    ]
    entries[0].entry_id = "entry:1"
    entries[1].entry_id = "entry:2"
    entries[2].entry_id = "entry:3"

    state = refresh_transcript_browsing_state(entries, TranscriptBrowsingState(query=" beta "))

    assert state.query == "beta"
    assert state.match_entry_ids == ("entry:2", "entry:3")
    assert state.active_match_index == 0
    assert state.active_match_entry_id == "entry:2"


def test_refresh_transcript_browsing_state_preserves_active_match() -> None:
    entries = [
        user_message_entry("alpha task"),
        assistant_message_entry("beta answer"),
        assistant_message_entry("beta followup"),
    ]
    entries[0].entry_id = "entry:1"
    entries[1].entry_id = "entry:2"
    entries[2].entry_id = "entry:3"

    state = refresh_transcript_browsing_state(
        entries,
        TranscriptBrowsingState(query="beta", match_entry_ids=("entry:2", "entry:3"), active_match_index=1),
    )

    assert state.active_match_index == 1
    assert state.active_match_entry_id == "entry:3"


def test_refresh_transcript_browsing_state_clears_empty_query_matches() -> None:
    state = refresh_transcript_browsing_state(
        [],
        TranscriptBrowsingState(query=" ", match_entry_ids=("entry:2",), active_match_index=0),
    )

    assert state.query == ""
    assert state.match_entry_ids == ()
    assert state.active_match_index == -1


def test_next_match_wraps_to_start() -> None:
    state = TranscriptBrowsingState(query="x", match_entry_ids=("a", "b"), active_match_index=1)

    next_state = next_match(state)

    assert next_state.active_match_index == 0
    assert next_state.active_match_entry_id == "a"


def test_prev_match_wraps_to_end() -> None:
    state = TranscriptBrowsingState(query="x", match_entry_ids=("a", "b"), active_match_index=0)

    previous_state = prev_match(state)

    assert previous_state.active_match_index == 1
    assert previous_state.active_match_entry_id == "b"

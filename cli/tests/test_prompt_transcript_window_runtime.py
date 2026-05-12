from __future__ import annotations

from dataclasses import replace

from cli.agent_cli.ui.prompt_transcript_window_runtime import (
    PromptTranscriptWindowConfig,
    PromptTranscriptWindowState,
    build_prompt_transcript_window,
)
from cli.agent_cli.ui.transcript_history import TranscriptEntry, assistant_message_entry, user_message_entry


def _turn(index: int, *, tool_count: int = 0, assistant_text: str | None = None) -> list[TranscriptEntry]:
    entries: list[TranscriptEntry] = [
        replace(user_message_entry(f"user {index}"), entry_id=f"user:{index}"),
    ]
    for tool_index in range(tool_count):
        entries.append(
            TranscriptEntry(
                kind="activity",
                layer="tool",
                lines=[f"• Running cmd {index}:{tool_index}"],
                status="success",
                render_mode="tool_command",
                entry_id=f"tool:{index}:{tool_index}",
            )
        )
    entries.append(
        replace(
            assistant_message_entry(assistant_text or f"assistant {index}"),
            entry_id=f"assistant:{index}",
        )
    )
    return entries


def _entries(turn_count: int, *, tool_count: int = 0) -> list[TranscriptEntry]:
    entries: list[TranscriptEntry] = []
    for index in range(turn_count):
        entries.extend(_turn(index, tool_count=tool_count))
    return entries


def test_prompt_window_keeps_entries_when_under_budget() -> None:
    entries = _entries(3, tool_count=1)

    result = build_prompt_transcript_window(
        entries,
        config=PromptTranscriptWindowConfig(
            recent_turns_always_visible=2,
            target_turns=4,
            max_lines=200,
            max_chars=2000,
            advance_step_turns=2,
        ),
    )

    assert result.hidden_summary_entry is None
    assert result.hidden_summary_turns == 0
    assert result.dropped_turns == 0
    assert [entry.entry_id for entry in result.entries] == [entry.entry_id for entry in entries]



def test_prompt_window_prepends_hidden_summary_for_collapsed_turns() -> None:
    entries = _entries(6)

    result = build_prompt_transcript_window(
        entries,
        config=PromptTranscriptWindowConfig(
            recent_turns_always_visible=2,
            target_turns=4,
            max_lines=200,
            max_chars=2000,
            advance_step_turns=1,
        ),
    )

    assert result.hidden_summary_entry is not None
    assert result.hidden_summary_turns == 2
    assert result.entries[0].lines[0] == "• Earlier transcript hidden"
    assert "collapsed 2 older turns" in "\n".join(result.entries[0].lines)
    assert result.entries[1].entry_id == "user:2"



def test_prompt_window_drops_older_visible_turns_when_hard_cap_hits() -> None:
    entries = _entries(6, tool_count=1)

    result = build_prompt_transcript_window(
        entries,
        config=PromptTranscriptWindowConfig(
            recent_turns_always_visible=2,
            target_turns=4,
            max_lines=7,
            max_chars=1000,
            advance_step_turns=1,
        ),
    )

    assert result.hidden_summary_entry is not None
    assert result.dropped_turns >= 1
    assert any("dropped" in line for line in result.hidden_summary_entry.lines)
    assert result.entries[1].entry_id == "user:4"



def test_prompt_window_uses_index_fallback_when_anchor_entry_id_is_missing() -> None:
    entries = _entries(6)
    state = PromptTranscriptWindowState(start_entry_id="missing", start_entry_index=6)

    result = build_prompt_transcript_window(
        entries,
        state=state,
        config=PromptTranscriptWindowConfig(
            recent_turns_always_visible=2,
            target_turns=4,
            max_lines=200,
            max_chars=2000,
            advance_step_turns=1,
        ),
    )

    assert result.state.start_entry_index == 6
    assert result.entries[1].entry_id == "user:3"



def test_prompt_window_advance_step_prevents_one_turn_jitter() -> None:
    config = PromptTranscriptWindowConfig(
        recent_turns_always_visible=2,
        target_turns=10,
        max_lines=400,
        max_chars=40000,
        advance_step_turns=2,
    )
    initial = build_prompt_transcript_window(_entries(11), config=config)
    followup = build_prompt_transcript_window(_entries(12), state=initial.state, config=config)

    assert initial.hidden_summary_turns == 0
    assert followup.hidden_summary_turns == 2
    assert followup.state.start_entry_id == "user:2"



def test_prompt_window_compacts_oversized_recent_turn_but_keeps_user_and_answer() -> None:
    entries = _turn(0, tool_count=10, assistant_text="final answer")

    result = build_prompt_transcript_window(
        entries,
        config=PromptTranscriptWindowConfig(
            recent_turns_always_visible=1,
            target_turns=1,
            max_lines=5,
            max_chars=400,
            advance_step_turns=1,
        ),
    )

    rendered_text = "\n".join("\n".join(entry.lines) for entry in result.entries)
    assert "user 0" in rendered_text
    assert "final answer" in rendered_text
    assert "Turn activity hidden" in rendered_text

from __future__ import annotations

from cli.agent_cli.ui.transcript_history import TranscriptEntry
from cli.agent_cli.ui.transcript_navigation_runtime import (
    expandable_entry_ids,
    latest_expandable_entry_id,
    navigable_entry_ids,
    next_navigable_entry_id,
    previous_navigable_entry_id,
    toggle_entry_expansion,
)


def test_toggle_entry_expansion_updates_only_matching_expandable_entry() -> None:
    entries = [
        TranscriptEntry(kind="user", layer="user", lines=["› prompt"], entry_id="user_1"),
        TranscriptEntry(
            kind="activity",
            layer="web",
            lines=["• Searched the web", "  └ 2 results"],
            expanded_lines=["• Searched the web", "  └ 3 results"],
            entry_id="web_1",
        ),
    ]

    updated, toggled = toggle_entry_expansion(entries, "web_1")

    assert toggled is True
    assert updated[0] is entries[0]
    assert updated[1].expanded is True
    assert entries[1].expanded is False


def test_expandable_entry_ids_include_structured_truncated_shell_entries() -> None:
    entries = [
        TranscriptEntry(
            kind="activity",
            layer="tool",
            lines=["• Ran pytest -q"],
            entry_id="cmd_1",
            structured={
                "type": "tool",
                "name": "command_execution",
                "metadata": {"output_truncated": True},
            },
        ),
        TranscriptEntry(
            kind="activity",
            layer="tool",
            lines=["• Ran echo ok"],
            entry_id="cmd_2",
            structured={
                "type": "tool",
                "name": "command_execution",
                "metadata": {"output_truncated": False},
            },
        ),
    ]

    assert expandable_entry_ids(entries) == ("cmd_1",)
    assert latest_expandable_entry_id(entries) == "cmd_1"


def test_navigable_entry_ids_group_tool_user_and_final_assistant_entries() -> None:
    entries = [
        TranscriptEntry(kind="user", layer="user", lines=["› prompt"], entry_id="user_1"),
        TranscriptEntry(kind="activity", layer="tool", lines=["• Ran ls"], entry_id="tool_1"),
        TranscriptEntry(
            kind="turn_item",
            layer="final",
            lines=["• answer"],
            entry_id="assistant_1",
        ),
        TranscriptEntry(kind="activity", layer="web", lines=["• Searched"], entry_id="web_1"),
    ]

    assert navigable_entry_ids(entries, kind="tool") == ("tool_1", "web_1")
    assert navigable_entry_ids(entries, kind="user") == ("user_1",)
    assert navigable_entry_ids(entries, kind="assistant") == ("assistant_1",)
    assert next_navigable_entry_id(entries, current_entry_id="tool_1", kind="tool") == "web_1"
    assert previous_navigable_entry_id(entries, current_entry_id="tool_1", kind="tool") == "web_1"

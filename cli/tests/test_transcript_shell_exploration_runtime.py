from __future__ import annotations

from dataclasses import replace

from cli.agent_cli.ui.transcript_formatting import merge_exploration_detail_items
from cli.agent_cli.ui.transcript_history import render_transcript_visual_entries
from cli.agent_cli.ui.transcript_shell_exploration import (
    ParsedShellCommandSummary,
    command_execution_exploration_activity,
    command_execution_exploration_entry,
    command_execution_exploration_summaries,
)
from cli.agent_cli.ui.transcript_shell_exploration_runtime import (
    exploration_activity_event,
    merged_exploration_details,
)


def test_merged_exploration_details_coalesces_sequential_reads() -> None:
    summaries = [
        ParsedShellCommandSummary(kind="read", name="a.rs", path="a.rs"),
        ParsedShellCommandSummary(kind="read", name="b.rs", path="b.rs"),
        ParsedShellCommandSummary(kind="search", query="needle", path="src"),
    ]

    assert merged_exploration_details(
        summaries,
        merge_exploration_detail_items_fn=merge_exploration_detail_items,
    ) == [
        ("read", "a.rs, b.rs"),
        ("search", "needle in src"),
    ]


def test_exploration_activity_event_builds_search_payload() -> None:
    event = exploration_activity_event(
        [ParsedShellCommandSummary(kind="search", query="needle", path="src")],
        status_text="completed",
    )

    assert event is not None
    assert event.title == "Searched files"
    assert event.status == "success"
    assert event.detail == "query=needle\npath=src"
    assert event.code == "dir.search"
    assert event.params == {"query": "needle", "path": "src", "tool_name": "grep_files"}


def test_command_execution_exploration_entry_and_activity_keep_public_contract() -> None:
    item = {
        "id": "item_1",
        "type": "command_execution",
        "command": '/bin/bash -lc "rg \\"Change Approved\\"\ncat diff_render.rs"',
        "aggregated_output": "",
        "exit_code": 0,
        "status": "completed",
    }

    entry = command_execution_exploration_entry(item, item_key="item_1")
    activity = command_execution_exploration_activity(item)

    assert entry is not None
    assert entry.lines == [
        "• Explored",
        "  └ Search Change Approved",
        "    Read diff_render.rs",
    ]
    assert entry.structured is not None
    assert entry.structured["type"] == "tool"
    assert entry.structured["name"] == "command_exploration"
    assert entry.structured["input"]["details"] == [
        {"kind": "search", "subject": "Change Approved"},
        {"kind": "read", "subject": "diff_render.rs"},
    ]
    assert entry.activity_key == "item_1"
    assert activity is not None
    assert activity.title == "Searched files"
    assert activity.detail == "query=Change Approved"


def test_command_execution_exploration_summaries_compact_help_search_pipeline() -> None:
    item = {
        "id": "item_help_search",
        "type": "command_execution",
        "command": "/bin/bash -lc \"pytest --help | rg -n -- '-q'\"",
    }

    summaries = command_execution_exploration_summaries(item)

    assert summaries == [
        ParsedShellCommandSummary(kind="search", query="-q", path="pytest --help"),
    ]


def test_command_execution_exploration_entry_compacts_help_search_and_read_sequence() -> None:
    item = {
        "id": "item_help_sequence",
        "type": "command_execution",
        "command": "/bin/bash -lc \"pytest --help | rg -n -- '-q'\npytest --help | sed -n '120,150p'\"",
        "aggregated_output": "",
        "exit_code": 0,
        "status": "completed",
    }

    entry = command_execution_exploration_entry(item, item_key="item_help_sequence")

    assert entry is not None
    assert entry.lines == [
        "• Explored",
        "  └ Search -q in pytest --help",
        "    Read pytest --help",
    ]


def test_command_execution_exploration_visual_render_uses_structured_payload_before_legacy_lines() -> (
    None
):
    entry = command_execution_exploration_entry(
        {
            "id": "item_structured_exploration",
            "type": "command_execution",
            "command": '/bin/bash -lc "rg \\"Change Approved\\"\ncat diff_render.rs"',
            "aggregated_output": "",
            "exit_code": 0,
            "status": "completed",
        },
        item_key="item_structured_exploration",
    )

    assert entry is not None
    tampered = replace(entry, lines=["BROKEN LEGACY LINE"])

    rendered = render_transcript_visual_entries([tampered], width=80)

    assert rendered.lines == [
        "◆ Explored",
        "  └ Search Change Approved",
        "    Read diff_render.rs",
    ]


def test_command_execution_exploration_summaries_ignore_leading_shell_comment_label() -> None:
    item = {
        "id": "item_labelled_search",
        "type": "command_execution",
        "command": "/bin/bash -lc \"# Check pytest quiet flag\npytest --help | rg -n -- '-q'\"",
    }

    summaries = command_execution_exploration_summaries(item)

    assert summaries == [
        ParsedShellCommandSummary(kind="search", query="-q", path="pytest --help"),
    ]


def test_command_execution_exploration_summaries_skip_printf_banner_before_read() -> None:
    item = {
        "id": "item_printf_banner",
        "type": "command_execution",
        "command": "/bin/bash -lc \"printf '---\\n' && sed -n '1,12p' README.md\"",
    }

    summaries = command_execution_exploration_summaries(item)

    assert summaries == [
        ParsedShellCommandSummary(kind="read", name="README.md", path="README.md"),
    ]

from __future__ import annotations

import json

from cli.agent_cli.ui.transcript_export_runtime import (
    transcript_entries_to_export_records,
    transcript_entries_to_json,
    transcript_entries_to_markdown,
)
from cli.agent_cli.ui.transcript_history import (
    TranscriptEntry,
    assistant_message_entry,
    reasoning_message_entry,
    user_message_entry,
)
from cli.agent_cli.ui.transcript_structured_runtime import command_execution_payload


def test_export_records_use_structured_payload_not_visual_lines() -> None:
    entry = TranscriptEntry(
        kind="activity",
        layer="tool",
        lines=["BROKEN VISUAL LINE"],
        status="success",
        entry_id="cmd_1",
        structured=command_execution_payload(
            command_text="pytest -q",
            command_lines=["pytest -q"],
            output_lines=["18 passed"],
            status_text="completed",
            exit_code=0,
            cwd="/repo",
            duration_ms=4120,
        ),
        render_mode="tool_command",
    )

    records = transcript_entries_to_export_records([entry])

    assert records[0]["entry_id"] == "cmd_1"
    assert records[0]["structured"]["input"]["command"] == "pytest -q"
    assert records[0]["structured"]["metadata"]["cwd"] == "/repo"
    assert records[0]["structured"]["output"] == "18 passed"
    assert "lines" not in records[0]
    assert "BROKEN VISUAL LINE" not in json.dumps(records, ensure_ascii=False)


def test_export_json_can_hide_reasoning_and_tool_details() -> None:
    entries = [
        user_message_entry("hello"),
        reasoning_message_entry("private chain"),
        assistant_message_entry("answer"),
        TranscriptEntry(
            kind="activity",
            layer="tool",
            lines=["• Ran echo ok"],
            structured=command_execution_payload(
                command_text="echo ok",
                command_lines=["echo ok"],
                output_lines=["ok"],
                status_text="completed",
                exit_code=0,
            ),
        ),
    ]

    payload = json.loads(
        transcript_entries_to_json(
            entries,
            include_reasoning=False,
            include_tool_details=False,
        )
    )

    assert [record["kind"] for record in payload] == ["user", "assistant", "activity"]
    tool_payload = payload[-1]["structured"]
    assert tool_payload["name"] == "command_execution"
    assert "input" not in tool_payload
    assert "output" not in tool_payload
    assert "metadata" not in tool_payload


def test_export_markdown_formats_structured_entries_separately_from_prompt_rendering() -> None:
    entry = TranscriptEntry(
        kind="activity",
        layer="tool",
        lines=["BROKEN VISUAL LINE"],
        structured=command_execution_payload(
            command_text="pytest -q",
            command_lines=["pytest -q"],
            output_lines=["18 passed"],
            status_text="completed",
            exit_code=0,
        ),
    )

    markdown = transcript_entries_to_markdown([entry])

    assert "## tool / command_execution / completed" in markdown
    assert "- input:" in markdown
    assert "- output: 18 passed" in markdown
    assert "BROKEN VISUAL LINE" not in markdown

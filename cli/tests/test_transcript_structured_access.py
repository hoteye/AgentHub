from __future__ import annotations

from cli.agent_cli.ui.transcript_history import TranscriptEntry
from cli.agent_cli.ui.transcript_structured_access import (
    first_summary_line,
    payload_code,
    payload_command_text,
    payload_exploration_details,
    payload_group_key,
    payload_input,
    payload_metadata,
    payload_name,
    payload_output,
    payload_state,
    payload_summary,
    payload_title,
    string_list,
    structured_payload,
)


def test_structured_payload_accessors_normalize_missing_and_invalid_payloads() -> None:
    entry = TranscriptEntry(kind="activity", layer="tool", lines=["legacy"], structured=None)

    assert structured_payload(entry) is None
    assert payload_name(None) == ""
    assert payload_state(None) == ""
    assert payload_title(None) == ""
    assert payload_output(None) == ""
    assert payload_group_key(None) == ""
    assert payload_summary(None) == ""
    assert payload_input(None) == {}
    assert payload_metadata(None) == {}
    assert payload_code(None) == ""
    assert payload_command_text(None) == ""
    assert payload_exploration_details(None) == []


def test_structured_payload_accessors_extract_common_tool_fields() -> None:
    payload = {
        "type": "tool",
        "name": "command_execution",
        "state": "completed",
        "title": "Ran command",
        "summary": "Ran pytest -q",
        "group_key": "inspect",
        "input": {
            "display_command": "pytest -q",
            "command": "python -m pytest -q",
            "command_lines": ["pytest -q"],
        },
        "output": "18 passed\n",
        "metadata": {"code": "command.run", "cwd": "/repo"},
    }
    entry = TranscriptEntry(kind="activity", layer="tool", lines=["broken"], structured=payload)

    assert structured_payload(entry) == payload
    assert payload_name(payload) == "command_execution"
    assert payload_state(payload) == "completed"
    assert payload_title(payload) == "Ran command"
    assert payload_output(payload) == "18 passed"
    assert payload_group_key(payload) == "inspect"
    assert payload_summary(payload) == "Ran pytest -q"
    assert payload_input(payload)["command"] == "python -m pytest -q"
    assert payload_metadata(payload)["cwd"] == "/repo"
    assert payload_code(payload) == "command.run"
    assert payload_command_text(payload) == "pytest -q"


def test_structured_payload_accessors_fallback_to_command_lines_and_name_code() -> None:
    payload = {
        "name": "command_execution",
        "input": {"command_lines": ["python - <<'PY'", "print('ok')", "PY"]},
    }

    assert payload_code(payload) == "command_execution"
    assert payload_command_text(payload) == "python - <<'PY'\nprint('ok')\nPY"


def test_structured_payload_accessors_normalize_lists_and_exploration_details() -> None:
    payload = {
        "input": {
            "details": [
                {"kind": "read", "subject": "README.md"},
                "invalid",
                {"kind": "search", "subject": "needle in src"},
            ]
        }
    }

    assert string_list(["a", 2, None]) == ["a", "2", "None"]
    assert string_list(("not", "a", "list")) == []
    assert payload_exploration_details(payload) == [
        {"kind": "read", "subject": "README.md"},
        {"kind": "search", "subject": "needle in src"},
    ]
    assert first_summary_line("\n  first\nsecond") == "first"

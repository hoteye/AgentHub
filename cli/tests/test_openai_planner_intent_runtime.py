from __future__ import annotations

import re

import pytest

from cli.agent_cli.providers.openai_planner_intent_runtime import (
    assert_synthetic_recovery_allowed,
    history_for_conversation,
    intent_from_raw_text,
    normalize_command_text,
)
from cli.agent_cli.providers.openai_planner_support_runtime import extract_json_payload

def test_history_for_conversation_skips_legacy_history_when_structured_assistant_present() -> None:
    history = [{"role": "assistant", "content": "legacy assistant"}]
    input_items = [{"type": "message", "role": "assistant", "content": [{"type": "input_text", "text": "structured"}]}]

    result = history_for_conversation(
        history,
        input_items=input_items,
        input_items_have_assistant_turn_fn=lambda items: bool(items),
    )

    assert result == []

def test_assert_synthetic_recovery_allowed_rejects_reference_parity() -> None:
    with pytest.raises(RuntimeError, match="fresh followup is disabled when reference parity is enabled"):
        assert_synthetic_recovery_allowed(reference_parity_enabled=True, path_name="fresh followup")

def test_normalize_command_text_trims_followup_commands_for_shell() -> None:
    command = normalize_command_text(
        "/shell   ls   -la   /tmp   /read_file foo.py",
        followup_command_pattern=re.compile(r"\s+/(?:shell|read_file)\b"),
        normalize_shell_command_fn=lambda text: " ".join(str(text).split()),
    )

    assert command == "/shell ls -la /tmp"


def test_normalize_command_text_normalizes_exec_command_body_and_keeps_flags() -> None:
    command = normalize_command_text(
        "/exec_command --workdir cli pwd --yield-time-ms 250 /read_file foo.py",
        followup_command_pattern=re.compile(r"\s+/(?:exec_command|shell|read_file)\b"),
        normalize_shell_command_fn=lambda text: "Get-Location" if str(text).strip() == "pwd" else " ".join(str(text).split()),
    )

    assert command == "/exec_command Get-Location --workdir cli --yield-time-ms 250"

def test_intent_from_raw_text_extracts_command_and_projects_assistant_text() -> None:
    command_pattern = re.compile(r"(?m)(/(?:read_file|shell)\b[^\r\n`]*)")

    intent = intent_from_raw_text(
        "先看代码：\n/read_file agent_cli/providers/openai_planner.py",
        extract_json_payload_fn=extract_json_payload,
        normalize_command_text_fn=lambda value: normalize_command_text(
            value,
            followup_command_pattern=re.compile(r"\s+/(?:read_file|shell)\b"),
            normalize_shell_command_fn=lambda text: " ".join(str(text).split()),
        ),
        extract_command_text_fn=lambda raw_text: normalize_command_text(
            command_pattern.search(raw_text).group(1) if command_pattern.search(raw_text) else None,
            followup_command_pattern=re.compile(r"\s+/(?:read_file|shell)\b"),
            normalize_shell_command_fn=lambda text: " ".join(str(text).split()),
        ),
        command_pattern=command_pattern,
    )

    assert intent.command_text == "/read_file agent_cli/providers/openai_planner.py"
    assert intent.status_hint == "tool"
    assert intent.assistant_text == "先看代码"

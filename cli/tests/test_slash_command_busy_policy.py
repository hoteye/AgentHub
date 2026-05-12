from __future__ import annotations

from cli.agent_cli.slash_commands import (
    slash_command_available_during_busy,
    slash_command_name_from_text,
)


def test_slash_command_name_from_text_parses_raw_slash_input() -> None:
    assert slash_command_name_from_text("/provider verbose") == "provider"
    assert slash_command_name_from_text("/HELP") == "help"
    assert slash_command_name_from_text("/model-route tool_followup") == "model-route"


def test_slash_command_name_from_text_accepts_name_only() -> None:
    assert slash_command_name_from_text("provider") == "provider"
    assert slash_command_name_from_text("  providers  ") == "providers"


def test_slash_command_name_from_text_handles_empty_and_invalid_values() -> None:
    assert slash_command_name_from_text("") is None
    assert slash_command_name_from_text("   ") is None
    assert slash_command_name_from_text("/") is None
    # malformed quote should fall back to whitespace split
    assert slash_command_name_from_text('/provider "oops') == "provider"


def test_busy_policy_allows_default_read_only_commands() -> None:
    assert slash_command_available_during_busy("/help") is True
    assert slash_command_available_during_busy("providers") is True
    assert slash_command_available_during_busy("/models") is True
    assert slash_command_available_during_busy("/setup") is True
    assert slash_command_available_during_busy("/update") is True
    assert slash_command_available_during_busy("/runtime_status") is True
    assert slash_command_available_during_busy("/tools") is True
    assert slash_command_available_during_busy("/plugins") is True
    assert slash_command_available_during_busy("/tab_rename Running Label") is True
    assert slash_command_available_during_busy("/approval_inbox") is True
    assert slash_command_available_during_busy("/approval_inbox go tab-1") is True
    assert slash_command_available_during_busy("/preview close") is True


def test_busy_policy_provider_command_is_arg_aware() -> None:
    assert slash_command_available_during_busy("/provider") is True
    assert slash_command_available_during_busy("/provider verbose") is True
    assert slash_command_available_during_busy("/provider -v") is True
    assert slash_command_available_during_busy("/provider anthropic") is False

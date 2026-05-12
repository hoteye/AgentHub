from __future__ import annotations

from dataclasses import dataclass

from cli.agent_cli.runtime_core.command_registry import (
    CommandAvailability,
    autocomplete_command_registry,
    build_command_registry,
    command_available_during_busy,
    command_help_text,
    command_name_from_text,
    command_registry_rows,
    match_command_registry,
)


@dataclass(frozen=True)
class _BuiltinSpec:
    name: str
    usage: str
    description: str


def _registry_entries():
    return build_command_registry(
        builtin_specs=(
            _BuiltinSpec("help", "/help", "show help"),
            _BuiltinSpec("provider", "/provider [name]", "show or switch provider"),
            _BuiltinSpec("model", "/model [name]", "show or switch model"),
        ),
        plugin_specs=(
            {
                "name": "demo_plugin",
                "usage": "/demo_plugin",
                "description": "demo command",
                "source": "plugin",
            },
            {
                "name": "demo_workflow",
                "usage": "/demo_workflow",
                "description": "demo workflow",
                "source": "workflow",
            },
        ),
        builtin_busy_availability={
            "help": CommandAvailability(busy_mode="allowed"),
            "provider": CommandAvailability(busy_mode="read_only"),
        },
    )


def test_build_registry_carries_source_and_availability_fields() -> None:
    entries = _registry_entries()
    rows = command_registry_rows(entries)
    by_name = {item["name"]: item for item in rows}

    assert by_name["help"]["source"] == "builtin"
    assert by_name["help"]["busy_mode"] == "allowed"
    assert by_name["provider"]["busy_mode"] == "read_only"
    assert by_name["demo_plugin"]["source"] == "plugin"
    assert by_name["demo_workflow"]["source"] == "workflow"
    assert by_name["demo_plugin"]["busy_mode"] == "blocked"


def test_registry_match_autocomplete_and_help_share_same_entries() -> None:
    entries = _registry_entries()

    matches = match_command_registry("pro", entries)
    assert [item.name for item in matches] == ["provider"]
    assert autocomplete_command_registry("pro", entries) == "/provider "
    assert command_help_text(entries).splitlines()[1:] == [
        f"{item.usage} - {item.description}" for item in entries
    ]


def test_registry_help_text_accepts_localized_heading() -> None:
    entries = _registry_entries()

    assert command_help_text(entries, heading="可用命令：").splitlines()[0] == "可用命令："


def test_command_name_parser_handles_raw_and_plain_inputs() -> None:
    assert command_name_from_text("/provider verbose") == "provider"
    assert command_name_from_text("provider") == "provider"
    assert command_name_from_text("/HELP") == "help"
    assert command_name_from_text("") is None
    assert command_name_from_text("/") is None


def test_busy_policy_uses_registry_availability_and_provider_read_only_rules() -> None:
    entries = _registry_entries()
    assert command_available_during_busy("/help", entries) is True
    assert command_available_during_busy("/provider", entries) is True
    assert command_available_during_busy("/provider verbose", entries) is True
    assert command_available_during_busy("/provider -v", entries) is True
    assert command_available_during_busy("/provider anthropic", entries) is False
    assert command_available_during_busy("/model default", entries) is False
    assert command_available_during_busy("/demo_plugin", entries) is False

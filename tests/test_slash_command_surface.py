from __future__ import annotations

from cli.agent_cli.slash_commands import (
    autocomplete_slash_command,
    match_slash_commands,
    slash_command_help_text,
    slash_command_specs,
)


def _names(items) -> set[str]:
    return {str(getattr(item, "name", "") or "").strip() for item in items}


def test_default_slash_surface_is_curated() -> None:
    names = _names(slash_command_specs())

    assert "help" in names
    assert "provider" in names
    assert "model" in names
    assert "status" in names
    assert "setup" in names

    assert "connect" not in names
    assert "auth" not in names
    assert "spawn_agent" not in names
    assert "web_search" not in names
    assert "read_file" not in names
    assert "browser" not in names
    assert "plugin_install" not in names
    assert "background_worker_start" not in names


def test_advanced_slash_surface_remains_registered() -> None:
    names = _names(slash_command_specs(discoverable_only=False))

    assert "web_search" in names
    assert "read_file" in names
    assert "browser" in names
    assert "spawn_agent" in names
    assert "plugin_install" in names
    assert "background_worker_start" in names


def test_default_matching_and_completion_use_curated_surface() -> None:
    assert match_slash_commands("web") == []
    assert autocomplete_slash_command("web") is None

    advanced_matches = match_slash_commands("web", discoverable_only=False)
    assert "web_search" in _names(advanced_matches)


def test_help_defaults_to_curated_surface_with_advanced_escape_hatch() -> None:
    default_help = slash_command_help_text()
    advanced_help = slash_command_help_text(include_advanced=True)

    assert "/status - show current session configuration and runtime status" in default_help
    assert "/web_search" not in default_help
    assert "Use /help all to show advanced and plugin commands." in default_help

    assert "/web_search" in advanced_help
    assert "Use /help all" not in advanced_help

from __future__ import annotations

from cli.agent_cli.provider_source_semantics_runtime import provider_source_semantics_fields


def test_provider_source_semantics_maps_user_home_from_agent_cli_home() -> None:
    payload = provider_source_semantics_fields(
        raw_source="agent_cli_home",
        config_path="/tmp/home/.agent_cli/config.toml",
        auth_path="/tmp/home/.agent_cli/auth.json",
        selection_path="/tmp/home/.agent_cli/config.toml",
        selection_present=True,
        user_config_path="/tmp/home/.agent_cli/config.toml",
        user_auth_path="/tmp/home/.agent_cli/auth.json",
        runtime_home="",
    )

    assert payload["provider_source"] == "user_home"
    assert payload["provider_config_scope"] == "user_home"
    assert payload["provider_selection_scope"] == "user_home"
    assert payload["provider_selection_active"] is True
    assert payload["provider_runtime_home_active"] is False
    assert payload["provider_source_raw"] == "agent_cli_home"


def test_provider_source_semantics_preserves_project_local_without_runtime_home() -> None:
    payload = provider_source_semantics_fields(
        raw_source="project_local",
        config_path="/tmp/workspace/.config/config.toml",
        auth_path="/tmp/workspace/.config/auth.json",
        selection_path="/tmp/home/.agent_cli/config.toml",
        selection_present=False,
        user_config_path="/tmp/home/.agent_cli/config.toml",
        user_auth_path="/tmp/home/.agent_cli/auth.json",
        runtime_home="",
    )

    assert payload["provider_source"] == "project_local"
    assert payload["provider_config_scope"] == "project_local"
    assert payload["provider_selection_scope"] == "none"
    assert payload["provider_selection_active"] is False
    assert payload["provider_runtime_home_active"] is False
    assert "provider_source_raw" not in payload


def test_provider_source_semantics_keeps_project_config_scope_with_user_auth() -> None:
    payload = provider_source_semantics_fields(
        raw_source="project_local",
        config_path="/tmp/workspace/.config/config.toml",
        auth_path="/tmp/home/.agent_cli/auth.json",
        selection_path="/tmp/home/.agent_cli/config.toml",
        selection_present=False,
        user_config_path="/tmp/home/.agent_cli/config.toml",
        user_auth_path="/tmp/home/.agent_cli/auth.json",
        runtime_home="",
    )

    assert payload["provider_source"] == "project_local"
    assert payload["provider_config_scope"] == "project_local"
    assert payload["provider_selection_scope"] == "none"


def test_provider_source_semantics_promotes_explicit_provider_home_to_runtime_home() -> None:
    payload = provider_source_semantics_fields(
        raw_source="project_local",
        config_path="/tmp/runtime-home/config.toml",
        auth_path="/tmp/runtime-home/auth.json",
        selection_path="/tmp/home/.agent_cli/config.toml",
        selection_present=True,
        user_config_path="/tmp/home/.agent_cli/config.toml",
        user_auth_path="/tmp/home/.agent_cli/auth.json",
        runtime_home="/tmp/runtime-home",
    )

    assert payload["provider_source"] == "runtime_home"
    assert payload["provider_source_raw"] == "project_local"
    assert payload["provider_config_scope"] == "runtime_home"
    assert payload["provider_selection_scope"] == "user_home"
    assert payload["provider_selection_active"] is True
    assert payload["provider_runtime_home_active"] is True
    assert payload["provider_runtime_home_path"] == "/tmp/runtime-home"

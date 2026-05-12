from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.providers.availability_feature_config_runtime import (
    provider_availability_feature_settings,
    provider_availability_feature_settings_from_config,
)


def test_provider_availability_feature_settings_defaults() -> None:
    settings = provider_availability_feature_settings_from_config({})

    assert settings["stale_after_seconds"] == 18000
    assert settings["config_source"] == "default"


def test_provider_availability_feature_settings_reads_workspace_overrides() -> None:
    settings = provider_availability_feature_settings_from_config(
        {
            "features": {
                "provider_availability": {
                    "stale_after_seconds": "45",
                }
            }
        }
    )

    assert settings["stale_after_seconds"] == 45
    assert settings["config_source"] == "workspace_config"


def test_provider_availability_feature_settings_accepts_scalar_shorthand() -> None:
    settings = provider_availability_feature_settings_from_config(
        {"features": {"provider_availability": "90"}}
    )

    assert settings["stale_after_seconds"] == 90
    assert settings["config_source"] == "workspace_config"


def test_provider_availability_feature_settings_reads_merged_workspace_config() -> None:
    owner = SimpleNamespace(cwd=Path("/tmp/workspace"))

    with patch(
        "cli.agent_cli.providers.availability_feature_config_runtime._effective_home_provider_config_path",
        return_value=Path("/tmp/runtime-home/config.toml"),
    ), patch(
        "cli.agent_cli.providers.availability_feature_config_runtime.workspace_context.read_merged_project_toml",
        return_value=(
            {"features": {"provider_availability": {"stale_after_seconds": 75}}},
            [],
        ),
    ) as read_merged:
        settings = provider_availability_feature_settings(owner)

    assert settings["stale_after_seconds"] == 75
    assert settings["config_source"] == "workspace_config"
    read_merged.assert_called_once_with(
        cwd=Path("/tmp/workspace"),
        home_config_paths=[Path("/tmp/runtime-home/config.toml")],
    )

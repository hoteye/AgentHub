from __future__ import annotations

from pathlib import Path

from cli.agent_cli.providers.provider_discovery_feature_config_runtime import (
    provider_discovery_feature_settings,
    provider_discovery_feature_settings_from_config,
)


def test_provider_discovery_feature_settings_defaults() -> None:
    settings = provider_discovery_feature_settings_from_config({})

    assert settings["strict_isolation"] is False
    assert settings["config_source"] == "default"


def test_provider_discovery_feature_settings_reads_home_config_mapping() -> None:
    settings = provider_discovery_feature_settings_from_config(
        {"features": {"provider_discovery": {"strict_isolation": True}}}
    )

    assert settings["strict_isolation"] is True
    assert settings["config_source"] == "home_config"


def test_provider_discovery_feature_settings_env_overrides_home_config() -> None:
    config_payload = {"features": {"provider_discovery": {"strict_isolation": False}}}

    settings = provider_discovery_feature_settings(
        env_mapping={"AGENTHUB_PROVIDER_STRICT_ISOLATION": "true"},
        config_paths=(Path("/tmp/config.toml"),),
        read_toml_fn=lambda _path: config_payload,
    )

    assert settings["strict_isolation"] is True
    assert settings["config_source"] == "env"

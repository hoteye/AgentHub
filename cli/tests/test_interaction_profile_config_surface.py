from __future__ import annotations

from pathlib import Path

from cli.agent_cli.providers.config_catalog import (
    LEGACY_CODEX_PROFILE,
    build_provider_catalog,
    resolve_configured_interaction_profile,
    select_provider_config,
)
from cli.agent_cli.providers.config_catalog_types import ProviderPathResolution


def _resolution() -> ProviderPathResolution:
    return ProviderPathResolution(
        config_path=Path("/tmp/config.toml"),
        auth_path=Path("/tmp/auth.json"),
        config_exists=True,
        auth_exists=True,
        used_project_local=True,
    )


def test_model_explicit_interaction_profile_overrides_provider_explicit() -> None:
    profile, source = resolve_configured_interaction_profile(
        raw_model={"interaction_profile": "Claude-Code"},
        raw_provider={"interaction_profile": "generic_chat", "reference_parity": True},
    )
    assert profile == "claude_code"
    assert source == "model.interaction_profile"


def test_model_legacy_alias_maps_codex_profile() -> None:
    profile, source = resolve_configured_interaction_profile(
        raw_model={"reference_parity": True},
        raw_provider={"interaction_profile": "generic_chat"},
    )
    assert profile == LEGACY_CODEX_PROFILE
    assert source == "model.reference_parity"


def test_model_legacy_alias_false_blocks_provider_alias() -> None:
    profile, source = resolve_configured_interaction_profile(
        raw_model={"codex_parity": False},
        raw_provider={"reference_parity": True},
    )
    assert profile == ""
    assert source == "model.codex_parity"


def test_select_provider_config_carries_interaction_profile_and_source_from_model() -> None:
    config = select_provider_config(
        env_mapping={"OPENAI_API_KEY": "sk-test"},
        auth_data={},
        toml_data={
            "model_provider": "openai",
            "model": "gpt_main",
            "model_providers": {
                "openai": {
                    "base_url": "https://relay.example/v1",
                    "interaction_profile": "generic_chat",
                    "default_model": "gpt_main",
                }
            },
            "models": {
                "gpt_main": {
                    "provider": "openai",
                    "model_id": "gpt-5.4",
                    "interaction_profile": "Codex-OpenAI",
                }
            },
        },
        resolution=_resolution(),
    )
    assert config is not None
    assert config.interaction_profile == "codex_openai"
    assert config.interaction_profile_source == "model.interaction_profile"


def test_select_provider_config_defaults_codex_openai_gpt54_to_xhigh_reasoning() -> None:
    config = select_provider_config(
        env_mapping={"OPENAI_API_KEY": "sk-test"},
        auth_data={},
        toml_data={
            "model_provider": "openai",
            "model": "gpt_main",
            "model_providers": {
                "openai": {
                    "base_url": "https://relay.example/v1",
                    "wire_api": "responses",
                    "default_model": "gpt_main",
                }
            },
            "models": {
                "gpt_main": {
                    "provider": "openai",
                    "model_id": "gpt-5.4",
                    "planner_kind": "openai_responses",
                    "wire_api": "responses",
                    "interaction_profile": "codex_openai",
                }
            },
        },
        resolution=_resolution(),
    )
    assert config is not None
    assert config.reasoning_effort == "xhigh"


def test_select_provider_config_respects_explicit_codex_openai_gpt54_reasoning() -> None:
    config = select_provider_config(
        env_mapping={"OPENAI_API_KEY": "sk-test"},
        auth_data={},
        toml_data={
            "model_provider": "openai",
            "model": "gpt_main",
            "model_reasoning_effort": "high",
            "model_providers": {
                "openai": {
                    "base_url": "https://relay.example/v1",
                    "wire_api": "responses",
                    "default_model": "gpt_main",
                }
            },
            "models": {
                "gpt_main": {
                    "provider": "openai",
                    "model_id": "gpt-5.4",
                    "planner_kind": "openai_responses",
                    "wire_api": "responses",
                    "interaction_profile": "codex_openai",
                }
            },
        },
        resolution=_resolution(),
    )
    assert config is not None
    assert config.reasoning_effort == "high"


def test_select_provider_config_uses_provider_profile_when_model_has_none() -> None:
    config = select_provider_config(
        env_mapping={"OPENAI_API_KEY": "sk-test"},
        auth_data={},
        toml_data={
            "model_provider": "openai",
            "model": "gpt_main",
            "model_providers": {
                "openai": {
                    "base_url": "https://relay.example/v1",
                    "interaction_profile": "Generic-Chat",
                }
            },
            "models": {
                "gpt_main": {
                    "provider": "openai",
                    "model_id": "gpt-5.4",
                }
            },
        },
        resolution=_resolution(),
    )
    assert config is not None
    assert config.interaction_profile == "generic_chat"
    assert config.interaction_profile_source == "provider.interaction_profile"


def test_select_provider_config_maps_provider_legacy_alias_when_no_explicit_profile() -> None:
    config = select_provider_config(
        env_mapping={"OPENAI_API_KEY": "sk-test"},
        auth_data={},
        toml_data={
            "model_provider": "openai",
            "model": "gpt_main",
            "model_providers": {
                "openai": {
                    "base_url": "https://relay.example/v1",
                    "codex_parity": True,
                }
            },
            "models": {
                "gpt_main": {
                    "provider": "openai",
                    "model_id": "gpt-5.4",
                }
            },
        },
        resolution=_resolution(),
    )
    assert config is not None
    assert config.interaction_profile == LEGACY_CODEX_PROFILE
    assert config.interaction_profile_source == "provider.codex_parity"


def test_build_provider_catalog_projects_interaction_profile_fields() -> None:
    catalog = build_provider_catalog(
        {
            "model_provider": "openai",
            "model": "gpt_main",
            "model_providers": {
                "openai": {
                    "base_url": "https://relay.example/v1",
                    "interaction_profile": "Codex-OpenAI",
                }
            },
            "models": {
                "gpt_main": {
                    "provider": "openai",
                    "model_id": "gpt-5.4",
                    "interaction_profile": "Claude-Code",
                }
            },
        }
    )

    assert catalog.providers["openai"].interaction_profile == "codex_openai"
    assert catalog.models["gpt_main"].interaction_profile == "claude_code"


def test_build_provider_catalog_projects_legacy_aliases_into_interaction_profile_fields() -> None:
    catalog = build_provider_catalog(
        {
            "model_provider": "openai",
            "model": "gpt_main",
            "model_providers": {
                "openai": {
                    "base_url": "https://relay.example/v1",
                    "reference_parity": True,
                }
            },
            "models": {
                "gpt_main": {
                    "provider": "openai",
                    "model_id": "gpt-5.4",
                    "codex_parity": True,
                }
            },
        }
    )

    assert catalog.providers["openai"].interaction_profile == LEGACY_CODEX_PROFILE
    assert catalog.models["gpt_main"].interaction_profile == LEGACY_CODEX_PROFILE

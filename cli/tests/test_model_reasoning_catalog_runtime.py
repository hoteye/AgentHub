from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from cli.agent_cli.app_server_reference_payloads_normalization_helpers_runtime import (
    model_list_entry_payload,
)
from cli.agent_cli.provider_catalog_runtime import model_catalog_reasoning_profile
from cli.agent_cli.providers.anthropic_claude import load_claude_provider_config
from cli.agent_cli.providers.config_catalog import (
    ProviderPathResolution,
    build_provider_catalog,
    select_provider_config,
)


def _resolution() -> ProviderPathResolution:
    return ProviderPathResolution(
        config_path=Path("/tmp/config.toml"),
        auth_path=Path("/tmp/auth.json"),
        config_exists=True,
        auth_exists=True,
        used_project_local=False,
    )


def test_build_provider_catalog_assigns_codex_openai_xhigh_default_for_gpt_54() -> None:
    catalog = build_provider_catalog(
        {
            "model_provider": "openai",
            "model": "gpt_54",
            "model_providers": {
                "openai": {
                    "base_url": "https://api.openai.com/v1",
                    "wire_api": "responses",
                    "default_model": "gpt_54",
                }
            },
            "models": {
                "gpt_54": {
                    "provider": "openai",
                    "model_id": "gpt-5.4",
                    "planner_kind": "openai_responses",
                    "wire_api": "responses",
                    "interaction_profile": "codex_openai",
                }
            },
        }
    )

    entry = catalog.models["gpt_54"]
    assert entry.supported_reasoning_efforts == ("low", "medium", "high", "xhigh")
    assert entry.default_reasoning_effort == "xhigh"
    assert entry.supports_reasoning is True


def test_build_provider_catalog_preserves_explicit_gpt_55_reasoning_contract() -> None:
    catalog = build_provider_catalog(
        {
            "model_provider": "openai",
            "model": "gpt_55",
            "model_providers": {
                "openai": {
                    "base_url": "https://api.openai.com/v1",
                    "wire_api": "responses",
                    "default_model": "gpt_54",
                }
            },
            "models": {
                "gpt_55": {
                    "provider": "openai",
                    "model_id": "gpt-5.5",
                    "planner_kind": "openai_responses",
                    "wire_api": "responses",
                    "interaction_profile": "codex_openai",
                    "supports_reasoning": True,
                    "supported_reasoning_efforts": ["low", "medium", "high", "xhigh"],
                    "default_reasoning_effort": "",
                }
            },
        }
    )

    entry = catalog.models["gpt_55"]
    assert entry.supported_reasoning_efforts == ("low", "medium", "high", "xhigh")
    assert entry.default_reasoning_effort == ""
    assert entry.supports_reasoning is True


def test_build_provider_catalog_assigns_anthropic_reasoning_profiles() -> None:
    catalog = build_provider_catalog(
        {
            "model_provider": "anthropic",
            "model": "claude_opus_46",
            "model_providers": {
                "anthropic": {
                    "wire_api": "anthropic_messages",
                    "default_model": "claude_opus_46",
                }
            },
            "models": {
                "claude_opus_46": {
                    "provider": "anthropic",
                    "model_id": "claude-opus-4-6",
                    "planner_kind": "anthropic_messages",
                    "wire_api": "anthropic_messages",
                },
                "claude_haiku_45": {
                    "provider": "anthropic",
                    "model_id": "claude-haiku-4-5-20251001",
                    "planner_kind": "anthropic_messages",
                    "wire_api": "anthropic_messages",
                },
            },
        }
    )

    opus = catalog.models["claude_opus_46"]
    haiku = catalog.models["claude_haiku_45"]
    assert opus.supported_reasoning_efforts == ("low", "medium", "high")
    assert opus.default_reasoning_effort == ""
    assert opus.supports_reasoning is True
    assert haiku.supported_reasoning_efforts == ()
    assert haiku.default_reasoning_effort == ""
    assert haiku.supports_reasoning is False


def test_build_provider_catalog_preserves_explicit_empty_effort_list_for_deepseek_reasoner() -> (
    None
):
    catalog = build_provider_catalog(
        {
            "model_provider": "deepseek",
            "model": "deepseek_reasoner",
            "model_providers": {
                "deepseek": {
                    "wire_api": "openai_chat",
                    "default_model": "deepseek_reasoner",
                }
            },
            "models": {
                "deepseek_reasoner": {
                    "provider": "deepseek",
                    "model_id": "deepseek-reasoner",
                    "planner_kind": "deepseek_reasoner",
                    "wire_api": "openai_chat",
                    "supports_reasoning": True,
                    "supported_reasoning_efforts": [],
                    "default_reasoning_effort": "",
                    "reasoning_output_field": "reasoning_content",
                }
            },
        }
    )

    entry = catalog.models["deepseek_reasoner"]
    assert entry.supports_reasoning is True
    assert entry.supported_reasoning_efforts == ()
    assert entry.default_reasoning_effort == ""


def test_select_provider_config_clears_invalid_reasoning_effort_for_haiku() -> None:
    config = select_provider_config(
        env_mapping={},
        auth_data={"ANTHROPIC_API_KEY": "sk-test"},
        toml_data={
            "model_provider": "anthropic",
            "model": "claude_haiku_45",
            "model_reasoning_effort": "high",
            "model_providers": {
                "anthropic": {
                    "wire_api": "anthropic_messages",
                }
            },
            "models": {
                "claude_haiku_45": {
                    "provider": "anthropic",
                    "model_id": "claude-haiku-4-5-20251001",
                    "planner_kind": "anthropic_messages",
                    "wire_api": "anthropic_messages",
                }
            },
        },
        resolution=_resolution(),
    )

    assert config is not None
    assert config.reasoning_effort is None
    assert config.raw_model["supports_reasoning"] is False
    assert config.raw_model["supported_reasoning_efforts"] == []
    assert config.raw_model["default_reasoning_effort"] == ""


def test_select_provider_config_clears_invalid_reasoning_effort_for_deepseek_reasoner_without_dropping_reasoning() -> (
    None
):
    config = select_provider_config(
        env_mapping={},
        auth_data={"DEEPSEEK_API_KEY": "sk-test"},
        toml_data={
            "model_provider": "deepseek",
            "model": "deepseek_reasoner",
            "model_reasoning_effort": "high",
            "model_providers": {
                "deepseek": {
                    "wire_api": "openai_chat",
                }
            },
            "models": {
                "deepseek_reasoner": {
                    "provider": "deepseek",
                    "model_id": "deepseek-reasoner",
                    "planner_kind": "deepseek_reasoner",
                    "wire_api": "openai_chat",
                    "supports_reasoning": True,
                    "supported_reasoning_efforts": [],
                    "default_reasoning_effort": "",
                    "reasoning_output_field": "reasoning_content",
                }
            },
        },
        resolution=_resolution(),
    )

    assert config is not None
    assert config.reasoning_effort is None
    assert config.raw_model["supports_reasoning"] is True
    assert config.raw_model["supported_reasoning_efforts"] == []
    assert config.raw_model["default_reasoning_effort"] == ""


def test_model_catalog_reasoning_profile_resolves_provider_default_model() -> None:
    catalog = build_provider_catalog(
        {
            "model_provider": "openai",
            "model_providers": {
                "openai": {
                    "wire_api": "responses",
                    "default_model": "gpt_54",
                }
            },
            "models": {
                "gpt_54": {
                    "provider": "openai",
                    "model_id": "gpt-5.4",
                    "planner_kind": "openai_responses",
                    "wire_api": "responses",
                    "interaction_profile": "codex_openai",
                }
            },
        }
    )

    profile = model_catalog_reasoning_profile(
        catalog=catalog,
        provider_name="openai",
        model="",
        interaction_profile="codex_openai",
        planner_kind="openai_responses",
        wire_api="responses",
    )

    assert profile["provider_name"] == "openai"
    assert profile["model_key"] == "gpt_54"
    assert profile["model_id"] == "gpt-5.4"
    assert profile["supported_reasoning_efforts"] == ("low", "medium", "high", "xhigh")
    assert profile["default_reasoning_effort"] == "xhigh"


def test_model_catalog_reasoning_profile_preserves_reasoning_without_effort_options() -> None:
    catalog = build_provider_catalog(
        {
            "model_provider": "deepseek",
            "model_providers": {
                "deepseek": {
                    "wire_api": "openai_chat",
                    "default_model": "deepseek_reasoner",
                }
            },
            "models": {
                "deepseek_reasoner": {
                    "provider": "deepseek",
                    "model_id": "deepseek-reasoner",
                    "planner_kind": "deepseek_reasoner",
                    "wire_api": "openai_chat",
                    "supports_reasoning": True,
                    "supported_reasoning_efforts": [],
                    "default_reasoning_effort": "",
                }
            },
        }
    )

    profile = model_catalog_reasoning_profile(
        catalog=catalog,
        provider_name="deepseek",
        model="deepseek_reasoner",
        planner_kind="deepseek_reasoner",
        wire_api="openai_chat",
    )

    assert profile["model_id"] == "deepseek-reasoner"
    assert profile["supports_reasoning"] is True
    assert profile["supported_reasoning_efforts"] == ()
    assert profile["default_reasoning_effort"] == ""


def test_model_catalog_reasoning_profile_keeps_explicit_unknown_model() -> None:
    catalog = build_provider_catalog(
        {
            "model_provider": "anthropic",
            "model_providers": {
                "anthropic": {
                    "wire_api": "anthropic_messages",
                    "default_model": "claude_sonnet_46",
                }
            },
            "models": {
                "claude_sonnet_46": {
                    "provider": "anthropic",
                    "model_id": "claude-sonnet-4-6",
                    "planner_kind": "anthropic_messages",
                    "wire_api": "anthropic_messages",
                }
            },
        }
    )

    profile = model_catalog_reasoning_profile(
        catalog=catalog,
        provider_name="anthropic",
        model="claude-haiku-4-5",
        planner_kind="anthropic_messages",
        wire_api="anthropic_messages",
    )

    assert profile["model_key"] == ""
    assert profile["model_id"] == "claude-haiku-4-5"
    assert profile["supported_reasoning_efforts"] == ()
    assert profile["default_reasoning_effort"] == ""


def test_load_claude_provider_config_clears_unsupported_haiku_effort() -> None:
    with TemporaryDirectory() as temp_dir:
        home = Path(temp_dir)
        claude_dir = home / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        (claude_dir / "settings.json").write_text(
            json.dumps({"env": {"ANTHROPIC_MODEL": "claude-haiku-4-5"}}),
            encoding="utf-8",
        )
        (claude_dir / "config.json").write_text(
            json.dumps({"primaryApiKey": "sk-claude-home", "reasoningEffort": "high"}),
            encoding="utf-8",
        )
        (home / ".claude.json").write_text(
            json.dumps({"hasCompletedOnboarding": True}),
            encoding="utf-8",
        )

        config = load_claude_provider_config(env_mapping={}, home_dir=home)

    assert config is not None
    assert config.model == "claude-haiku-4-5"
    assert config.reasoning_effort is None
    assert config.raw_model["supports_reasoning"] is False
    assert config.raw_model["supported_reasoning_efforts"] == []
    assert config.raw_model["default_reasoning_effort"] == ""


def test_model_list_entry_payload_keeps_reasoning_default_empty_when_unsupported() -> None:
    payload = model_list_entry_payload(
        {
            "model_key": "claude_haiku_45",
            "provider_name": "anthropic",
            "model_id": "claude-haiku-4-5-20251001",
            "display_name": "Claude Haiku 4.5",
            "planner_kind": "anthropic_messages",
            "wire_api": "anthropic_messages",
            "supports_reasoning": "false",
            "supported_reasoning_efforts": [],
            "default_reasoning_effort": "",
        },
        current_model_tokens=set(),
        default_reasoning_effort="",
    )

    assert payload["supportedReasoningEfforts"] == []
    assert payload["defaultReasoningEffort"] == ""


def test_model_list_entry_payload_respects_explicit_empty_effort_list_for_reasoning_model() -> None:
    payload = model_list_entry_payload(
        {
            "model_key": "deepseek_reasoner",
            "provider_name": "deepseek",
            "model_id": "deepseek-reasoner",
            "display_name": "DeepSeek Reasoner",
            "planner_kind": "deepseek_reasoner",
            "wire_api": "openai_chat",
            "supports_reasoning": "true",
            "supported_reasoning_efforts": [],
            "default_reasoning_effort": "",
        },
        current_model_tokens=set(),
        default_reasoning_effort="",
    )

    assert payload["supportedReasoningEfforts"] == []
    assert payload["defaultReasoningEffort"] == ""

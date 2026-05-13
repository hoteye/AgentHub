from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli import agent_config_runtime, agent_provider_runtime
from cli.agent_cli.providers.availability_registry import AvailabilityRegistry
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.config_catalog_types import (
    ModelCatalogEntry,
    ProviderCatalog,
    ProviderCatalogEntry,
    ProviderPathResolution,
)


def test_expert_review_feature_settings_reads_merged_workspace_config() -> None:
    agent = SimpleNamespace(cwd=Path("/tmp/workspace"))

    with (
        patch(
            "cli.agent_cli.agent_provider_probe_runtime._effective_home_provider_config_path",
            return_value=Path("/tmp/runtime-home/config.toml"),
        ),
        patch(
            "cli.agent_cli.workspace_context.read_merged_project_toml",
            return_value=(
                {
                    "features": {
                        "expert_review": {
                            "enabled": False,
                            "min_eligible_providers": 4,
                            "prefer_cross_vendor": False,
                        }
                    }
                },
                [],
            ),
        ) as read_merged,
    ):
        settings = agent_provider_runtime.expert_review_feature_settings(agent)

    assert settings["enabled"] is False
    assert settings["config_source"] == "workspace_config"
    assert settings["min_eligible_providers"] == 4
    assert settings["prefer_cross_vendor"] is False
    assert settings["required_reasoning_effort"] == ""
    assert settings["reviewer_capability_policy"] == "capability_matrix_v1"
    read_merged.assert_called_once_with(
        cwd=Path("/tmp/workspace"),
        home_config_paths=[Path("/tmp/runtime-home/config.toml")],
    )


def test_available_providers_uses_provider_availability_stale_after_from_workspace_config() -> None:
    catalog = ProviderCatalog(
        providers={
            "openai": ProviderCatalogEntry(
                provider_name="openai",
                default_model="gpt_54",
                auth_mode="api_key",
                raw_provider={},
            ),
        },
        models={
            "gpt_54": ModelCatalogEntry(
                key="gpt_54",
                provider_name="openai",
                model_id="gpt-5.4",
                supports_reasoning=True,
            ),
        },
    )
    agent = SimpleNamespace(
        cwd=Path("/tmp/workspace"),
        _provider_availability_registry=AvailabilityRegistry(),
        _provider_loader_kwargs=lambda: {"cwd": Path("/tmp/workspace")},
        _session_provider_env_overrides={},
    )

    def _load_provider_inputs(**kwargs):
        del kwargs
        resolution = ProviderPathResolution(
            config_path=Path("/tmp/config.toml"),
            auth_path=Path("/tmp/auth.json"),
            config_exists=True,
            auth_exists=True,
            used_project_local=False,
        )
        return resolution, {}, {"OPENAI_API_KEY": "sk-openai"}

    with patch(
        "cli.agent_cli.workspace_context.read_merged_project_toml",
        return_value=(
            {"features": {"provider_availability": {"stale_after_seconds": 45}}},
            [],
        ),
    ):
        items = agent_provider_runtime.available_providers(
            agent,
            load_provider_catalog_fn=lambda **kwargs: catalog,
            load_provider_inputs_fn=_load_provider_inputs,
            supplement_catalog_fn=lambda item: item,
        )

    assert items[0]["availability_stale_after_seconds"] == 45


def test_provider_review_gate_uses_feature_settings_from_workspace_config() -> None:
    catalog = ProviderCatalog(
        providers={
            "openai": ProviderCatalogEntry(
                provider_name="openai",
                default_model="gpt_54",
                auth_mode="api_key",
                raw_provider={},
            ),
            "anthropic": ProviderCatalogEntry(
                provider_name="anthropic",
                default_model="claude_opus",
                auth_mode="api_key",
                raw_provider={},
            ),
        },
        models={
            "gpt_54": ModelCatalogEntry(
                key="gpt_54",
                provider_name="openai",
                model_id="gpt-5.4",
                supports_reasoning=True,
            ),
            "claude_opus": ModelCatalogEntry(
                key="claude_opus",
                provider_name="anthropic",
                model_id="claude-opus-4.1",
                supports_reasoning=True,
            ),
        },
    )
    agent = SimpleNamespace(
        cwd=Path("/tmp/workspace"),
        _planner=SimpleNamespace(
            public_summary=lambda: {
                "provider_name": "openai",
                "model": "gpt-5.4",
                "base_url": "https://api.openai.com/v1",
                "planner_kind": "openai_responses",
            }
        ),
        _session_provider_env_overrides={},
        _provider_loader_kwargs=lambda: {"cwd": Path("/tmp/workspace")},
    )

    def _load_provider_inputs(**kwargs):
        del kwargs
        resolution = ProviderPathResolution(
            config_path=Path("/tmp/config.toml"),
            auth_path=Path("/tmp/auth.json"),
            config_exists=True,
            auth_exists=True,
            used_project_local=False,
        )
        return resolution, {}, {"OPENAI_API_KEY": "sk-openai", "ANTHROPIC_API_KEY": "sk-anthropic"}

    with patch(
        "cli.agent_cli.workspace_context.read_merged_project_toml",
        return_value=(
            {
                "features": {
                    "expert_review": {
                        "enabled": False,
                        "min_eligible_providers": 3,
                    }
                }
            },
            [],
        ),
    ):
        gate = agent_provider_runtime.provider_review_gate(
            agent,
            load_provider_catalog_fn=lambda **kwargs: catalog,
            load_provider_inputs_fn=_load_provider_inputs,
            supplement_catalog_fn=lambda item: item,
        )

    assert gate["expert_review_available"] is False
    assert gate["expert_review_unavailable_reason"] == "feature_disabled"
    assert gate["expert_review_feature_enabled"] is False
    assert gate["expert_review_feature_source"] == "workspace_config"
    assert gate["expert_review_min_eligible_providers"] == 3
    assert gate["expert_review_required_reasoning_effort"] == "-"
    assert gate["expert_review_reviewer_capability_policy"] == "capability_matrix_v1"


def test_reload_planner_projects_expert_review_gate_snapshot_into_provider_config() -> None:
    captured: list[ProviderConfig] = []
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="test-key",
        provider_name="openai",
        raw_provider={"existing": "value"},
    )
    agent = SimpleNamespace(
        _planner=None,
        _planner_managed=False,
        _planner_error=None,
        _planner_runtime_error=None,
        _planner_runtime_error_diagnostics=None,
        _session_provider_env_overrides={},
        _session_route_overrides={},
        _session_delegation_overrides={},
        _runtime_policy_overrides={},
        _plugin_manager_factory=None,
        cwd=Path("/tmp/workspace"),
        host_platform=SimpleNamespace(),
        provider_review_gate=lambda: {
            "expert_review_available": True,
            "expert_review_unavailable_reason": "-",
            "expert_review_feature_enabled": True,
        },
    )

    agent_config_runtime.reload_planner(
        agent,
        resolve_provider_paths_fn=lambda **_kwargs: "paths",
        load_provider_config_fn=lambda **_kwargs: config,
        build_planner_fn=lambda planner_config, **_kwargs: captured.append(planner_config)
        or SimpleNamespace(),
    )

    assert captured
    planner_config = captured[0]
    assert planner_config.raw_provider["existing"] == "value"
    assert planner_config.raw_provider["expert_review_available"] is True
    assert (
        planner_config.raw_provider["expert_review_gate_snapshot"]["expert_review_available"]
        is True
    )


def test_reload_planner_preserves_gate_snapshot_from_existing_primary_provider_context() -> None:
    captured: list[ProviderConfig] = []
    config = ProviderConfig(
        model="claude-sonnet-4-6",
        api_key="test-key",
        provider_name="anthropic",
        raw_provider={"existing": "value"},
    )
    agent = SimpleNamespace(
        _planner=SimpleNamespace(
            public_summary=lambda: {
                "provider_name": "anthropic",
                "model": "claude-sonnet-4-6",
                "base_url": "https://relay.example/claudecode",
                "planner_kind": "anthropic_messages",
            }
        ),
        _planner_managed=True,
        _planner_error=None,
        _planner_runtime_error=None,
        _planner_runtime_error_diagnostics=None,
        _session_provider_env_overrides={},
        _session_route_overrides={},
        _session_delegation_overrides={},
        _runtime_policy_overrides={},
        _plugin_manager_factory=None,
        cwd=Path("/tmp/workspace"),
        host_platform=SimpleNamespace(),
    )

    def _provider_review_gate():
        if getattr(agent, "_planner", None) is None:
            return {
                "expert_review_available": False,
                "expert_review_unavailable_reason": "primary_provider_unknown",
            }
        return {
            "expert_review_available": True,
            "expert_review_unavailable_reason": "-",
            "primary_provider_name": "anthropic",
        }

    agent.provider_review_gate = _provider_review_gate

    agent_config_runtime.reload_planner(
        agent,
        resolve_provider_paths_fn=lambda **_kwargs: "paths",
        load_provider_config_fn=lambda **_kwargs: config,
        build_planner_fn=lambda planner_config, **_kwargs: captured.append(planner_config)
        or SimpleNamespace(),
    )

    assert captured
    planner_config = captured[0]
    assert planner_config.raw_provider["expert_review_available"] is True
    assert planner_config.raw_provider["expert_review_unavailable_reason"] == "-"
    assert (
        planner_config.raw_provider["expert_review_gate_snapshot"]["primary_provider_name"]
        == "anthropic"
    )


def test_lazy_planner_defers_expert_review_gate_until_build() -> None:
    captured: list[ProviderConfig] = []
    config = ProviderConfig(
        model="gpt-5.4",
        api_key="test-key",
        provider_name="openai",
        raw_provider={"existing": "value"},
    )
    gate_calls = {"count": 0}
    agent = SimpleNamespace(
        _planner=None,
        _planner_managed=False,
        _planner_error=None,
        _planner_runtime_error=None,
        _planner_runtime_error_diagnostics=None,
        _planner_config=None,
        _planner_build_pending=False,
        _session_provider_env_overrides={},
        _session_route_overrides={},
        _session_delegation_overrides={},
        _runtime_policy_overrides={},
        _plugin_manager_factory=None,
        cwd=Path("/tmp/workspace"),
        host_platform=SimpleNamespace(),
    )

    def _provider_review_gate():
        gate_calls["count"] += 1
        return {"expert_review_available": True}

    agent.provider_review_gate = _provider_review_gate

    agent_config_runtime.prepare_lazy_planner(
        agent,
        resolve_provider_paths_fn=lambda **_kwargs: "paths",
        load_provider_config_fn=lambda **_kwargs: config,
        apply_review_gate=False,
    )

    assert gate_calls["count"] == 0
    assert agent._planner_config.raw_provider == {"existing": "value"}

    agent_config_runtime.build_pending_planner(
        agent,
        build_planner_fn=lambda planner_config, **_kwargs: captured.append(planner_config)
        or SimpleNamespace(),
    )

    assert gate_calls["count"] == 1
    assert captured[0].raw_provider["expert_review_available"] is True

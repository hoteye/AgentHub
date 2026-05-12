from __future__ import annotations

from unittest.mock import patch

from cli.agent_cli.agent import RuleBasedAgent
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.model_routing import resolve_delegation_config, resolve_route_config

def _base_config() -> ProviderConfig:
    return ProviderConfig(
        model="gpt-5.4",
        api_key="sk-test",
        provider_name="openai",
        model_key="gpt_54",
        planner_kind="openai_responses",
        wire_api="responses",
        base_url="https://relay.example/v1",
        reasoning_effort="high",
        raw_model={},
    )

def test_resolve_route_config_uses_explicit_route_selector_and_reasoning() -> None:
    config = _base_config()
    config.raw_model = {
        "routes": {
            "policy_helper": {
                "model": "deepseek_chat",
                "reasoning_effort": "low",
                "timeout": 18,
            }
        }
    }
    resolved_config = ProviderConfig(
        model="deepseek-chat",
        api_key="sk-deepseek",
        provider_name="deepseek",
        model_key="deepseek_chat",
        planner_kind="deepseek_chat",
        wire_api="openai_chat",
        base_url="https://api.deepseek.com",
        reasoning_effort="low",
    )

    with patch(
        "cli.agent_cli.provider.load_provider_config",
        return_value=resolved_config,
    ) as load_provider_config:
        route = resolve_route_config(config, "policy_helper", cwd="/tmp/work")

    load_provider_config.assert_called_once_with(
        cwd="/tmp/work",
        env_overrides={
            "AGENT_CLI_MODEL": "deepseek_chat",
            "AGENT_CLI_REASONING_EFFORT": "low",
        },
    )
    assert route.config == resolved_config
    assert route.timeout == 18
    assert route.source == "route"
    assert route.configured is True

def test_resolve_route_config_supports_reasoning_only_override() -> None:
    config = _base_config()
    config.raw_model = {
        "routes": {
            "final_synthesis": {
                "reasoning_effort": "medium",
                "timeout": 25,
            }
        }
    }

    route = resolve_route_config(config, "final_synthesis")

    assert route.source == "route"
    assert route.timeout == 25
    assert route.config is not None
    assert route.config.model == "gpt-5.4"
    assert route.config.reasoning_effort == "medium"

def test_resolve_route_config_falls_back_to_legacy_selector_when_no_route_block() -> None:
    config = _base_config()
    resolved_config = ProviderConfig(
        model="deepseek-chat",
        api_key="sk-deepseek",
        provider_name="deepseek",
        model_key="deepseek_chat",
        planner_kind="deepseek_chat",
        wire_api="openai_chat",
        base_url="https://api.deepseek.com",
        reasoning_effort="low",
    )

    with patch(
        "cli.agent_cli.provider.load_provider_config",
        return_value=resolved_config,
    ) as load_provider_config:
        route = resolve_route_config(
            config,
            "policy_helper",
            cwd="/tmp/work",
            default_timeout=20,
            legacy_selector="deepseek-chat",
        )

    load_provider_config.assert_called_once_with(
        cwd="/tmp/work",
        env_overrides={"AGENT_CLI_MODEL": "deepseek-chat"},
    )
    assert route.config == resolved_config
    assert route.timeout == 20
    assert route.source == "legacy"

def test_resolve_delegation_config_uses_explicit_selector_and_cross_provider() -> None:
    config = _base_config()
    config.raw_model = {
        "delegation": {
            "teammate": {
                "provider": "glm",
                "model": "glm_5",
                "reasoning_effort": "medium",
                "timeout": 40,
            }
        }
    }
    resolved_config = ProviderConfig(
        model="glm-5",
        api_key="sk-glm",
        provider_name="glm",
        model_key="glm_5",
        planner_kind="openai_chat",
        wire_api="openai_chat",
        base_url="https://glm.example/v1",
        reasoning_effort="medium",
    )

    with patch(
        "cli.agent_cli.provider.load_provider_config",
        return_value=resolved_config,
    ) as load_provider_config:
        delegation = resolve_delegation_config(config, "teammate", cwd="/tmp/work")

    load_provider_config.assert_called_once_with(
        cwd="/tmp/work",
        env_overrides={
            "AGENT_CLI_PROVIDER": "glm",
            "AGENT_CLI_MODEL": "glm_5",
            "AGENT_CLI_REASONING_EFFORT": "medium",
        },
    )
    assert delegation.config == resolved_config
    assert delegation.timeout == 40
    assert delegation.source == "delegation"
    assert delegation.configured is True

def test_resolve_delegation_config_defaults_to_inherit_main() -> None:
    config = _base_config()

    delegation = resolve_delegation_config(config, "subagent")

    assert delegation.config is not None
    assert delegation.config.model == "gpt-5.4"
    assert delegation.timeout is None
    assert delegation.source == "inherit_main"
    assert delegation.configured is False

def test_resolve_delegation_config_supports_explicit_inherit_selector() -> None:
    config = _base_config()
    config.raw_model = {
        "delegation": {
            "subagent": {
                "model": "inherit",
                "reasoning_effort": "medium",
                "timeout": 22,
            }
        }
    }

    delegation = resolve_delegation_config(config, "subagent")

    assert delegation.config is not None
    assert delegation.config.model == "gpt-5.4"
    assert delegation.config.reasoning_effort == "medium"
    assert delegation.timeout == 22
    assert delegation.source == "delegation_inherit_main"
    assert delegation.configured is True

def test_rule_based_agent_resolve_delegate_execution_applies_explicit_inherit_override() -> None:
    agent = RuleBasedAgent()
    agent.set_planner_override(type("PlannerStub", (), {"config": _base_config()})())

    delegation = agent.resolve_delegate_execution(
        "subagent",
        model="inherit",
        reasoning_effort="medium",
        timeout=22,
    )

    assert delegation.config is not None
    assert delegation.config.model == "gpt-5.4"
    assert delegation.config.reasoning_effort == "medium"
    assert delegation.timeout == 22
    assert delegation.source == "call_override_inherit_main"

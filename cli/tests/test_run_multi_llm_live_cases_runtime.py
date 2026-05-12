from __future__ import annotations

from cli.agent_cli.providers.config_catalog_types import ProviderConfig
from cli.scripts.run_multi_llm_live_cases_runtime import overlay_multi_llm_routes


def _config(*, raw_model: dict | None = None) -> ProviderConfig:
    return ProviderConfig(
        provider_name="openai",
        model_key="gpt_54",
        model="gpt-5.4",
        api_key="test-key",
        planner_kind="openai_responses",
        wire_api="responses",
        raw_model=dict(raw_model or {}),
    )


def test_overlay_multi_llm_routes_fills_defaults_when_routes_are_missing() -> None:
    config = overlay_multi_llm_routes(
        _config(),
        default_tool_followup_provider="glm",
        default_tool_followup_model="glm_5",
        default_tool_followup_reasoning_effort="high",
        default_tool_followup_timeout=30,
        default_final_synthesis_provider="glm",
        default_final_synthesis_model="glm_5",
        default_final_synthesis_reasoning_effort="high",
        default_final_synthesis_timeout=30,
    )

    routes = dict(config.raw_model.get("routes") or {})
    assert routes["tool_followup"] == {
        "provider": "glm",
        "model": "glm_5",
        "reasoning_effort": "high",
        "timeout": 30,
    }
    assert routes["final_synthesis"] == {
        "provider": "glm",
        "model": "glm_5",
        "reasoning_effort": "high",
        "timeout": 30,
    }


def test_overlay_multi_llm_routes_preserves_existing_routes_when_no_override_is_given() -> None:
    config = overlay_multi_llm_routes(
        _config(
            raw_model={
                "routes": {
                    "tool_followup": {
                        "provider": "deepseek",
                        "model": "deepseek_chat",
                        "reasoning_effort": "low",
                        "timeout": 20,
                    }
                }
            }
        ),
        default_tool_followup_provider="glm",
        default_tool_followup_model="glm_5",
        default_tool_followup_reasoning_effort="high",
        default_tool_followup_timeout=30,
        default_final_synthesis_provider="glm",
        default_final_synthesis_model="glm_5",
        default_final_synthesis_reasoning_effort="high",
        default_final_synthesis_timeout=30,
    )

    routes = dict(config.raw_model.get("routes") or {})
    assert routes["tool_followup"] == {
        "provider": "deepseek",
        "model": "deepseek_chat",
        "reasoning_effort": "low",
        "timeout": 20,
    }
    assert routes["final_synthesis"] == {
        "provider": "glm",
        "model": "glm_5",
        "reasoning_effort": "high",
        "timeout": 30,
    }


def test_overlay_multi_llm_routes_applies_explicit_overrides() -> None:
    config = overlay_multi_llm_routes(
        _config(
            raw_model={
                "routes": {
                    "tool_followup": {
                        "provider": "glm",
                        "model": "glm_5",
                        "reasoning_effort": "high",
                        "timeout": 30,
                    }
                }
            }
        ),
        default_tool_followup_provider="glm",
        default_tool_followup_model="glm_5",
        default_tool_followup_reasoning_effort="high",
        default_tool_followup_timeout=30,
        default_final_synthesis_provider="glm",
        default_final_synthesis_model="glm_5",
        default_final_synthesis_reasoning_effort="high",
        default_final_synthesis_timeout=30,
        tool_followup_provider="deepseek",
        tool_followup_model="deepseek_reasoner",
        tool_followup_reasoning_effort="medium",
        tool_followup_timeout=45,
    )

    routes = dict(config.raw_model.get("routes") or {})
    assert routes["tool_followup"] == {
        "provider": "deepseek",
        "model": "deepseek_reasoner",
        "reasoning_effort": "medium",
        "timeout": 45,
    }

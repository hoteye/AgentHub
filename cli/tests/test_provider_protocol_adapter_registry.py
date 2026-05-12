from cli.agent_cli.providers.protocol_adapter_registry import (
    adapter_for_family,
    adapter_for_planner_kind,
    protocol_adapters,
)
from cli.agent_cli.providers.protocols.anthropic_messages import AnthropicClaudePlanner
from cli.agent_cli.providers.protocols.openai_chat import ChatCompletionsPlanner
from cli.agent_cli.providers.protocols.openai_responses import OpenAIPlanner


def test_adapter_for_family_maps_known_values() -> None:
    assert adapter_for_family("openai_responses").planner_class is OpenAIPlanner
    assert adapter_for_family("openai_chat").planner_class is ChatCompletionsPlanner
    assert adapter_for_family("anthropic_messages").planner_class is AnthropicClaudePlanner
    assert adapter_for_family("missing") is None


def test_adapter_for_planner_kind_unknown_falls_back_to_openai_responses() -> None:
    assert adapter_for_planner_kind("unknown_kind").planner_class is OpenAIPlanner
    assert adapter_for_planner_kind("").planner_class is OpenAIPlanner


def test_adapter_registry_smoke_matrix_for_provider_families() -> None:
    # openai
    assert adapter_for_planner_kind("openai_responses").planner_class is OpenAIPlanner
    # deepseek (openai-compatible chat family)
    assert adapter_for_planner_kind("deepseek_chat").planner_class is ChatCompletionsPlanner
    assert adapter_for_planner_kind("deepseek_reasoner").planner_class is ChatCompletionsPlanner
    # glm (openai-compatible chat family)
    assert adapter_for_planner_kind("openai_chat").planner_class is ChatCompletionsPlanner
    # anthropic
    assert adapter_for_planner_kind("anthropic_messages").planner_class is AnthropicClaudePlanner
    # unknown -> degrade to default family
    assert adapter_for_planner_kind("totally_unknown_family").planner_class is OpenAIPlanner


def test_protocol_adapters_include_minimum_runtime_families() -> None:
    names = {adapter.family.name for adapter in protocol_adapters()}
    assert "openai_responses" in names
    assert "openai_chat" in names
    assert "anthropic_messages" in names

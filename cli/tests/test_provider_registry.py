from unittest.mock import patch

from cli.agent_cli.provider import build_planner as legacy_build_planner
from cli.agent_cli.providers.config.catalog import ProviderConfig
from cli.agent_cli.providers.protocols.anthropic_messages import AnthropicClaudePlanner
from cli.agent_cli.providers.protocols.openai_chat import ChatCompletionsPlanner
from cli.agent_cli.providers.protocols.openai_responses import OpenAIPlanner
from cli.agent_cli.providers.registry import infer_vendor, model_selector_for_line, planner_class_for_kind


def test_planner_class_for_kind_matches_protocol_families() -> None:
    assert planner_class_for_kind("anthropic_messages") is AnthropicClaudePlanner
    assert planner_class_for_kind("openai_chat") is ChatCompletionsPlanner
    assert planner_class_for_kind("deepseek_chat") is ChatCompletionsPlanner
    assert planner_class_for_kind("deepseek_reasoner") is ChatCompletionsPlanner
    assert planner_class_for_kind("openai_responses") is OpenAIPlanner
    assert planner_class_for_kind("") is OpenAIPlanner
    assert planner_class_for_kind("unknown_kind") is OpenAIPlanner

def test_legacy_provider_build_planner_delegates_to_registry() -> None:
    config = ProviderConfig(model="gpt-5.4", api_key="test-key", planner_kind="openai_responses")
    sentinel = object()

    with patch("cli.agent_cli.provider._build_planner_impl", return_value=sentinel) as build_impl:
        planner = legacy_build_planner(config)

    assert planner is sentinel
    build_impl.assert_called_once_with(
        config,
        host_platform=None,
        cwd=None,
        plugin_manager_factory=None,
    )

def test_infer_vendor_recognizes_vendor_aliases_and_fingerprints() -> None:
    assert infer_vendor(provider_name="deepseek").name == "deepseek"
    assert infer_vendor(provider_name="claude").name == "anthropic"
    assert infer_vendor(model="claude-sonnet-4-6", planner_kind="anthropic_messages").name == "anthropic"
    assert infer_vendor(model="gpt-5.4", planner_kind="openai_responses").name == "openai"
    assert infer_vendor(provider_name="glm").name == "glm"

def test_model_selector_for_line_comes_from_vendor_contract() -> None:
    assert model_selector_for_line(line="chat", provider_name="deepseek") == "deepseek-chat"
    assert model_selector_for_line(line="reasoner", model="deepseek-chat") == "deepseek-reasoner"
    assert model_selector_for_line(line="chat", provider_name="anthropic") is None


def test_infer_vendor_smoke_matrix_and_unknown_degrade() -> None:
    assert infer_vendor(provider_name="openai").name == "openai"
    assert infer_vendor(provider_name="deepseek").name == "deepseek"
    assert infer_vendor(provider_name="glm").name == "glm"
    assert infer_vendor(provider_name="anthropic").name == "anthropic"
    assert infer_vendor(provider_name="unknown-provider") is None

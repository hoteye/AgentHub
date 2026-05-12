from __future__ import annotations

from dataclasses import dataclass

import pytest

from cli.agent_cli.host_platform import current_host_platform
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.tool_specs import merged_provider_tool_specs
from cli.agent_cli.tools_core.tool_backend_registry import (
    BACKEND_LOCAL_WEB_SEARCH,
    BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH,
    BACKEND_PROVIDER_NATIVE_GLM_WEB_SEARCH,
    BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH,
)
from cli.agent_cli.tools_core.tool_capability_resolver import (
    WebSearchResolverInput,
    resolve_web_search_capability,
)
from cli.agent_cli.tools_core.web_tools_runtime import runtime_web_search_route


@dataclass(frozen=True)
class _Case:
    label: str
    config: ProviderConfig
    expected_resolver_backend: str
    expected_resolver_availability: str
    expected_merged_spec_type: str
    expected_route_effective_backend: str
    expected_route_execution_path: str


def _web_search_spec_type(config: ProviderConfig) -> str:
    specs = merged_provider_tool_specs(
        config,
        current_host_platform(),
        plugin_manager_factory=lambda: None,
    )
    for item in specs:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip()
        if item_type == "web_search":
            return "web_search"
        function_block = item.get("function")
        if item_type == "function" and isinstance(function_block, dict):
            if str(function_block.get("name") or "").strip() == "web_search":
                return "function"
    raise AssertionError("merged_provider_tool_specs did not expose web_search")


@pytest.mark.parametrize(
    "case",
    [
        _Case(
            label="openai:gpt-5.4",
            config=ProviderConfig(
                model="gpt-5.4",
                api_key="sk-test",
                provider_name="openai",
                planner_kind="openai_responses",
                wire_api="responses",
            ),
            expected_resolver_backend=BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH,
            expected_resolver_availability="supported",
            expected_merged_spec_type="function",
            expected_route_effective_backend=BACKEND_PROVIDER_NATIVE_OPENAI_RESPONSES_WEB_SEARCH,
            expected_route_execution_path="openai_responses_native",
        ),
        _Case(
            label="anthropic:claude-sonnet-4-6",
            config=ProviderConfig(
                model="claude-sonnet-4-6",
                api_key="sk-test",
                provider_name="anthropic",
                planner_kind="anthropic_messages",
                wire_api="anthropic_messages",
            ),
            expected_resolver_backend=BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH,
            expected_resolver_availability="supported",
            expected_merged_spec_type="function",
            expected_route_effective_backend=BACKEND_PROVIDER_NATIVE_ANTHROPIC_WEB_SEARCH,
            expected_route_execution_path="anthropic_native",
        ),
        _Case(
            label="deepseek:deepseek-chat",
            config=ProviderConfig(
                model="deepseek-chat",
                api_key="sk-test",
                provider_name="deepseek",
                planner_kind="deepseek_chat",
                wire_api="openai_chat",
            ),
            expected_resolver_backend=BACKEND_LOCAL_WEB_SEARCH,
            expected_resolver_availability="unsupported",
            expected_merged_spec_type="function",
            expected_route_effective_backend=BACKEND_LOCAL_WEB_SEARCH,
            expected_route_execution_path="local_fallback",
        ),
        _Case(
            label="glm:glm-5(default)",
            config=ProviderConfig(
                model="glm-5",
                api_key="sk-test",
                provider_name="glm",
                planner_kind="openai_chat",
                wire_api="openai_chat",
            ),
            expected_resolver_backend=BACKEND_PROVIDER_NATIVE_GLM_WEB_SEARCH,
            expected_resolver_availability="unknown",
            expected_merged_spec_type="web_search",
            expected_route_effective_backend=BACKEND_LOCAL_WEB_SEARCH,
            expected_route_execution_path="local_fallback",
        ),
        _Case(
            label="glm:glm-5(native_web_search=false)",
            config=ProviderConfig(
                model="glm-5",
                api_key="sk-test",
                provider_name="glm",
                planner_kind="openai_chat",
                wire_api="openai_chat",
                raw_model={"native_web_search": False},
            ),
            expected_resolver_backend=BACKEND_PROVIDER_NATIVE_GLM_WEB_SEARCH,
            expected_resolver_availability="unknown",
            expected_merged_spec_type="function",
            expected_route_effective_backend=BACKEND_LOCAL_WEB_SEARCH,
            expected_route_execution_path="local_fallback",
        ),
    ],
    ids=lambda value: value.label,
)
def test_unified_tool_layer_redirection_matrix(case: _Case) -> None:
    resolver_snapshot = resolve_web_search_capability(
        WebSearchResolverInput(
            provider_name=case.config.provider_name,
            model=case.config.model,
            wire_api=case.config.wire_api or "",
            planner_kind=case.config.planner_kind or "",
        )
    )
    merged_spec_type = _web_search_spec_type(case.config)
    route = runtime_web_search_route(provider_config=case.config)

    assert resolver_snapshot.selected_backend == case.expected_resolver_backend
    assert resolver_snapshot.availability == case.expected_resolver_availability
    assert merged_spec_type == case.expected_merged_spec_type
    assert route["effective_backend_id"] == case.expected_route_effective_backend
    assert route["execution_path"] == case.expected_route_execution_path

    if route["effective_backend_id"] == BACKEND_LOCAL_WEB_SEARCH:
        assert isinstance(route["fallback_reason"], str)
    else:
        assert route["fallback_reason"] == ""

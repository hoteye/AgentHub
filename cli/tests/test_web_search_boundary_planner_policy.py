from __future__ import annotations

import cli.agent_cli.providers.chat_completions_planner as chat_module
import cli.agent_cli.providers.openai_planner as openai_module
from cli.agent_cli.host_platform import detect_host_platform
from cli.agent_cli.providers.config_catalog import ProviderConfig


def _host_platform(system_name: str = "Linux", sys_platform: str = "linux"):
    return detect_host_platform(system_name=system_name, sys_platform=sys_platform)


def _provider_config(
    *,
    planner_kind: str = "openai_responses",
    raw_model: dict | None = None,
    raw_provider: dict | None = None,
) -> ProviderConfig:
    return ProviderConfig(
        model="gpt-5.4",
        api_key="test-key",
        planner_kind=planner_kind,
        raw_model=dict(raw_model or {}),
        raw_provider=dict(raw_provider or {}),
    )


def test_chat_completions_planner_uses_config_aware_disabled_web_search_prompt(monkeypatch) -> None:
    monkeypatch.setattr(chat_module, "build_openai_client", lambda *args, **kwargs: object())

    planner = chat_module.ChatCompletionsPlanner(
        _provider_config(
            planner_kind="openai_chat",
            raw_provider={"web_search_mode": "disabled"},
        ),
        host_platform=_host_platform(),
        plugin_manager_factory=lambda: None,
    )

    assert "Do not promise live web lookup unless web_search is actually exposed in this session." in planner.system_prompt


def test_openai_planner_chat_route_prompt_uses_route_config_native_web_search_boundary(monkeypatch) -> None:
    monkeypatch.setattr(openai_module, "build_openai_client", lambda *args, **kwargs: object())

    planner = openai_module.OpenAIPlanner(
        _provider_config(),
        host_platform=_host_platform(),
        plugin_manager_factory=lambda: None,
    )
    prompt = planner._chat_route_system_prompt(
        ProviderConfig(
            model="claude-sonnet-4-6",
            api_key="test-key",
            provider_name="anthropic",
            planner_kind="anthropic_messages",
            raw_model={"native_web_search_mixed_tools": True},
        )
    )

    assert "When the provider exposes native web_search in this session" in prompt
    assert "If the user already gives a concrete public URL, prefer web_fetch directly instead of web_search unless the task requires browser navigation or interaction." in prompt


def test_openai_planner_default_command_patterns_cover_canonical_browser_path() -> None:
    assert openai_module.OpenAIPlanner._COMMAND_PATTERN.search("/browser open --url https://example.com")
    assert openai_module.OpenAIPlanner._FOLLOWUP_COMMAND_PATTERN.search(" then /browser snapshot")

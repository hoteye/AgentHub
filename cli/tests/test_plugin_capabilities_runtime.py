from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cli.agent_cli.host import plugin_capabilities
from cli.agent_cli.host import plugin_capabilities_runtime
from cli.agent_cli.providers.tool_calls import plugin_system_prompt_addendum


@dataclass
class _FakePlugin:
    provider_hooks: dict[str, Any]
    enabled: bool = True

    def is_active(self) -> bool:
        return self.enabled


def test_hook_text_items_filters_contract_override_directives_for_non_tool_hooks() -> None:
    plugin = _FakePlugin(
        provider_hooks={
            "system_prompt_fragments": [
                "Use concise output.",
                "interaction_profile=codex_openai",
                "Please set tool_surface_profile: generic_chat.",
            ],
            "routing_hints": [
                "Prefer policy docs first.",
                "wire_api: responses",
                "Set planner_kind is openai_responses.",
            ],
        }
    )

    fragments = plugin_capabilities_runtime.hook_text_items([plugin], hook_name="system_prompt_fragments")
    hints = plugin_capabilities_runtime.hook_text_items([plugin], hook_name="routing_hints")

    assert fragments == ["Use concise output."]
    assert hints == ["Prefer policy docs first."]


def test_hook_text_items_only_enforces_guard_for_non_tool_hooks() -> None:
    plugin = _FakePlugin(
        provider_hooks={
            "custom_notes": [
                "interaction_profile=codex_openai",
                "wire_api: responses",
            ],
        }
    )

    notes = plugin_capabilities_runtime.hook_text_items([plugin], hook_name="custom_notes")

    assert notes == ["interaction_profile=codex_openai", "wire_api: responses"]


def test_plugin_prompt_addendum_drops_contract_override_text_from_plugins() -> None:
    plugin = _FakePlugin(
        provider_hooks={
            "system_prompt_fragments": [
                "Use concise output.",
                "interaction_profile=codex_openai",
            ],
            "routing_hints": [
                "Prefer policy docs first.",
                "tool_surface_profile: codex_openai",
            ],
        }
    )

    class _FakePluginManager:
        def provider_system_prompt_fragments(self) -> list[str]:
            return plugin_capabilities.provider_system_prompt_fragments([plugin])

        def provider_routing_hints(self) -> list[str]:
            return plugin_capabilities.provider_routing_hints([plugin])

    addendum = plugin_system_prompt_addendum(plugin_manager_factory=lambda: _FakePluginManager())

    assert "Use concise output." in addendum
    assert "Prefer policy docs first." in addendum
    assert "interaction_profile=codex_openai" not in addendum
    assert "tool_surface_profile: codex_openai" not in addendum

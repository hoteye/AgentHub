from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli.providers import tool_family_mapping_runtime
from cli.agent_cli.providers import tool_family_registry

class _FakePluginManager:
    def __init__(self, capability_specs: List[Dict[str, Any]]) -> None:
        self._capability_specs = list(capability_specs)

    def tool_specs(self) -> List[Dict[str, Any]]:
        return list(self._capability_specs)

def test_tool_family_registry_reexports_family_mapping_constants() -> None:
    assert tool_family_registry.BUILTIN_TOOL_ORDER == tool_family_mapping_runtime.BUILTIN_TOOL_ORDER
    assert tool_family_registry.RESPONSES_MINIMAL_TOOL_ORDER == tool_family_mapping_runtime.RESPONSES_MINIMAL_TOOL_ORDER
    assert tool_family_registry.BROWSER_RUNTIME_ACTIONS == tool_family_mapping_runtime.BROWSER_RUNTIME_ACTIONS
    assert tool_family_registry.BROWSER_PROVIDER_ACTIONS == tool_family_mapping_runtime.BROWSER_PROVIDER_ACTIONS

def test_tool_family_registry_normalize_capability_spec_preserves_plugin_name() -> None:
    normalized = tool_family_registry.normalize_capability_spec(
        {
            "name": "demo_lookup",
            "description": "demo",
            "mutates_ui": True,
            "requires_confirmation": False,
            "slash_actions": [" open ", "", "open", "navigate"],
            "provider_actions": (" tabs", "tabs", "close "),
            "plugin_name": "demo_plugin",
        }
    )

    assert normalized is not None
    assert normalized["name"] == "demo_lookup"
    assert normalized["label"] == "demo_lookup"
    assert normalized["description"] == "demo"
    assert normalized["mutates_ui"] is True
    assert normalized["requires_confirmation"] is False
    assert normalized["plugin_name"] == "demo_plugin"

def test_tool_family_registry_merged_capability_specs_uses_projection_runtime() -> None:
    specs = tool_family_registry.merged_capability_specs(
        plugin_manager_factory=lambda: _FakePluginManager(
            [
                {
                    "name": "web_search",
                    "description": "plugin override",
                    "mutates_ui": True,
                    "requires_confirmation": True,
                    "plugin_name": "demo_plugin",
                }
            ]
        )
    )

    web_search = next(item for item in specs if item["name"] == "web_search")

    assert web_search["description"] == "plugin override"
    assert web_search["mutates_ui"] is True
    assert web_search["requires_confirmation"] is True
    assert web_search["plugin_name"] == "demo_plugin"

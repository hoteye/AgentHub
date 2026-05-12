from __future__ import annotations

import os
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from cli.agent_cli.host import plugin_capabilities
from cli.agent_cli.host import plugin_capability_compat_runtime
from cli.agent_cli.host import plugin_registry


@dataclass
class _FakePlugin:
    provider_hooks: dict[str, Any]
    enabled: bool = True
    plugin_name: str = "demo_plugin"

    def is_active(self) -> bool:
        return self.enabled


def test_provider_tool_specs_hides_undeclared_legacy_tools_by_default() -> None:
    plugin = _FakePlugin(
        provider_hooks={
            "tool_specs": [
                {
                    "name": "legacy_lookup",
                    "description": "legacy provider tool without declarations",
                    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                }
            ]
        }
    )

    specs = plugin_capabilities.provider_tool_specs([plugin])
    warnings = plugin_capabilities.provider_tool_compat_warnings([plugin])

    assert specs == []
    assert len(warnings) == 1
    assert "legacy_lookup" in warnings[0]
    assert "legacy_hidden_undeclared" in warnings[0]


def test_provider_tool_specs_keeps_declared_capability_items_model_visible() -> None:
    plugin = _FakePlugin(
        provider_hooks={
            "tool_specs": [
                {
                    "name": "declared_lookup",
                    "description": "declared provider tool",
                    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                    "capability": {
                        "capability_id": "plugin.demo.lookup",
                        "supported_profiles": ["generic_chat"],
                        "default_visibility": "model_visible",
                    },
                }
            ]
        }
    )

    specs = plugin_capabilities.provider_tool_specs([plugin])
    warnings = plugin_capabilities.provider_tool_compat_warnings([plugin])

    assert [item["function"]["name"] for item in specs] == ["declared_lookup"]
    assert warnings == []


def test_provider_tool_specs_supports_explicit_legacy_visibility_override() -> None:
    plugin = _FakePlugin(
        provider_hooks={
            "tool_specs": [
                {
                    "name": "legacy_override_tool",
                    "description": "legacy provider tool",
                    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                }
            ]
        }
    )

    with patch.dict(
        os.environ,
        {plugin_capability_compat_runtime.LEGACY_PROVIDER_TOOL_SPECS_MODEL_VISIBLE_ENV: "1"},
        clear=False,
    ):
        specs = plugin_capabilities.provider_tool_specs([plugin])

    assert [item["function"]["name"] for item in specs] == ["legacy_override_tool"]


def test_host_direct_execution_path_remains_unaffected_by_provider_tool_visibility() -> None:
    tool_entry = SimpleNamespace(handler=lambda text: f"ok:{text}")
    result = plugin_registry.invoke_tool(
        {"legacy_host_tool": tool_entry},
        name="legacy_host_tool",
        args=("x",),
        kwargs={},
    )
    assert result == "ok:x"


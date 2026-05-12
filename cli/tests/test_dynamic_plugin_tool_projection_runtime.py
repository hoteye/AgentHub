from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli.host_platform import current_host_platform
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.tool_specs import merged_provider_tool_specs, provider_tool_names


def _function_spec(name: str, description: str = "plugin tool") -> Dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    }


def _task_a_declaration(
    *,
    tool_name: str,
    canonical_family: str | None = None,
    tool_capability_kind: str = "local_runtime_tool",
    tool_runtime_binding: str = "plugin_runtime",
    supported_profiles: List[str] | None = None,
    default_visibility: str = "model_visible",
    canonical_family_source: str = "dynamic",
    canonical_family_owner: str = "test_plugin",
) -> Dict[str, Any]:
    family_name = canonical_family or tool_name
    return {
        "tool_name": tool_name,
        "canonical_family": family_name,
        "canonical_family_source": canonical_family_source,
        "canonical_family_owner": canonical_family_owner,
        "tool_capability_kind": tool_capability_kind,
        "tool_runtime_binding": tool_runtime_binding,
        "supported_profiles": list(supported_profiles or ["all"]),
        "default_visibility": default_visibility,
        "canonical_family_record": {
            "canonical_family": family_name,
            "family_source": canonical_family_source,
            "family_owner": canonical_family_owner,
            "canonical_tool_names": [tool_name],
            "compatibility_aliases": [],
            "tool_capability_kind": tool_capability_kind,
            "tool_runtime_binding": tool_runtime_binding,
        },
    }


class _FakePluginManager:
    def __init__(
        self,
        provider_specs: List[Dict[str, Any]],
        *,
        declarations: List[Dict[str, Any]],
    ) -> None:
        self._provider_specs = list(provider_specs)
        self._declarations = list(declarations)

    def provider_tool_specs(self) -> List[Dict[str, Any]]:
        return list(self._provider_specs)

    def provider_tool_capability_declarations(self) -> List[Dict[str, Any]]:
        return list(self._declarations)


def test_merged_provider_tool_specs_exposes_task_a_aligned_local_runtime_tool() -> None:
    specs = merged_provider_tool_specs(
        ProviderConfig(model="gpt-5.4", api_key="test"),
        current_host_platform(),
        plugin_manager_factory=lambda: _FakePluginManager(
            [_function_spec("demo_lookup")],
            declarations=[_task_a_declaration(tool_name="demo_lookup")],
        ),
    )

    names = [item["function"]["name"] for item in specs if item.get("type") == "function"]
    assert "demo_lookup" in names


def test_merged_provider_tool_specs_hide_plugin_tool_without_task_a_alignment() -> None:
    specs = merged_provider_tool_specs(
        ProviderConfig(model="gpt-5.4", api_key="test"),
        current_host_platform(),
        plugin_manager_factory=lambda: _FakePluginManager(
            [_function_spec("demo_lookup")],
            declarations=[
                {
                    "tool_name": "demo_lookup",
                    "supported_profiles": ["all"],
                    "default_visibility": "model_visible",
                }
            ],
        ),
    )

    names = [item["function"]["name"] for item in specs if item.get("type") == "function"]
    assert "demo_lookup" not in names


def test_provider_tool_names_hide_provider_native_plugin_tool_without_native_projection_path() -> None:
    names = provider_tool_names(
        ProviderConfig(
            model="gpt-5.4",
            api_key="test",
            interaction_profile="codex_openai",
        ),
        current_host_platform(),
        plugin_manager_factory=lambda: _FakePluginManager(
            [_function_spec("sample_lookup")],
            declarations=[
                _task_a_declaration(
                    tool_name="sample_lookup",
                    canonical_family="web_search",
                    canonical_family_source="builtin",
                    canonical_family_owner="builtin",
                    tool_capability_kind="provider_native_tool",
                    tool_runtime_binding="provider_native",
                    supported_profiles=["codex_openai"],
                )
            ],
        ),
    )

    assert "sample_lookup" not in names

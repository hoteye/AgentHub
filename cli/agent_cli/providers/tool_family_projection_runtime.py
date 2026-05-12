from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.providers import tool_capability_registry as capability_registry_helpers
from cli.agent_cli.providers.tool_capability_registry import CapabilityRegistryProjection

PluginManagerFactory = Callable[[], Optional[PluginManager]]


def build_projection(base_capability_metadata: List[Dict[str, Any]]) -> CapabilityRegistryProjection:
    return capability_registry_helpers.build_capability_registry(base_capability_metadata)


def canonical_registry_entry(
    projection: CapabilityRegistryProjection,
    name: str,
) -> Optional[Dict[str, Any]]:
    return capability_registry_helpers.canonical_registry_entry(projection, name)


def clone_canonical_registry_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    return capability_registry_helpers.clone_canonical_registry_entry(entry)


def canonical_tool_registry(projection: CapabilityRegistryProjection) -> List[Dict[str, Any]]:
    return capability_registry_helpers.canonical_tool_registry(projection)


def canonical_tool_metadata(
    projection: CapabilityRegistryProjection,
    name: str,
) -> Optional[Dict[str, Any]]:
    return capability_registry_helpers.canonical_tool_metadata(projection, name)


def base_capability_specs(projection: CapabilityRegistryProjection) -> List[Dict[str, Any]]:
    return capability_registry_helpers.base_capability_specs(projection)


def builtin_tool_metadata(
    projection: CapabilityRegistryProjection,
    name: str,
) -> Optional[Dict[str, Any]]:
    return capability_registry_helpers.builtin_tool_metadata(projection, name)


def command_usage_text(
    projection: CapabilityRegistryProjection,
    name: str,
) -> str:
    return capability_registry_helpers.command_usage_text(projection, name)


def command_action_names(
    projection: CapabilityRegistryProjection,
    name: str,
):
    return capability_registry_helpers.command_action_names(projection, name)


def provider_action_names(
    projection: CapabilityRegistryProjection,
    name: str,
):
    return capability_registry_helpers.provider_action_names(projection, name)


def merged_capability_specs(
    projection: CapabilityRegistryProjection,
    *,
    plugin_manager_factory: PluginManagerFactory | None = None,
) -> List[Dict[str, Any]]:
    return capability_registry_helpers.merged_capability_specs(
        projection,
        plugin_manager_factory=plugin_manager_factory,
    )


def provider_description(
    projection: CapabilityRegistryProjection,
    name: str,
) -> str:
    return capability_registry_helpers.provider_description(projection, name)

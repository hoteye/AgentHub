from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.providers import command_tool_metadata as metadata_helpers

PluginManagerFactory = Callable[[], Optional[PluginManager]]


@dataclass(frozen=True)
class CapabilityRegistryProjection:
    canonical_tool_registry: Tuple[Dict[str, Any], ...]
    canonical_tool_registry_by_name: Dict[str, Dict[str, Any]]


def normalize_base_capability_spec(spec: Any) -> Optional[Dict[str, Any]]:
    return metadata_helpers.normalize_base_capability_spec(spec)


def normalized_actions(value: Any) -> Tuple[str, ...]:
    return metadata_helpers.normalized_actions(value)


def build_canonical_registry_entry(metadata: Dict[str, Any]) -> Dict[str, Any]:
    return metadata_helpers.build_canonical_registry_entry(metadata)


def build_capability_registry(
    base_capability_metadata: Sequence[Dict[str, Any]],
) -> CapabilityRegistryProjection:
    canonical_tool_registry = tuple(
        build_canonical_registry_entry(item) for item in base_capability_metadata
    )
    canonical_tool_registry_by_name = {
        str(item.get("name") or "").strip(): item for item in canonical_tool_registry
    }
    return CapabilityRegistryProjection(
        canonical_tool_registry=canonical_tool_registry,
        canonical_tool_registry_by_name=canonical_tool_registry_by_name,
    )


def canonical_registry_entry(
    projection: CapabilityRegistryProjection,
    name: str,
) -> Optional[Dict[str, Any]]:
    return metadata_helpers.canonical_registry_entry(
        projection.canonical_tool_registry_by_name,
        name,
    )


def clone_canonical_registry_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    return metadata_helpers.clone_canonical_registry_entry(entry)


def canonical_tool_registry(projection: CapabilityRegistryProjection) -> List[Dict[str, Any]]:
    return metadata_helpers.canonical_tool_registry(projection.canonical_tool_registry)


def canonical_tool_metadata(
    projection: CapabilityRegistryProjection,
    name: str,
) -> Optional[Dict[str, Any]]:
    return metadata_helpers.canonical_tool_metadata(
        projection.canonical_tool_registry_by_name,
        name,
    )


def base_capability_specs(projection: CapabilityRegistryProjection) -> List[Dict[str, Any]]:
    return metadata_helpers.base_capability_specs(projection.canonical_tool_registry)


def builtin_tool_metadata(
    projection: CapabilityRegistryProjection,
    name: str,
) -> Optional[Dict[str, Any]]:
    return metadata_helpers.builtin_tool_metadata(
        projection.canonical_tool_registry_by_name,
        name,
    )


def command_usage_text(
    projection: CapabilityRegistryProjection,
    name: str,
) -> str:
    return metadata_helpers.command_usage_text(
        projection.canonical_tool_registry_by_name,
        name,
    )


def command_action_names(
    projection: CapabilityRegistryProjection,
    name: str,
) -> Tuple[str, ...]:
    return metadata_helpers.command_action_names(
        projection.canonical_tool_registry_by_name,
        name,
    )


def provider_action_names(
    projection: CapabilityRegistryProjection,
    name: str,
) -> Tuple[str, ...]:
    return metadata_helpers.provider_action_names(
        projection.canonical_tool_registry_by_name,
        name,
    )


def normalize_capability_spec(spec: Any) -> Optional[Dict[str, Any]]:
    normalized = normalize_base_capability_spec(spec)
    if normalized is None:
        return None
    plugin_name = str(spec.get("plugin_name") or "").strip()
    if plugin_name:
        normalized["plugin_name"] = plugin_name
    return normalized


def merged_capability_specs(
    projection: CapabilityRegistryProjection,
    *,
    plugin_manager_factory: PluginManagerFactory | None = None,
) -> List[Dict[str, Any]]:
    specs = base_capability_specs(projection)
    manager = plugin_manager_factory() if plugin_manager_factory is not None else PluginManager()
    for item in ([] if manager is None else manager.tool_specs()):
        normalized = normalize_capability_spec(item)
        if normalized is None:
            continue
        name = str(normalized.get("name") or "").strip()
        specs = [existing for existing in specs if str(existing.get("name") or "").strip() != name]
        specs.append(normalized)
    return specs


def provider_description(
    projection: CapabilityRegistryProjection,
    name: str,
) -> str:
    return metadata_helpers.provider_description(
        projection.canonical_tool_registry_by_name,
        name,
    )

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.providers import tool_family_metadata_runtime as metadata_runtime
from cli.agent_cli.providers import tool_family_mapping_runtime as mapping_runtime
from cli.agent_cli.providers import tool_family_normalization_runtime as normalization_runtime
from cli.agent_cli.providers import tool_family_projection_runtime as projection_runtime

PluginManagerFactory = Callable[[], Optional[PluginManager]]

BUILTIN_TOOL_ORDER: Tuple[str, ...] = mapping_runtime.BUILTIN_TOOL_ORDER

RESPONSES_MINIMAL_TOOL_ORDER: Tuple[str, ...] = mapping_runtime.RESPONSES_MINIMAL_TOOL_ORDER

BROWSER_RUNTIME_ACTIONS: Tuple[str, ...] = mapping_runtime.BROWSER_RUNTIME_ACTIONS

BROWSER_PROVIDER_ACTIONS: Tuple[str, ...] = mapping_runtime.BROWSER_PROVIDER_ACTIONS

BASE_CAPABILITY_METADATA: Tuple[Dict[str, Any], ...] = metadata_runtime.build_base_capability_metadata(
    browser_runtime_actions=BROWSER_RUNTIME_ACTIONS,
    browser_provider_actions=BROWSER_PROVIDER_ACTIONS,
)


def normalize_base_capability_spec(spec: Any) -> Optional[Dict[str, Any]]:
    return normalization_runtime.normalize_base_capability_spec(spec)


def normalized_actions(value: Any) -> Tuple[str, ...]:
    return normalization_runtime.normalized_actions(value)


def build_canonical_registry_entry(metadata: Dict[str, Any]) -> Dict[str, Any]:
    return normalization_runtime.build_canonical_registry_entry(metadata)


_CAPABILITY_REGISTRY = projection_runtime.build_projection(
    BASE_CAPABILITY_METADATA,
)


def canonical_registry_entry(name: str) -> Optional[Dict[str, Any]]:
    return projection_runtime.canonical_registry_entry(_CAPABILITY_REGISTRY, name)


def clone_canonical_registry_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    return projection_runtime.clone_canonical_registry_entry(entry)


def canonical_tool_registry() -> List[Dict[str, Any]]:
    return projection_runtime.canonical_tool_registry(_CAPABILITY_REGISTRY)


def canonical_tool_metadata(name: str) -> Optional[Dict[str, Any]]:
    return projection_runtime.canonical_tool_metadata(_CAPABILITY_REGISTRY, name)


def base_capability_specs() -> List[Dict[str, Any]]:
    return projection_runtime.base_capability_specs(_CAPABILITY_REGISTRY)


def builtin_tool_metadata(name: str) -> Optional[Dict[str, Any]]:
    return projection_runtime.builtin_tool_metadata(_CAPABILITY_REGISTRY, name)


def command_usage_text(name: str) -> str:
    return projection_runtime.command_usage_text(_CAPABILITY_REGISTRY, name)


def command_action_names(name: str) -> Tuple[str, ...]:
    return projection_runtime.command_action_names(_CAPABILITY_REGISTRY, name)


def provider_action_names(name: str) -> Tuple[str, ...]:
    return projection_runtime.provider_action_names(_CAPABILITY_REGISTRY, name)


def merged_capability_specs(
    *,
    plugin_manager_factory: PluginManagerFactory | None = None,
) -> List[Dict[str, Any]]:
    return projection_runtime.merged_capability_specs(
        _CAPABILITY_REGISTRY,
        plugin_manager_factory=plugin_manager_factory,
    )


def normalize_capability_spec(spec: Any) -> Optional[Dict[str, Any]]:
    return normalization_runtime.normalize_capability_spec(spec)


def provider_description(name: str) -> str:
    return projection_runtime.provider_description(_CAPABILITY_REGISTRY, name)

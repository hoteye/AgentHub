from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from cli.agent_cli.providers import tool_spec_registry as registry_helpers
from cli.agent_cli.slash_surface import surface_usage_text


def normalize_base_capability_spec(spec: Any) -> Optional[Dict[str, Any]]:
    return registry_helpers.normalize_base_capability_spec(spec)


def normalized_actions(value: Any) -> Tuple[str, ...]:
    return registry_helpers.normalized_actions(value)


def build_canonical_registry_entry(metadata: Dict[str, Any]) -> Dict[str, Any]:
    return registry_helpers.build_canonical_registry_entry(metadata)


def canonical_registry_entry(
    registry_by_name: Dict[str, Dict[str, Any]],
    name: str,
) -> Optional[Dict[str, Any]]:
    return registry_helpers.canonical_registry_entry(registry_by_name, name)


def clone_canonical_registry_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    return registry_helpers.clone_canonical_registry_entry(entry)


def canonical_tool_registry(registry: Tuple[Dict[str, Any], ...]) -> List[Dict[str, Any]]:
    return registry_helpers.canonical_tool_registry(registry)


def canonical_tool_metadata(
    registry_by_name: Dict[str, Dict[str, Any]],
    name: str,
) -> Optional[Dict[str, Any]]:
    return registry_helpers.canonical_tool_metadata(registry_by_name, name)


def base_capability_specs(registry: Tuple[Dict[str, Any], ...]) -> List[Dict[str, Any]]:
    specs: List[Dict[str, Any]] = []
    for entry in registry:
        capability = entry.get("capability")
        if isinstance(capability, dict) and capability:
            specs.append(dict(capability))
    return specs


def builtin_tool_metadata(
    registry_by_name: Dict[str, Dict[str, Any]],
    name: str,
) -> Optional[Dict[str, Any]]:
    return canonical_tool_metadata(registry_by_name, name)


def command_usage_text(
    registry_by_name: Dict[str, Dict[str, Any]],
    name: str,
) -> str:
    item = builtin_tool_metadata(registry_by_name, name)
    usage = str((item or {}).get("usage_text") or "").strip()
    if usage.startswith("Usage: "):
        return f"Usage: {surface_usage_text(name, usage[len('Usage: '):].strip())}"
    surfaced = surface_usage_text(name, usage)
    if surfaced:
        return f"Usage: {surfaced}"
    return usage


def command_action_names(
    registry_by_name: Dict[str, Dict[str, Any]],
    name: str,
) -> Tuple[str, ...]:
    entry = canonical_registry_entry(registry_by_name, name)
    return tuple(entry.get("command_actions") or ()) if isinstance(entry, dict) else tuple()


def provider_action_names(
    registry_by_name: Dict[str, Dict[str, Any]],
    name: str,
) -> Tuple[str, ...]:
    entry = canonical_registry_entry(registry_by_name, name)
    return tuple(entry.get("provider_actions") or ()) if isinstance(entry, dict) else tuple()


def provider_description(
    registry_by_name: Dict[str, Dict[str, Any]],
    name: str,
) -> str:
    entry = canonical_registry_entry(registry_by_name, name)
    return str((entry or {}).get("provider_description") or "").strip()

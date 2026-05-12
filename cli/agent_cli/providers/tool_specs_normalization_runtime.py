from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from cli.agent_cli.providers import tool_family_registry


def normalize_base_capability_spec(spec: Any) -> Optional[Dict[str, Any]]:
    return tool_family_registry.normalize_base_capability_spec(spec)


def normalized_actions(value: Any) -> Tuple[str, ...]:
    return tool_family_registry.normalized_actions(value)


def build_canonical_registry_entry(metadata: Dict[str, Any]) -> Dict[str, Any]:
    return tool_family_registry.build_canonical_registry_entry(metadata)


def canonical_registry_entry(name: str) -> Optional[Dict[str, Any]]:
    return tool_family_registry.canonical_registry_entry(name)


def clone_canonical_registry_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    return tool_family_registry.clone_canonical_registry_entry(entry)


def normalize_capability_spec(spec: Any) -> Optional[Dict[str, Any]]:
    return tool_family_registry.normalize_capability_spec(spec)


def provider_description(name: str) -> str:
    return tool_family_registry.provider_description(name)

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from cli.agent_cli.providers import tool_capability_registry as capability_registry_helpers


def normalize_base_capability_spec(spec: Any) -> Optional[Dict[str, Any]]:
    return capability_registry_helpers.normalize_base_capability_spec(spec)


def normalized_actions(value: Any) -> Tuple[str, ...]:
    return capability_registry_helpers.normalized_actions(value)


def build_canonical_registry_entry(metadata: Dict[str, Any]) -> Dict[str, Any]:
    return capability_registry_helpers.build_canonical_registry_entry(metadata)


def normalize_capability_spec(spec: Any) -> Optional[Dict[str, Any]]:
    return capability_registry_helpers.normalize_capability_spec(spec)

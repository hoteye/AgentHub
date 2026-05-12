from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def normalize_base_capability_spec(spec: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(spec, dict):
        return None
    name = str(spec.get("name") or "").strip()
    if not name:
        return None
    label = str(spec.get("label") or name).strip() or name
    description = str(spec.get("description") or "").strip()
    return {
        "name": name,
        "label": label,
        "description": description,
        "mutates_ui": bool(spec.get("mutates_ui")),
        "requires_confirmation": bool(spec.get("requires_confirmation")),
    }


def normalized_actions(value: Any) -> Tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return tuple()
    return tuple(str(action).strip() for action in value if str(action).strip())


def build_canonical_registry_entry(metadata: Dict[str, Any]) -> Dict[str, Any]:
    normalized_metadata = dict(metadata)
    name = str(normalized_metadata.get("name") or "").strip()
    capability = normalize_base_capability_spec(normalized_metadata)
    return {
        "name": name,
        "metadata": normalized_metadata,
        "capability": dict(capability or {}),
        "provider_description": str(
            normalized_metadata.get("provider_description") or normalized_metadata.get("description") or ""
        ).strip(),
        "command_actions": normalized_actions(normalized_metadata.get("slash_actions")),
        "provider_actions": normalized_actions(normalized_metadata.get("provider_actions")),
    }


def canonical_registry_entry(registry_by_name: Dict[str, Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    normalized = str(name or "").strip()
    if not normalized:
        return None
    return registry_by_name.get(normalized)


def clone_canonical_registry_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": str(entry.get("name") or "").strip(),
        "metadata": dict(entry.get("metadata") or {}),
        "capability": dict(entry.get("capability") or {}),
        "provider_description": str(entry.get("provider_description") or "").strip(),
        "command_actions": tuple(entry.get("command_actions") or ()),
        "provider_actions": tuple(entry.get("provider_actions") or ()),
    }


def canonical_tool_registry(registry: Tuple[Dict[str, Any], ...]) -> List[Dict[str, Any]]:
    return [clone_canonical_registry_entry(item) for item in registry]


def canonical_tool_metadata(registry_by_name: Dict[str, Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    entry = canonical_registry_entry(registry_by_name, name)
    metadata = (entry or {}).get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else None

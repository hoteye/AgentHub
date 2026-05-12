from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from typing import Any, Dict, List, Optional

import tomllib

from cli.agent_cli.host import plugin_capability_declaration as plugin_capability_declaration_runtime
from cli.agent_cli.host.plugin_manifest import PluginManifest

_DEFAULT_CAPABILITIES_FILENAMES = ("capabilities.toml", "capabilities.json")
_REFERENCE_CAPABILITIES_PATHS = tuple(Path(".agent_cli_legacy-plugin") / name for name in _DEFAULT_CAPABILITIES_FILENAMES)
_REFERENCE_MANIFEST_PATH = Path(".agent_cli_legacy-plugin") / "plugin.json"


def _value_with_aliases(payload: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return None


def safe_resolve(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser()


def read_json_dict(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_capability_payload(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        if path.suffix.lower() == ".toml":
            return tomllib.loads(path.read_text(encoding="utf-8"))
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, tomllib.TOMLDecodeError):
        return None


def _capability_items_from_payload(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        raw_items = payload.get("capabilities")
        if isinstance(raw_items, list):
            return [dict(item) for item in raw_items if isinstance(item, dict)]
    return []


def _normalize_capability_item(
    item: Dict[str, Any],
    *,
    plugin_name: str,
    infer_canonical_family: bool,
) -> Dict[str, Any] | None:
    capability_id = str(_value_with_aliases(item, "capability_id", "capabilityId") or "").strip()
    tool_name = str(_value_with_aliases(item, "tool_name", "toolName") or "").strip()
    canonical_family = str(_value_with_aliases(item, "canonical_family", "canonicalFamily") or "").strip()
    kind = str(item.get("kind") or "").strip()
    if not (capability_id or tool_name):
        return None
    normalized = dict(item)
    if capability_id:
        normalized["capability_id"] = capability_id
    elif tool_name:
        normalized["capability_id"] = tool_name
    if tool_name:
        normalized["tool_name"] = tool_name
    if canonical_family:
        normalized["canonical_family"] = canonical_family
    elif infer_canonical_family and tool_name:
        normalized["canonical_family"] = tool_name
    elif infer_canonical_family and capability_id:
        normalized["canonical_family"] = capability_id
    if kind:
        normalized["kind"] = kind
    media_capability = _value_with_aliases(item, "media_capability")
    if not isinstance(media_capability, dict):
        media_capability = _value_with_aliases(item, "mediaCapability")
    if not isinstance(media_capability, dict):
        media_kind = _value_with_aliases(item, "media_kind", "mediaKind")
        if media_kind:
            media_capability = {
                "media_kind": media_kind,
                "ingest_semantics": _value_with_aliases(item, "ingest_semantics", "ingestSemantics"),
                "source_modes": _value_with_aliases(item, "source_modes", "sourceModes"),
                "projection_modes": _value_with_aliases(
                    item,
                    "projection_modes",
                    "projectionModes",
                    "media_projection_modes",
                    "mediaProjectionModes",
                ),
                "mime_types": _value_with_aliases(
                    item,
                    "mime_types",
                    "mimeTypes",
                    "supported_mime_types",
                    "supportedMimeTypes",
                ),
                "max_size_bytes": _value_with_aliases(item, "max_size_bytes", "maxSizeBytes"),
            }
    if isinstance(media_capability, dict):
        normalized["media_capability"] = dict(media_capability)
    normalized.setdefault("plugin_name", plugin_name)
    return normalized


def read_plugin_capability_declarations(root: Path, *, plugin_name: str | None = None) -> List[Dict[str, Any]]:
    resolved_plugin_name = str(plugin_name or "").strip() or (str(root.name or "").strip() or "unknown_plugin")
    candidates: List[tuple[List[Dict[str, Any]], bool, bool]] = []

    for filename in _DEFAULT_CAPABILITIES_FILENAMES:
        top_level_payload = _read_capability_payload(root / filename)
        if top_level_payload is not None:
            candidates.append((_capability_items_from_payload(top_level_payload), False, False))

    for path in _REFERENCE_CAPABILITIES_PATHS:
        reference_caps_payload = _read_capability_payload(root / path)
        if reference_caps_payload is not None:
            candidates.append((_capability_items_from_payload(reference_caps_payload), True, True))

    reference_manifest_payload = read_json_dict(root / _REFERENCE_MANIFEST_PATH)
    if reference_manifest_payload is not None:
        candidates.append((_capability_items_from_payload(reference_manifest_payload), True, True))

    declarations: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for capability_items, infer_canonical_family, allow_compat_aliases in candidates:
        raw_items: List[Dict[str, Any]] = []
        for item in capability_items:
            normalized = _normalize_capability_item(
                item,
                plugin_name=resolved_plugin_name,
                infer_canonical_family=infer_canonical_family,
            )
            if normalized is not None:
                raw_items.append(normalized)
        normalized_result = plugin_capability_declaration_runtime.normalize_plugin_capability_declarations(
            raw_items,
            allow_compat_aliases=allow_compat_aliases,
        )
        for normalized in normalized_result.as_dicts():
            dedupe_key = "|".join(
                (
                    str(normalized.get("plugin_name") or "").strip(),
                    str(normalized.get("capability_id") or "").strip(),
                    str(normalized.get("tool_name") or "").strip(),
                    str(normalized.get("kind") or "").strip(),
                )
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            declarations.append(normalized)
    return declarations


def normalize_manifest(item: Any, *, plugin_name: str) -> PluginManifest:
    name = str(getattr(item, "name", "") or "").strip() or plugin_name
    if name != plugin_name:
        raise ValueError(f"manifest name '{name}' does not match plugin directory '{plugin_name}'")
    return PluginManifest(
        name=name,
        version=str(getattr(item, "version", "") or "").strip() or "0.0.0",
        description=str(getattr(item, "description", "") or "").strip(),
        api_version=str(getattr(item, "api_version", "") or "1").strip() or "1",
        plugin_kind=str(getattr(item, "plugin_kind", "") or "generic").strip() or "generic",
        distribution=str(getattr(item, "distribution", "") or "bundled").strip() or "bundled",
        min_host_version=str(getattr(item, "min_host_version", "") or "0.1.0").strip() or "0.1.0",
        enabled_by_default=bool(getattr(item, "enabled_by_default", False)),
        commercial=bool(getattr(item, "commercial", False)),
        dependencies=[
            str(dep).strip()
            for dep in (getattr(item, "dependencies", None) or [])
            if str(dep).strip()
        ],
        capability_declarations=[
            dict(capability)
            for capability in (getattr(item, "capability_declarations", None) or [])
            if isinstance(capability, dict)
        ],
    )


def reference_manifest_as_plugin_manifest(payload: Dict[str, Any], *, root: Path) -> PluginManifest:
    name = str(payload.get("name") or "").strip() or root.name
    return PluginManifest(
        name=name,
        version=str(payload.get("version") or "0.0.0").strip() or "0.0.0",
        description=str(payload.get("description") or "").strip(),
        api_version=str(payload.get("api_version") or payload.get("apiVersion") or "1").strip() or "1",
        plugin_kind=str(payload.get("plugin_kind") or payload.get("pluginKind") or "generic").strip() or "generic",
        distribution=str(payload.get("distribution") or "installed").strip() or "installed",
        min_host_version=str(payload.get("min_host_version") or payload.get("minHostVersion") or "0.1.0").strip() or "0.1.0",
        enabled_by_default=bool(payload.get("enabled_by_default") or payload.get("enabledByDefault")),
        commercial=bool(payload.get("commercial")),
        dependencies=[
            str(item).strip()
            for item in (payload.get("dependencies") or [])
            if str(item).strip()
        ],
        capability_declarations=[
            dict(capability)
            for capability in _capability_items_from_payload(payload)
            if isinstance(capability, dict)
        ],
    )


def read_legacy_compat_manifest_metadata(root: Path, *, manifest_name: str = "manifest.py") -> Optional[PluginManifest]:
    manifest_path = root / manifest_name
    if not manifest_path.exists():
        return None
    plugin_name = root.name
    root_key = "_host_plugins_manifest"
    if root_key not in sys.modules:
        module = types.ModuleType(root_key)
        module.__path__ = []  # type: ignore[attr-defined]
        sys.modules[root_key] = module
    spec = importlib.util.spec_from_file_location(f"{root_key}.{plugin_name}", str(manifest_path))
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"{root_key}.{plugin_name}"] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        return None
    if not hasattr(module, "manifest"):
        return None
    try:
        return normalize_manifest(module.manifest(), plugin_name=plugin_name)
    except Exception:
        return None


def normalize_plugin_mcp_value(plugin_root: Path, value: Any) -> Dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    normalized = dict(value)
    cwd = normalized.get("cwd")
    if isinstance(cwd, str) and cwd and not Path(cwd).is_absolute():
        normalized["cwd"] = str((plugin_root / cwd).resolve())
    return normalized


def load_mcp_servers(plugin_root: Path, payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    raw_servers = payload.get("mcpServers") or payload.get("mcp_servers") or {}
    if not isinstance(raw_servers, dict):
        return {}
    servers: Dict[str, Dict[str, Any]] = {}
    for name, value in raw_servers.items():
        key = str(name or "").strip()
        if not key:
            continue
        servers[key] = normalize_plugin_mcp_value(plugin_root, value)
    return servers


def load_apps(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_apps = payload.get("apps") or {}
    if not isinstance(raw_apps, dict):
        return []
    apps: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for key, value in raw_apps.items():
        entry = dict(value) if isinstance(value, dict) else {}
        connector_id = str(entry.get("id") or key).strip()
        if not connector_id or connector_id in seen:
            continue
        seen.add(connector_id)
        connector_kind = (
            str(entry.get("connector_kind") or entry.get("kind") or "app")
            .strip()
            .lower()
            or "app"
        )
        display_name = str(entry.get("display_name") or entry.get("name") or connector_id).strip() or connector_id
        metadata = dict(entry.get("metadata") or {})
        apps.append(
            {
                "connector_id": connector_id,
                "connector_key": connector_id,
                "display_name": display_name,
                "description": str(entry.get("description") or "").strip(),
                "connector_kind": connector_kind,
                "supports_webhook": bool(entry.get("supports_webhook")),
                "supports_polling": bool(entry.get("supports_polling")),
                "supports_actions": entry.get("supports_actions", True),
                "health": str(entry.get("health") or "ready"),
                "event_types": list(entry.get("event_types") or []),
                "action_types": list(entry.get("action_types") or []),
                "metadata": metadata,
                "source_kind": entry.get("source_kind") or "plugin_app",
            }
        )
    return apps

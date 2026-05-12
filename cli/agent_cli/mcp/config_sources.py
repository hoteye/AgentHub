from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

SOURCE_USER = "user"
SOURCE_WORKSPACE = "workspace"
SOURCE_PLUGIN = "plugin"
SOURCE_RUNTIME_DYNAMIC = "runtime_dynamic"

SOURCE_PRECEDENCE: dict[str, int] = {
    SOURCE_RUNTIME_DYNAMIC: 0,
    SOURCE_USER: 1,
    SOURCE_WORKSPACE: 2,
    SOURCE_PLUGIN: 3,
}


@dataclass(frozen=True)
class McpConfigSourceItem:
    name: str
    source: str
    precedence: int
    config: dict[str, Any]
    enabled: bool
    metadata: dict[str, Any]


_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _normalized_source(source: str) -> str:
    key = str(source or "").strip().lower()
    if key not in SOURCE_PRECEDENCE:
        return SOURCE_PLUGIN
    return key


def _normalized_name(raw: Any) -> str:
    return str(raw or "").strip()


def _expand_env_placeholders(value: Any) -> Any:
    if isinstance(value, str):
        def _replace(match: re.Match[str]) -> str:
            key = str(match.group(1) or "")
            if key in os.environ:
                return os.environ[key]
            return match.group(0)

        return _ENV_PATTERN.sub(_replace, value)
    if isinstance(value, list):
        return [_expand_env_placeholders(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_expand_env_placeholders(item) for item in value)
    if isinstance(value, dict):
        return {str(key): _expand_env_placeholders(item) for key, item in value.items()}
    return value


def _normalized_config(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return _expand_env_placeholders({str(key): value for key, value in raw.items()})


def _is_enveloped_source_config(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    envelope_keys = {"config", "enabled", "metadata", "registry_ref", "registry", "registry_catalog", "official_registry"}
    return any(key in raw for key in envelope_keys)


def _resolve_registry_config(raw: dict[str, Any], *, metadata: dict[str, Any]) -> dict[str, Any]:
    registry_ref = str(raw.get("registry_ref") or raw.get("registry") or "").strip()
    if not registry_ref:
        return {}
    metadata["registry_ref"] = registry_ref
    catalog_raw = raw.get("registry_catalog")
    if not isinstance(catalog_raw, dict):
        catalog_raw = raw.get("official_registry")
    if not isinstance(catalog_raw, dict):
        metadata["registry_error"] = "catalog_missing"
        return {}
    resolved = catalog_raw.get(registry_ref)
    if not isinstance(resolved, dict):
        metadata["registry_error"] = "ref_not_found"
        return {}
    metadata["registry_origin"] = "inline_catalog"
    return _normalized_config(resolved)


def _item_from_payload(
    source: str,
    *,
    name: str,
    config: Any,
    enabled: bool = True,
    metadata: dict[str, Any] | None = None,
) -> McpConfigSourceItem | None:
    normalized_name = _normalized_name(name)
    if not normalized_name:
        return None
    normalized_source = _normalized_source(source)
    return McpConfigSourceItem(
        name=normalized_name,
        source=normalized_source,
        precedence=SOURCE_PRECEDENCE[normalized_source],
        config=_normalized_config(config),
        enabled=bool(enabled),
        metadata=dict(metadata or {}),
    )


def normalize_source_items(source: str, payload: Any) -> list[McpConfigSourceItem]:
    if payload is None:
        return []
    items: list[McpConfigSourceItem] = []
    if isinstance(payload, dict):
        for name, raw_value in payload.items():
            config = raw_value
            enabled = True
            metadata: dict[str, Any] | None = None
            if _is_enveloped_source_config(raw_value):
                enabled = bool(raw_value.get("enabled", True))
                metadata = dict(raw_value.get("metadata") or {}) if isinstance(raw_value.get("metadata"), dict) else {}
                resolved = _resolve_registry_config(raw_value, metadata=metadata)
                explicit_config = _normalized_config(raw_value.get("config", {}))
                config = {**resolved, **explicit_config}
                for key in ("mcpb", "headers_helper", "workspace_trust"):
                    if key in raw_value and key not in config:
                        config[key] = _expand_env_placeholders(raw_value.get(key))
            item = _item_from_payload(
                source,
                name=str(name),
                config=config,
                enabled=enabled,
                metadata=metadata,
            )
            if item is not None:
                items.append(item)
    elif isinstance(payload, list):
        for raw in payload:
            if not isinstance(raw, dict):
                continue
            metadata = dict(raw.get("metadata") or {}) if isinstance(raw.get("metadata"), dict) else {}
            config: Any = raw.get("config", {})
            if _is_enveloped_source_config(raw):
                resolved = _resolve_registry_config(raw, metadata=metadata)
                explicit_config = _normalized_config(raw.get("config", {}))
                config = {**resolved, **explicit_config}
                for key in ("mcpb", "headers_helper", "workspace_trust"):
                    if key in raw and key not in config:
                        config[key] = _expand_env_placeholders(raw.get(key))
            item = _item_from_payload(
                source,
                name=str(raw.get("name") or ""),
                config=config,
                enabled=bool(raw.get("enabled", True)),
                metadata=metadata,
            )
            if item is not None:
                items.append(item)
    items.sort(key=lambda item: (item.precedence, item.name))
    return items


def collect_mcp_config_sources(
    *,
    user: Any = None,
    workspace: Any = None,
    plugin: Any = None,
    runtime_dynamic: Any = None,
) -> list[McpConfigSourceItem]:
    items: list[McpConfigSourceItem] = []
    items.extend(normalize_source_items(SOURCE_RUNTIME_DYNAMIC, runtime_dynamic))
    items.extend(normalize_source_items(SOURCE_USER, user))
    items.extend(normalize_source_items(SOURCE_WORKSPACE, workspace))
    items.extend(normalize_source_items(SOURCE_PLUGIN, plugin))
    items.sort(key=lambda item: (item.precedence, item.name))
    return items


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def canonical_config_fingerprint(config: dict[str, Any]) -> str:
    safe = _json_safe(config)
    return json.dumps(safe, sort_keys=True, ensure_ascii=True, separators=(",", ":"))

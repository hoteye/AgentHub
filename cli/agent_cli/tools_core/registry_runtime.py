from __future__ import annotations

from typing import Any


def contract_item_dict(item: Any) -> dict[str, Any]:
    if item is None:
        return {}
    to_dict = getattr(item, "to_dict", None)
    if callable(to_dict):
        value = to_dict()
        return dict(value or {}) if isinstance(value, dict) else {}
    if isinstance(item, dict):
        return dict(item)
    return {}


def contract_item_text(item: Any, *names: str) -> str:
    raw = contract_item_dict(item)
    for name in names:
        value = raw.get(name)
        if value is None:
            value = getattr(item, name, None)
        if value is None:
            continue
        return str(value).strip()
    return ""


def contract_item_bool(item: Any, *names: str, default: bool = False) -> bool:
    raw = contract_item_dict(item)
    for name in names:
        if name in raw:
            return bool(raw.get(name))
        value = getattr(item, name, None)
        if value is not None:
            return bool(value)
    return bool(default)


def contract_item_list(item: Any, *names: str) -> list[str]:
    raw = contract_item_dict(item)
    for name in names:
        value = raw.get(name)
        if value is None:
            value = getattr(item, name, None)
        if not isinstance(value, list):
            continue
        return [str(entry).strip() for entry in value if str(entry).strip()]
    return []


def contract_item_mapping(item: Any, *names: str) -> dict[str, Any]:
    raw = contract_item_dict(item)
    for name in names:
        value = raw.get(name)
        if value is None:
            value = getattr(item, name, None)
        if isinstance(value, dict):
            return dict(value)
    return {}


def build_capabilities_payload(
    *,
    plugin_manager_factory,
    merged_capability_specs_fn,
) -> dict[str, Any]:
    plugin_manager = plugin_manager_factory() if plugin_manager_factory is not None else None
    tools = merged_capability_specs_fn(
        plugin_manager_factory=(lambda: plugin_manager) if plugin_manager_factory is not None else None
    )
    workspace_trust = "trusted"
    mcp_servers: dict[str, dict[str, Any]] = {}
    mcp_server_entries: list[dict[str, Any]] = []
    app_connectors: list[dict[str, str]] = []
    if plugin_manager is not None:
        trust_getter = getattr(plugin_manager, "workspace_trust_level", None)
        if callable(trust_getter):
            workspace_trust = str(trust_getter() or "trusted")
        mcp_runtime_map_getter = getattr(plugin_manager, "mcp_server_runtime_map", None)
        if callable(mcp_runtime_map_getter):
            mcp_servers = dict(mcp_runtime_map_getter() or {})
        if not mcp_servers:
            mcp_getter = getattr(plugin_manager, "configured_mcp_servers", None)
            if callable(mcp_getter):
                mcp_servers = dict(mcp_getter() or {})
        mcp_entries_getter = getattr(plugin_manager, "mcp_server_entries", None)
        if callable(mcp_entries_getter):
            mcp_server_entries = [dict(item) for item in list(mcp_entries_getter() or []) if isinstance(item, dict)]
        app_getter = getattr(plugin_manager, "effective_app_connectors", None)
        if callable(app_getter):
            app_connectors = list(app_getter() or [])
    return {
        "ok": True,
        "tools": tools,
        "count": len(tools),
        "registry_error": None,
        "workspace_trust": workspace_trust,
        "mcp_servers": mcp_servers,
        "mcp_server_entries": mcp_server_entries,
        "app_connectors": app_connectors,
    }


def plugin_contract_metadata(plugin_manager: Any) -> dict[str, Any]:
    if plugin_manager is None:
        return {}
    for method_name in ("gui_bridge_metadata", "gui_bridge_settings_metadata", "settings_metadata"):
        getter = getattr(plugin_manager, method_name, None)
        if not callable(getter):
            continue
        payload = getter()
        if isinstance(payload, dict):
            return dict(payload)
    return {}


def metadata_entries(metadata: dict[str, Any], *, keys: tuple[str, ...], key_field: str) -> list[Any] | None:
    for key in keys:
        if key not in metadata:
            continue
        value = metadata.get(key)
        if isinstance(value, list):
            return list(value)
        if isinstance(value, dict):
            entries: list[dict[str, Any]] = []
            for item_key, item_value in value.items():
                if not isinstance(item_value, dict):
                    continue
                normalized = dict(item_value)
                normalized.setdefault(key_field, str(item_key or ""))
                entries.append(normalized)
            return entries
        return []
    return None


def normalize_mcp_server_entry(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    name = str(item.get("name") or "").strip()
    if not name:
        return None
    source = str(item.get("source") or "plugin").strip().lower()
    if source not in {"plugin", "user", "workspace", "runtime", "runtime_dynamic"}:
        source = "plugin"
    payload = {
        "name": name,
        "source": source,
        "config": dict(item.get("config") or {}),
    }
    for key in ("status", "enabled", "scope", "last_error", "error", "error_code", "projection_state"):
        if key in item:
            payload[key] = item.get(key)
    return payload


def normalize_app_connector_entry(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    connector_id = str(
        item.get("connector_id")
        or item.get("connectorId")
        or item.get("connector_key")
        or item.get("connectorKey")
        or item.get("name")
        or ""
    ).strip()
    if not connector_id:
        return None
    enabled = bool(item.get("enabled", True))
    return {
        "connector_id": connector_id,
        "connector_key": connector_id,
        "plugin_name": str(item.get("plugin_name") or item.get("pluginName") or "").strip(),
        "display_name": str(item.get("display_name") or item.get("displayName") or connector_id).strip(),
        "connector_kind": str(item.get("connector_kind") or item.get("connectorKind") or "app").strip(),
        "supports_webhook": bool(item.get("supports_webhook", False)),
        "supports_polling": bool(item.get("supports_polling", False)),
        "supports_actions": bool(item.get("supports_actions", item.get("supportsActions", True))),
        "enabled": enabled,
        "health": str(item.get("health") or ("ready" if enabled else "warning")).strip(),
        "event_types": [str(value).strip() for value in list(item.get("event_types") or []) if str(value).strip()],
        "action_types": [str(value).strip() for value in list(item.get("action_types") or []) if str(value).strip()],
        "source_kind": str(item.get("source_kind") or item.get("sourceKind") or "plugin_app").strip(),
        "metadata": dict(item.get("metadata") or {}) if isinstance(item.get("metadata"), dict) else {},
    }

from __future__ import annotations

from typing import Any, Dict, List, Optional

from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.tools_core import registry_runtime as registry_runtime_service


def _contract_item_dict(item: Any) -> Dict[str, Any]:
    return registry_runtime_service.contract_item_dict(item)


def _contract_item_text(item: Any, *names: str) -> str:
    return registry_runtime_service.contract_item_text(item, *names)


def _contract_item_bool(item: Any, *names: str, default: bool = False) -> bool:
    return registry_runtime_service.contract_item_bool(item, *names, default=default)


def _contract_item_list(item: Any, *names: str) -> List[str]:
    return registry_runtime_service.contract_item_list(item, *names)


def _contract_item_mapping(item: Any, *names: str) -> Dict[str, Any]:
    return registry_runtime_service.contract_item_mapping(item, *names)


def connector_approval_required(*, supports_actions: bool, approval_policy: str) -> bool:
    from cli.agent_cli.runtime_action_policy_runtime import evaluate_connector_action_policy

    return bool(
        evaluate_connector_action_policy(
            supports_actions=supports_actions,
            approval_policy=approval_policy,
        ).get("approval_required")
    )


def connector_approval_contract(*, supports_actions: bool, approval_policy: str) -> Dict[str, Any]:
    from cli.agent_cli.runtime_action_policy_runtime import evaluate_connector_action_policy

    return dict(
        evaluate_connector_action_policy(
            supports_actions=supports_actions,
            approval_policy=approval_policy,
        ).get("payload")
        or {}
    )


def plugin_contract_metadata(plugin_manager: Any) -> Dict[str, Any]:
    return registry_runtime_service.plugin_contract_metadata(plugin_manager)


def metadata_entries(metadata: Dict[str, Any], *, keys: tuple[str, ...], key_field: str) -> List[Any] | None:
    return registry_runtime_service.metadata_entries(metadata, keys=keys, key_field=key_field)


def normalize_mcp_server_entry(item: Any) -> Dict[str, Any] | None:
    return registry_runtime_service.normalize_mcp_server_entry(item)


def _mcp_server_entry_payload(
    item: Any,
    *,
    default_source: str | None = None,
) -> Dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    raw = dict(item)
    if default_source and not str(raw.get("source") or "").strip():
        raw["source"] = default_source
    normalized = normalize_mcp_server_entry(raw)
    if normalized is None:
        return None
    config = dict(normalized.get("config") or {})
    for key in ("url", "transport", "type", "command", "args", "env", "headers", "cwd", "timeout_seconds", "timeout_sec"):
        if key in raw and key not in config:
            config[key] = raw.get(key)
    normalized["config"] = config
    normalized.update({key: value for key, value in raw.items() if key not in normalized})
    return normalized


def _mcp_server_entries_from_list(items: Any) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for raw in list(items or []):
        payload = _mcp_server_entry_payload(raw)
        if payload is not None:
            entries.append(payload)
    return entries


def _mcp_server_entries_from_map(
    raw_mcp_servers: Dict[str, Any],
    *,
    user_configured: Dict[str, Any],
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for name in sorted(raw_mcp_servers):
        key = str(name or "").strip()
        if not key:
            continue
        raw = dict(raw_mcp_servers.get(name) or {})
        raw.setdefault("name", key)
        payload = _mcp_server_entry_payload(
            raw,
            default_source="user" if key in user_configured else "plugin",
        )
        if payload is not None:
            items.append(payload)
    return items


def _mcp_runtime_fields_present(items: List[Dict[str, Any]]) -> bool:
    runtime_fields = {"status", "projection_state", "error", "error_code", "last_error"}
    for item in list(items or []):
        if any(field in item for field in runtime_fields):
            return True
    return False


def _merge_mcp_server_entries(
    base_entries: List[Dict[str, Any]],
    overlay_entries: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    index_by_name: Dict[str, int] = {}
    for source_entries in (base_entries, overlay_entries):
        for raw in list(source_entries or []):
            name = str(raw.get("name") or "").strip()
            if not name:
                continue
            payload = dict(raw)
            existing_index = index_by_name.get(name)
            if existing_index is None:
                index_by_name[name] = len(merged)
                merged.append(payload)
                continue
            combined = dict(merged[existing_index])
            for key, value in payload.items():
                if key == "config" and isinstance(value, dict):
                    if value or "config" not in combined:
                        combined["config"] = dict(value)
                    continue
                combined[key] = value
            merged[existing_index] = combined
    return merged


def runtime_registry_mcp_server_entries(
    plugin_manager: Any,
    *,
    runtime_capabilities: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    metadata = plugin_contract_metadata(plugin_manager)
    canonical_entries = metadata_entries(metadata, keys=("mcpServers", "mcp_servers"), key_field="name")
    canonical_items = _mcp_server_entries_from_list(canonical_entries) if canonical_entries is not None else []
    capabilities = dict(runtime_capabilities or {})
    runtime_entries = capabilities.get("mcp_server_entries")
    if isinstance(runtime_entries, list):
        items = _mcp_server_entries_from_list(runtime_entries)
        if items:
            return _merge_mcp_server_entries(canonical_items, items)
    raw_mcp_servers = capabilities.get("mcp_servers")
    if isinstance(raw_mcp_servers, dict):
        user_configured: Dict[str, Any] = {}
        if plugin_manager is not None:
            user_mcp_getter = getattr(plugin_manager, "user_configured_mcp_servers", None)
            user_configured = dict(user_mcp_getter() or {}) if callable(user_mcp_getter) else {}
        items = _mcp_server_entries_from_map(raw_mcp_servers, user_configured=user_configured)
        runtime_map_getter = getattr(plugin_manager, "mcp_server_runtime_map", None)
        if not canonical_items:
            return items
        if callable(runtime_map_getter) or _mcp_runtime_fields_present(items):
            return _merge_mcp_server_entries(canonical_items, items)
        return canonical_items
    if canonical_items:
        return canonical_items
    if plugin_manager is None:
        return []
    configured_mcp_getter = getattr(plugin_manager, "configured_mcp_servers", None)
    user_mcp_getter = getattr(plugin_manager, "user_configured_mcp_servers", None)
    if not callable(configured_mcp_getter):
        return []
    configured = dict(configured_mcp_getter() or {})
    user_configured = dict(user_mcp_getter() or {}) if callable(user_mcp_getter) else {}
    return _mcp_server_entries_from_map(configured, user_configured=user_configured)


def normalize_app_connector_entry(item: Any) -> Dict[str, Any] | None:
    return registry_runtime_service.normalize_app_connector_entry(item)


def runtime_registry_app_connector_entries(
    plugin_manager: Any,
    *,
    runtime_capabilities: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    metadata = plugin_contract_metadata(plugin_manager)
    canonical_entries = metadata_entries(metadata, keys=("appConnectors", "app_connectors"), key_field="connector_id")
    if canonical_entries is not None:
        source_entries = list(canonical_entries)
    else:
        capabilities = dict(runtime_capabilities or {})
        runtime_entries = capabilities.get("app_connectors")
        if isinstance(runtime_entries, list):
            source_entries = list(runtime_entries)
        elif plugin_manager is not None:
            app_connector_getter = getattr(plugin_manager, "effective_app_connectors", None)
            source_entries = list(app_connector_getter() or []) if callable(app_connector_getter) else []
        else:
            source_entries = []
    items: List[Dict[str, Any]] = []
    for raw in source_entries:
        normalized = normalize_app_connector_entry(raw)
        if normalized is not None:
            items.append(normalized)
    return items


def app_connector_contract_item(
    item: Any,
    *,
    approval_policy: str,
    plugin_enabled: bool | None = None,
) -> Dict[str, Any] | None:
    normalized = normalize_app_connector_entry(item)
    if normalized is None:
        return None
    if plugin_enabled is not None:
        effective_enabled = bool(plugin_enabled) and bool(normalized.get("enabled", True))
        normalized["enabled"] = effective_enabled
        if not str(normalized.get("health") or "").strip():
            normalized["health"] = "ready" if effective_enabled else "warning"
        elif not effective_enabled:
            normalized["health"] = "warning"
    supports_actions = bool(normalized.get("supports_actions"))
    normalized["approval_required"] = connector_approval_required(
        supports_actions=supports_actions,
        approval_policy=approval_policy,
    )
    normalized["approval"] = connector_approval_contract(
        supports_actions=supports_actions,
        approval_policy=approval_policy,
    )
    return normalized


def gateway_connector_contract_item(
    item: Any,
    *,
    approval_policy: str,
    plugin_enabled: bool | None = None,
) -> Dict[str, Any] | None:
    connector_key = _contract_item_text(item, "connector_key", "connectorKey", "name")
    if not connector_key:
        return None
    enabled_by_default = _contract_item_bool(item, "enabled_by_default", "enabled", default=True)
    effective_enabled = enabled_by_default if plugin_enabled is None else bool(plugin_enabled) and enabled_by_default
    supports_actions = _contract_item_bool(item, "supports_actions", "supportsActions")
    return {
        "connector_id": connector_key,
        "connector_key": connector_key,
        "plugin_name": _contract_item_text(item, "plugin_name", "pluginName"),
        "display_name": _contract_item_text(item, "display_name", "displayName") or connector_key,
        "connector_kind": _contract_item_text(item, "connector_kind", "connectorKind"),
        "supports_webhook": _contract_item_bool(item, "supports_webhook", "supportsWebhook"),
        "supports_polling": _contract_item_bool(item, "supports_polling", "supportsPolling"),
        "supports_actions": supports_actions,
        "approval_required": connector_approval_required(
            supports_actions=supports_actions,
            approval_policy=approval_policy,
        ),
        "approval": connector_approval_contract(
            supports_actions=supports_actions,
            approval_policy=approval_policy,
        ),
        "enabled": effective_enabled,
        "health": "ready" if effective_enabled else "warning",
        "event_types": _contract_item_list(item, "event_types", "eventTypes"),
        "action_types": _contract_item_list(item, "action_types", "actionTypes"),
        "source_kind": _contract_item_text(item, "source_kind", "sourceKind") or "gateway",
        "config_schema_ref": _contract_item_dict(item).get("config_schema_ref", getattr(item, "config_schema_ref", None)),
        "metadata": _contract_item_mapping(item, "metadata"),
    }

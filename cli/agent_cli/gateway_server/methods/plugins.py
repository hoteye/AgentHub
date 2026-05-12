from __future__ import annotations

from typing import Any

from cli.agent_cli.tools_core.registry import (
    app_connector_contract_item as _shared_app_connector_contract_item,
    gateway_connector_contract_item as _shared_gateway_connector_contract_item,
    runtime_registry_app_connector_entries as _shared_runtime_registry_app_connector_entries,
    runtime_registry_mcp_server_entries as _shared_runtime_registry_mcp_server_entries,
)
from cli.agent_cli.runtime_tools_surface_runtime import runtime_tools_capabilities as _projected_runtime_tools_capabilities

from . import GatewayMethodFamily


def _first_text(params: dict[str, Any], *names: str) -> str:
    for name in names:
        value = params.get(name)
        if value is None:
            continue
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()
    return ""


def _list_texts(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _to_dict(item: Any) -> dict[str, Any]:
    if item is None:
        return {}
    to_dict = getattr(item, "to_dict", None)
    if callable(to_dict):
        value = to_dict()
        return dict(value or {}) if isinstance(value, dict) else {}
    if isinstance(item, dict):
        return dict(item)
    return {}


def _plugin_manager(runtime: Any) -> Any | None:
    tools = getattr(runtime, "tools", None)
    return getattr(tools, "_plugin_manager", None)


def _runtime_policy_status(runtime: Any) -> dict[str, str]:
    getter = getattr(runtime, "runtime_policy_status", None)
    if not callable(getter):
        return {}
    value = getter() or {}
    return dict(value) if isinstance(value, dict) else {}


def _runtime_tools_capabilities(runtime: Any) -> dict[str, Any]:
    return _projected_runtime_tools_capabilities(runtime)


def _plugin_state_map(plugin_items: list[dict[str, Any]]) -> dict[str, bool]:
    state: dict[str, bool] = {}
    for item in plugin_items:
        enabled = bool(item.get("enabled"))
        for key_name in ("plugin_id", "config_name", "name"):
            key = str(item.get(key_name) or "").strip()
            if key:
                state[key] = enabled
    return state


def _plugin_health(item: dict[str, Any]) -> str:
    if str(item.get("error") or "").strip():
        return "error"
    return "ready" if bool(item.get("enabled")) else "warning"


def _normalize_plugin_summary(item: Any) -> dict[str, Any]:
    raw = _to_dict(item)
    return {
        "plugin_id": str(raw.get("plugin_id") or raw.get("name") or raw.get("plugin_name") or "").strip(),
        "config_name": str(raw.get("config_name") or raw.get("plugin_id") or raw.get("name") or "").strip(),
        "name": str(raw.get("name") or raw.get("plugin_name") or "").strip(),
        "version": str(raw.get("version") or "").strip(),
        "description": str(raw.get("description") or "").strip(),
        "api_version": str(raw.get("api_version") or "").strip(),
        "plugin_kind": str(raw.get("plugin_kind") or "").strip(),
        "distribution": str(raw.get("distribution") or "").strip(),
        "min_host_version": str(raw.get("min_host_version") or "").strip(),
        "enabled": bool(raw.get("enabled")),
        "health": _plugin_health(raw),
        "commercial": bool(raw.get("commercial")),
        "dependencies": _list_texts(raw.get("dependencies")),
        "command_count": int(raw.get("command_count") or 0),
        "tool_count": int(raw.get("tool_count") or 0),
        "connector_count": int(raw.get("connector_count") or 0),
        "trigger_count": int(raw.get("trigger_count") or 0),
        "policy_count": int(raw.get("policy_count") or 0),
        "workflow_count": int(raw.get("workflow_count") or 0),
        "skill_root_count": int(raw.get("skill_root_count") or 0),
        "app_count": int(raw.get("app_count") or 0),
        "mcp_server_count": int(raw.get("mcp_server_count") or 0),
        "root": str(raw.get("root") or "").strip() or None,
        "error": str(raw.get("error") or "").strip() or None,
    }


def _normalize_gateway_connector(item: Any, *, plugin_state: dict[str, bool], runtime: Any) -> dict[str, Any]:
    raw = _to_dict(item)
    plugin_name = str(raw.get("plugin_name") or "").strip()
    plugin_enabled = plugin_state.get(plugin_name, True)
    approval_policy = str(_runtime_policy_status(runtime).get("approval_policy") or "").strip().lower()
    normalized = _shared_gateway_connector_contract_item(
        raw,
        approval_policy=approval_policy,
        plugin_enabled=plugin_enabled,
    )
    return dict(normalized or {})


def _normalize_app_connector(item: Any, *, plugin_state: dict[str, bool], runtime: Any) -> dict[str, Any]:
    raw = _to_dict(item)
    connector_id = str(raw.get("connector_id") or raw.get("connectorId") or raw.get("connector_key") or raw.get("name") or "").strip()
    plugin_name = str(raw.get("plugin_name") or raw.get("pluginName") or "").strip()
    plugin_enabled = plugin_state.get(plugin_name, True)
    approval_policy = str(_runtime_policy_status(runtime).get("approval_policy") or "").strip().lower()
    normalized = _shared_app_connector_contract_item(
        raw,
        approval_policy=approval_policy,
        plugin_enabled=plugin_enabled,
    )
    if normalized is None:
        return {}
    if connector_id and not str(normalized.get("connector_id") or "").strip():
        normalized["connector_id"] = connector_id
        normalized["connector_key"] = connector_id
    if plugin_name and not str(normalized.get("plugin_name") or "").strip():
        normalized["plugin_name"] = plugin_name
    return dict(normalized)


def _runtime_registry_contract(
    runtime: Any,
    *,
    manager: Any | None,
    plugin_state: dict[str, bool],
) -> dict[str, Any]:
    capabilities = _runtime_tools_capabilities(runtime)
    workspace_trust = str(capabilities.get("workspace_trust") or "").strip()
    if not workspace_trust and manager is not None:
        trust_getter = getattr(manager, "workspace_trust_level", None)
        if callable(trust_getter):
            workspace_trust = str(trust_getter() or "").strip()
    if not workspace_trust:
        workspace_trust = "trusted"

    mcp_entries = _shared_runtime_registry_mcp_server_entries(
        manager,
        runtime_capabilities=capabilities,
    )

    app_connectors: list[dict[str, Any]] = []
    seen_connector_ids: set[str] = set()
    source_entries = _shared_runtime_registry_app_connector_entries(
        manager,
        runtime_capabilities=capabilities,
    )
    for item in source_entries:
        normalized = _normalize_app_connector(item, plugin_state=plugin_state, runtime=runtime)
        connector_id = str(normalized.get("connector_id") or "").strip()
        if not connector_id or connector_id in seen_connector_ids:
            continue
        seen_connector_ids.add(connector_id)
        app_connectors.append(normalized)

    return {
        "workspace_trust": workspace_trust,
        "mcp_servers": mcp_entries,
        "app_connectors": app_connectors,
        "tool_count": int(capabilities.get("count") or 0),
        "source": "tools.capabilities" if bool(capabilities) else "plugin_manager",
    }


def _normalize_trigger(item: Any, *, plugin_state: dict[str, bool]) -> dict[str, Any]:
    raw = _to_dict(item)
    plugin_name = str(raw.get("plugin_name") or "").strip()
    plugin_enabled = plugin_state.get(plugin_name, True)
    enabled = plugin_enabled and bool(raw.get("enabled", True))
    return {
        "trigger_key": str(raw.get("trigger_key") or "").strip(),
        "plugin_name": plugin_name,
        "trigger_kind": str(raw.get("trigger_kind") or "").strip(),
        "connector_key": str(raw.get("connector_key") or "").strip() or None,
        "event_types": _list_texts(raw.get("event_types")),
        "workflow_name": str(raw.get("workflow_name") or "").strip(),
        "priority": int(raw.get("priority") or 0),
        "enabled": enabled,
        "health": "ready" if enabled else "warning",
        "filters": dict(raw.get("filters") or {}) if isinstance(raw.get("filters"), dict) else {},
        "metadata": dict(raw.get("metadata") or {}) if isinstance(raw.get("metadata"), dict) else {},
    }


def _plugins_list(**kwargs: Any) -> dict[str, Any]:
    params = dict(kwargs.get("params") or {})
    runtime = kwargs["runtime"]
    manager = _plugin_manager(runtime)
    plugin_name_filter = _first_text(params, "pluginName", "plugin_name")
    raw_plugins = list(manager.list_plugins() or []) if manager is not None and callable(getattr(manager, "list_plugins", None)) else []
    plugins = [_normalize_plugin_summary(item) for item in raw_plugins]
    if plugin_name_filter:
        plugins = [
            item
            for item in plugins
            if plugin_name_filter in {
                str(item.get("plugin_id") or "").strip(),
                str(item.get("config_name") or "").strip(),
                str(item.get("name") or "").strip(),
            }
        ]
    plugin_state = _plugin_state_map(raw_plugins)
    runtime_registry = _runtime_registry_contract(runtime, manager=manager, plugin_state=plugin_state)
    workspace_trust = str(runtime_registry.get("workspace_trust") or "trusted")
    return {
        "plugins": plugins,
        "workspaceTrust": workspace_trust,
        "runtimeRegistry": {
            "workspaceTrust": workspace_trust,
            "mcpServers": list(runtime_registry.get("mcp_servers") or []),
            "appConnectors": list(runtime_registry.get("app_connectors") or []),
            "toolCount": int(runtime_registry.get("tool_count") or 0),
            "source": str(runtime_registry.get("source") or ""),
        },
        "runtimePolicy": _runtime_policy_status(runtime),
        "counts": {
            "plugins": len(plugins),
            "enabled": sum(1 for item in plugins if bool(item.get("enabled"))),
            "withErrors": sum(1 for item in plugins if str(item.get("error") or "").strip()),
        },
    }


def _plugins_connectors_list(**kwargs: Any) -> dict[str, Any]:
    params = dict(kwargs.get("params") or {})
    runtime = kwargs["runtime"]
    manager = _plugin_manager(runtime)
    plugin_name_filter = _first_text(params, "pluginName", "plugin_name")
    raw_plugins = list(manager.list_plugins() or []) if manager is not None and callable(getattr(manager, "list_plugins", None)) else []
    plugin_state = _plugin_state_map(raw_plugins)
    runtime_registry = _runtime_registry_contract(runtime, manager=manager, plugin_state=plugin_state)
    connectors: list[dict[str, Any]] = []
    seen_connector_ids: set[str] = set()
    if manager is not None:
        connector_getter = getattr(manager, "connector_registrations", None)
        if callable(connector_getter):
            for item in connector_getter() or []:
                normalized = _normalize_gateway_connector(item, plugin_state=plugin_state, runtime=runtime)
                connector_id = str(normalized.get("connector_id") or "").strip()
                if connector_id in seen_connector_ids:
                    continue
                if plugin_name_filter and normalized["plugin_name"] != plugin_name_filter:
                    continue
                seen_connector_ids.add(connector_id)
                connectors.append(normalized)
    for item in list(runtime_registry.get("app_connectors") or []):
        normalized = _normalize_app_connector(item, plugin_state=plugin_state, runtime=runtime)
        connector_id = str(normalized.get("connector_id") or "").strip()
        if not connector_id or connector_id in seen_connector_ids:
            continue
        if plugin_name_filter and normalized["plugin_name"] != plugin_name_filter:
            continue
        seen_connector_ids.add(connector_id)
        connectors.append(normalized)
    return {
        "connectors": connectors,
        "runtimeRegistry": {
            "workspaceTrust": str(runtime_registry.get("workspace_trust") or "trusted"),
            "mcpServers": list(runtime_registry.get("mcp_servers") or []),
            "appConnectors": list(runtime_registry.get("app_connectors") or []),
            "toolCount": int(runtime_registry.get("tool_count") or 0),
            "source": str(runtime_registry.get("source") or ""),
        },
        "runtimePolicy": _runtime_policy_status(runtime),
        "counts": {
            "connectors": len(connectors),
            "approvalRequired": sum(1 for item in connectors if bool(item.get("approval_required"))),
        },
    }


def _plugins_triggers_list(**kwargs: Any) -> dict[str, Any]:
    params = dict(kwargs.get("params") or {})
    runtime = kwargs["runtime"]
    manager = _plugin_manager(runtime)
    plugin_name_filter = _first_text(params, "pluginName", "plugin_name")
    connector_key_filter = _first_text(params, "connectorKey", "connector_key")
    raw_plugins = list(manager.list_plugins() or []) if manager is not None and callable(getattr(manager, "list_plugins", None)) else []
    plugin_state = _plugin_state_map(raw_plugins)
    triggers: list[dict[str, Any]] = []
    if manager is not None:
        trigger_getter = getattr(manager, "trigger_registrations", None)
        if callable(trigger_getter):
            for item in trigger_getter() or []:
                normalized = _normalize_trigger(item, plugin_state=plugin_state)
                if plugin_name_filter and normalized["plugin_name"] != plugin_name_filter:
                    continue
                if connector_key_filter and normalized["connector_key"] != connector_key_filter:
                    continue
                triggers.append(normalized)
    return {
        "triggers": triggers,
        "counts": {
            "triggers": len(triggers),
            "enabled": sum(1 for item in triggers if bool(item.get("enabled"))),
        },
    }


_PLUGIN_METHOD_SUMMARIES = {
    "plugins.list": "List gateway-visible plugins and their control-plane state.",
    "plugins.connectors.list": "List plugin gateway connectors and app connectors visible to the gateway.",
    "plugins.triggers.list": "List trigger registrations exposed by loaded plugins.",
}

PLUGINS_FAMILY = GatewayMethodFamily(
    family_name="plugins",
    methods=tuple(_PLUGIN_METHOD_SUMMARIES.keys()),
    handlers={
        "plugins.list": _plugins_list,
        "plugins.connectors.list": _plugins_connectors_list,
        "plugins.triggers.list": _plugins_triggers_list,
    },
)

plugins_handlers = PLUGINS_FAMILY.handlers

__all__ = [
    "PLUGINS_FAMILY",
    "plugins_handlers",
]

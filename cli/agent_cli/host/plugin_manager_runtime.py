from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cli.agent_cli.gateway_core.models import (
    ConnectorRegistration,
    PolicyRegistration,
    TriggerRegistration,
)
from cli.agent_cli.host import plugin_capabilities as _plugin_capabilities
from cli.agent_cli.host import plugin_registry as _plugin_registry
from cli.agent_cli.host import plugin_types as _plugin_types
from cli.agent_cli.host.plugin_sources import read_plugin_capability_declarations as _read_plugin_capability_declarations
from cli.agent_cli.host.plugin_store_runtime import _safe_resolve

RegisteredWorkflowHandler = _plugin_types.RegisteredWorkflowHandler


def _active_plugin(plugin: Any) -> bool:
    is_active = getattr(plugin, "is_active", None)
    if callable(is_active):
        try:
            return bool(is_active())
        except Exception:
            return False
    return bool(getattr(plugin, "enabled", False))


def _normalized_plugin_capability_declarations(plugin: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    items = getattr(plugin, "capability_declarations", None)
    if not isinstance(items, list):
        items = getattr(plugin, "plugin_capability_declarations", None)
    if not isinstance(items, list):
        return []
    plugin_name = str(getattr(plugin, "plugin_name", "") or "").strip()
    source_kind = str(getattr(plugin, "source_kind", "") or "").strip()
    config_name = str(getattr(plugin, "config_name", "") or "").strip()
    for item in items:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        if plugin_name and not str(row.get("plugin_name") or "").strip():
            row["plugin_name"] = plugin_name
        if source_kind and not str(row.get("source_kind") or "").strip():
            row["source_kind"] = source_kind
        if config_name and not str(row.get("config_name") or "").strip():
            row["config_name"] = config_name
        normalized.append(row)
    return normalized


def _plugin_capability_declarations_with_fallback(plugin: Any) -> List[Dict[str, Any]]:
    declared = _normalized_plugin_capability_declarations(plugin)
    if declared:
        return declared
    root = getattr(plugin, "root", None)
    plugin_name = str(getattr(plugin, "plugin_name", "") or "").strip()
    if root is None:
        return []
    try:
        payload = _read_plugin_capability_declarations(_safe_resolve(root), plugin_name=plugin_name)
    except Exception:
        return []
    if not isinstance(payload, list) or not payload:
        return []
    if hasattr(plugin, "capability_declarations"):
        plugin.capability_declarations = list(payload)
    setattr(plugin, "plugin_capability_declarations", list(payload))
    return _normalized_plugin_capability_declarations(plugin)


def command_specs(self: Any) -> List[Dict[str, str]]:
    specs = list(_plugin_registry.command_specs(self._commands))
    mcp_command_specs = getattr(self, "mcp_command_specs", None)
    if callable(mcp_command_specs):
        specs.extend(
            dict(item)
            for item in list(mcp_command_specs() or [])
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        )
    return specs


def execute_command(self: Any, name: str, arg_text: str, runtime: Any) -> Optional[Tuple[str, List[Any]]]:
    mcp_execute_command = getattr(self, "mcp_execute_command", None)
    if callable(mcp_execute_command):
        mcp_result = mcp_execute_command(name, arg_text, runtime)
        if mcp_result is not None:
            return mcp_result
    return _plugin_registry.execute_command(
        self._commands,
        name=name,
        arg_text=arg_text,
        runtime=runtime,
    )


def tool_specs(self: Any) -> List[Dict[str, Any]]:
    specs = list(_plugin_registry.tool_specs(self._tools))
    mcp_tool_specs = getattr(self, "mcp_tool_specs", None)
    if callable(mcp_tool_specs):
        specs.extend(
            dict(item)
            for item in list(mcp_tool_specs() or [])
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        )
    return specs


def connector_registrations(self: Any) -> List[ConnectorRegistration]:
    return _plugin_registry.registrations(self._connectors)


def trigger_registrations(self: Any) -> List[TriggerRegistration]:
    return _plugin_registry.registrations(self._triggers)


def policy_registrations(self: Any) -> List[PolicyRegistration]:
    return _plugin_registry.registrations(self._policies)


def connector_registrations_for_plugin(self: Any, plugin_name: str) -> List[ConnectorRegistration]:
    return _plugin_registry.registrations_for_plugin(self._connectors, plugin_name=plugin_name)


def trigger_registrations_for_plugin(self: Any, plugin_name: str) -> List[TriggerRegistration]:
    return _plugin_registry.registrations_for_plugin(self._triggers, plugin_name=plugin_name)


def policy_registrations_for_plugin(self: Any, plugin_name: str) -> List[PolicyRegistration]:
    return _plugin_registry.registrations_for_plugin(self._policies, plugin_name=plugin_name)


def workflow_handler_registrations(self: Any) -> List[RegisteredWorkflowHandler]:
    return _plugin_registry.workflow_handler_registrations(self._workflow_handlers)


def workflow_handler_registrations_for_plugin(self: Any, plugin_name: str) -> List[RegisteredWorkflowHandler]:
    return _plugin_registry.workflow_handler_registrations_for_plugin(
        self._workflow_handlers,
        plugin_name=plugin_name,
    )


def get_workflow_handler(
    self: Any,
    *,
    plugin_name: str,
    workflow_name: str,
) -> Optional[RegisteredWorkflowHandler]:
    return _plugin_registry.get_workflow_handler(
        self._workflow_handlers,
        plugin_name=plugin_name,
        workflow_name=workflow_name,
    )


def provider_tool_specs(self: Any) -> List[Dict[str, Any]]:
    specs = list(_plugin_capabilities.provider_tool_specs(self._plugins))
    mcp_provider_tool_specs = getattr(self, "mcp_provider_tool_specs", None)
    if callable(mcp_provider_tool_specs):
        specs.extend(
            dict(item)
            for item in list(mcp_provider_tool_specs() or [])
            if isinstance(item, dict)
        )
    return specs


def plugin_capability_declarations(self: Any, *, include_inactive: bool = False) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for plugin in list(getattr(self, "_plugins", []) or []):
        if not include_inactive and not _active_plugin(plugin):
            continue
        rows.extend(_plugin_capability_declarations_with_fallback(plugin))
    return rows


def plugin_capability_declarations_for_plugin(
    self: Any,
    plugin_name: str,
    *,
    include_inactive: bool = False,
) -> List[Dict[str, Any]]:
    target = str(plugin_name or "").strip()
    if not target:
        return []
    rows: List[Dict[str, Any]] = []
    for plugin in list(getattr(self, "_plugins", []) or []):
        if str(getattr(plugin, "plugin_name", "") or "").strip() != target:
            continue
        if not include_inactive and not _active_plugin(plugin):
            continue
        rows.extend(_plugin_capability_declarations_with_fallback(plugin))
    return rows


def provider_capability_declarations(self: Any, *, include_inactive: bool = False) -> List[Dict[str, Any]]:
    return plugin_capability_declarations(self, include_inactive=include_inactive)


def provider_tool_capability_declarations(self: Any, *, include_inactive: bool = False) -> List[Dict[str, Any]]:
    return plugin_capability_declarations(self, include_inactive=include_inactive)


def plugin_tool_capability_declarations(self: Any, *, include_inactive: bool = False) -> List[Dict[str, Any]]:
    return plugin_capability_declarations(self, include_inactive=include_inactive)


def tool_capability_declarations(self: Any, *, include_inactive: bool = False) -> List[Dict[str, Any]]:
    return plugin_capability_declarations(self, include_inactive=include_inactive)


def provider_system_prompt_fragments(self: Any) -> List[str]:
    return _plugin_capabilities.provider_system_prompt_fragments(self._plugins)


def provider_routing_hints(self: Any) -> List[str]:
    return _plugin_capabilities.provider_routing_hints(self._plugins)


def effective_skill_roots(self: Any) -> List[Path]:
    return _plugin_capabilities.effective_skill_roots(self._plugins, safe_resolve=_safe_resolve)


def effective_mcp_servers(self: Any) -> Dict[str, Dict[str, Any]]:
    return _plugin_capabilities.effective_mcp_servers(self._plugins)


def configured_mcp_servers(self: Any) -> Dict[str, Dict[str, Any]]:
    return _plugin_capabilities.configured_mcp_servers(
        user_configured=self.user_configured_mcp_servers(),
        effective=self.effective_mcp_servers(),
    )


def user_configured_mcp_servers(self: Any) -> Dict[str, Dict[str, Any]]:
    return _plugin_capabilities.user_configured_mcp_servers(self._merged_workspace_config())


def effective_apps(self: Any) -> List[str]:
    return _plugin_capabilities.effective_apps(self._plugins)


def effective_app_connectors(self: Any) -> List[Dict[str, Any]]:
    return _plugin_capabilities.effective_app_connectors(self._plugins)


def mcp_server_summaries(self: Any) -> List[Dict[str, Any]]:
    return _plugin_capabilities.mcp_server_summaries(
        plugins=self._plugins,
        user_configured=self.user_configured_mcp_servers(),
        effective=self.effective_mcp_servers(),
    )


def gui_bridge_metadata(self: Any) -> Dict[str, Any]:
    return _plugin_capabilities.gui_bridge_metadata(
        plugins=self._plugins,
        user_configured=self.user_configured_mcp_servers(),
        effective=self.effective_mcp_servers(),
    )


def invoke_tool(self: Any, name: str, *args: Any, **kwargs: Any) -> Any:
    return _plugin_registry.invoke_tool(self._tools, name=name, args=args, kwargs=kwargs)


def bind_plugin_manager_methods(plugin_manager_cls: Any) -> None:
    plugin_manager_cls.command_specs = command_specs
    plugin_manager_cls.execute_command = execute_command
    plugin_manager_cls.tool_specs = tool_specs
    plugin_manager_cls.connector_registrations = connector_registrations
    plugin_manager_cls.trigger_registrations = trigger_registrations
    plugin_manager_cls.policy_registrations = policy_registrations
    plugin_manager_cls.connector_registrations_for_plugin = connector_registrations_for_plugin
    plugin_manager_cls.trigger_registrations_for_plugin = trigger_registrations_for_plugin
    plugin_manager_cls.policy_registrations_for_plugin = policy_registrations_for_plugin
    plugin_manager_cls.workflow_handler_registrations = workflow_handler_registrations
    plugin_manager_cls.workflow_handler_registrations_for_plugin = workflow_handler_registrations_for_plugin
    plugin_manager_cls.get_workflow_handler = get_workflow_handler
    plugin_manager_cls.provider_tool_specs = provider_tool_specs
    plugin_manager_cls.plugin_capability_declarations = plugin_capability_declarations
    plugin_manager_cls.plugin_capability_declarations_for_plugin = plugin_capability_declarations_for_plugin
    plugin_manager_cls.provider_capability_declarations = provider_capability_declarations
    plugin_manager_cls.provider_tool_capability_declarations = provider_tool_capability_declarations
    plugin_manager_cls.plugin_tool_capability_declarations = plugin_tool_capability_declarations
    plugin_manager_cls.tool_capability_declarations = tool_capability_declarations
    plugin_manager_cls.provider_system_prompt_fragments = provider_system_prompt_fragments
    plugin_manager_cls.provider_routing_hints = provider_routing_hints
    plugin_manager_cls.effective_skill_roots = effective_skill_roots
    plugin_manager_cls.effective_mcp_servers = effective_mcp_servers
    plugin_manager_cls.configured_mcp_servers = configured_mcp_servers
    plugin_manager_cls.user_configured_mcp_servers = user_configured_mcp_servers
    plugin_manager_cls.effective_apps = effective_apps
    plugin_manager_cls.effective_app_connectors = effective_app_connectors
    plugin_manager_cls.mcp_server_summaries = mcp_server_summaries
    plugin_manager_cls.gui_bridge_metadata = gui_bridge_metadata
    plugin_manager_cls.invoke_tool = invoke_tool

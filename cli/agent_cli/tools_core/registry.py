from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.models import CommandExecutionResult, ToolEvent, generic_tool_call_item_events, tool_events_to_turn_events
from cli.agent_cli.providers.tool_specs import (
    base_capability_specs as _shared_base_capability_specs,
    merged_capability_specs as _shared_merged_capability_specs,
)
from cli.agent_cli.tools_core import registry_runtime as registry_runtime_service
from cli.agent_cli.tools_core import registry_helpers as helpers

try:
    from shared.web_automation.client import BrowserClient
except ImportError:
    BrowserClient = None


def base_capability_specs() -> List[Dict[str, Any]]:
    return _shared_base_capability_specs()


def merged_capability_specs(
    *,
    plugin_manager_factory: Optional[Callable[[], Optional[PluginManager]]] = None,
) -> List[Dict[str, Any]]:
    return _shared_merged_capability_specs(plugin_manager_factory=plugin_manager_factory)


def build_capabilities_payload(
    *,
    plugin_manager_factory: Optional[Callable[[], Optional[PluginManager]]] = None,
) -> Dict[str, Any]:
    return registry_runtime_service.build_capabilities_payload(
        plugin_manager_factory=plugin_manager_factory,
        merged_capability_specs_fn=merged_capability_specs,
    )


connector_approval_required = helpers.connector_approval_required
connector_approval_contract = helpers.connector_approval_contract
plugin_contract_metadata = helpers.plugin_contract_metadata
metadata_entries = helpers.metadata_entries
normalize_mcp_server_entry = helpers.normalize_mcp_server_entry
runtime_registry_mcp_server_entries = helpers.runtime_registry_mcp_server_entries
normalize_app_connector_entry = helpers.normalize_app_connector_entry
runtime_registry_app_connector_entries = helpers.runtime_registry_app_connector_entries
app_connector_contract_item = helpers.app_connector_contract_item
gateway_connector_contract_item = helpers.gateway_connector_contract_item


class PluginBridge:
    def __init__(self, manager: PluginManager) -> None:
        self._manager = manager

    @staticmethod
    def to_event(name: str, ok: bool, summary: str, payload: Dict[str, Any]) -> ToolEvent:
        return ToolEvent(name=name, ok=bool(ok), summary=summary, payload=payload)

    def tool_specs(self) -> List[Dict[str, Any]]:
        return self._manager.tool_specs()

    def command_specs(self) -> List[Dict[str, str]]:
        return self._manager.command_specs()

    def execute_command(self, name: str, arg_text: str, runtime: Any) -> Optional[tuple[str, list[ToolEvent]]]:
        return self._manager.execute_command(name, arg_text, runtime)

    def execute_command_result(self, name: str, arg_text: str, runtime: Any) -> Optional[CommandExecutionResult]:
        result = self._manager.execute_command(name, arg_text, runtime)
        if result is None:
            return None
        if isinstance(result, CommandExecutionResult):
            return result
        assistant_text, events = result
        item_events, _ = tool_events_to_turn_events(list(events or []), start_index=0)
        return CommandExecutionResult(
            assistant_text=str(assistant_text or ""),
            tool_events=list(events or []),
            item_events=item_events,
        )

    def invoke_tool(self, name: str, *args: Any, **kwargs: Any) -> ToolEvent:
        return self._manager.invoke_tool(name, *args, **kwargs)

    def invoke_tool_result(self, name: str, *args: Any, **kwargs: Any) -> CommandExecutionResult:
        event = self.invoke_tool(name, *args, **kwargs)
        arguments = None
        if args or kwargs:
            arguments = {}
            if args:
                arguments["args"] = list(args)
            if kwargs:
                arguments["kwargs"] = dict(kwargs)
        return CommandExecutionResult(
            assistant_text=str(event.summary or ""),
            tool_events=[event],
            item_events=generic_tool_call_item_events(
                tool_name=str(name or event.name or "").strip(),
                arguments=arguments,
                ok=bool(event.ok),
                summary=str(event.summary or ""),
                structured_content=dict(event.payload or {}),
            ),
        )

    def list_plugins(self) -> ToolEvent:
        payload = {"ok": True, "plugins": self._manager.list_plugins()}
        return self.to_event("plugins", True, f"loaded {len(payload['plugins'])} plugins", payload)

    def enable_plugin(self, plugin_name: str) -> ToolEvent:
        payload = self._manager.enable_plugin(plugin_name)
        return self.to_event(
            "plugin_enable",
            bool(payload.get("ok")),
            f"plugin enabled: {plugin_name}" if payload.get("ok") else f"failed to enable plugin: {plugin_name}",
            payload,
        )

    def disable_plugin(self, plugin_name: str) -> ToolEvent:
        payload = self._manager.disable_plugin(plugin_name)
        return self.to_event(
            "plugin_disable",
            bool(payload.get("ok")),
            f"plugin disabled: {plugin_name}" if payload.get("ok") else f"failed to disable plugin: {plugin_name}",
            payload,
        )

    def disable_all_plugins(self) -> ToolEvent:
        payload = self._manager.disable_all_plugins()
        disabled_count = int(payload.get("disabled_count") or 0)
        return self.to_event(
            "plugin_disable",
            bool(payload.get("ok")),
            f"disabled {disabled_count} plugins" if payload.get("ok") else "failed to disable all plugins",
            payload,
        )

    def reload_plugins(self) -> ToolEvent:
        self._manager.reload()
        payload = {"ok": True, "plugins": self._manager.list_plugins()}
        return self.to_event("plugin_reload", True, f"reloaded {len(payload['plugins'])} plugins", payload)

    def install_plugin(self, path: str, *, replace: bool = False, scope: str = "user") -> ToolEvent:
        payload = self._manager.install_plugin(path, replace=bool(replace), scope=scope)
        summary = (
            f"plugin installed: {payload.get('plugin_name')}"
            if payload.get("ok")
            else f"failed to install plugin from: {path}"
        )
        return self.to_event("plugin_install", bool(payload.get("ok")), summary, payload)

    def remove_plugin(self, plugin_name: str) -> ToolEvent:
        payload = self._manager.remove_plugin(plugin_name)
        summary = (
            f"plugin removed: {plugin_name}"
            if payload.get("ok")
            else f"failed to remove plugin: {plugin_name}"
        )
        return self.to_event("plugin_remove", bool(payload.get("ok")), summary, payload)

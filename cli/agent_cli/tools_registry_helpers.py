from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core.registry import build_capabilities_payload
from cli.agent_cli.tools_core import tool_registry_compat_runtime, tool_registry_runtime


def workspace_root(self: Any) -> Path:
    return tool_registry_runtime.workspace_root(self)


def file_workspace_root(self: Any) -> Path:
    return tool_registry_runtime.file_workspace_root(self)


def resolve_shell_cwd(self: Any, cwd: Optional[str]) -> str:
    return tool_registry_runtime.resolve_shell_cwd(self, cwd)


def set_workspace_root(self: Any, path: str | Path) -> Path:
    return tool_registry_runtime.set_workspace_root(self, path)


def legacy_capabilities(self: Any) -> Dict[str, Any]:
    return tool_registry_runtime.legacy_capabilities(self)


def capabilities(self: Any) -> Dict[str, Any]:
    return tool_registry_compat_runtime.capabilities_with_patchpoint(
        self,
        build_capabilities_payload_fn=build_capabilities_payload,
    )


def _mcp_tool_registry_contracts(self: Any) -> List[Dict[str, Any]]:
    return tool_registry_compat_runtime.projected_mcp_tool_contracts(get_mcp_runtime(self))


def set_mcp_runtime(self: Any, runtime: Any | None) -> Any | None:
    self._mcp_runtime = runtime
    return self._mcp_runtime


def get_mcp_runtime(self: Any) -> Any | None:
    return self._mcp_runtime


def list_plugins(self: Any) -> ToolEvent:
    return tool_registry_runtime.list_plugins(self)


def list_plugins_result(self: Any) -> CommandExecutionResult:
    return tool_registry_runtime.list_plugins_result(self)


def enable_plugin(self: Any, plugin_name: str) -> ToolEvent:
    return tool_registry_runtime.enable_plugin(self, plugin_name)


def enable_plugin_result(self: Any, plugin_name: str) -> CommandExecutionResult:
    return tool_registry_runtime.enable_plugin_result(self, plugin_name)


def disable_plugin(self: Any, plugin_name: str) -> ToolEvent:
    return tool_registry_runtime.disable_plugin(self, plugin_name)


def disable_plugin_result(self: Any, plugin_name: str) -> CommandExecutionResult:
    return tool_registry_runtime.disable_plugin_result(self, plugin_name)


def disable_all_plugins(self: Any) -> ToolEvent:
    return tool_registry_runtime.disable_all_plugins(self)


def disable_all_plugins_result(self: Any) -> CommandExecutionResult:
    return tool_registry_runtime.disable_all_plugins_result(self)


def reload_plugins(self: Any) -> ToolEvent:
    return tool_registry_runtime.reload_plugins(self)


def reload_plugins_result(self: Any) -> CommandExecutionResult:
    return tool_registry_runtime.reload_plugins_result(self)


def install_plugin(self: Any, path: str, *, replace: bool = False, scope: str = "user") -> ToolEvent:
    return tool_registry_runtime.install_plugin(self, path, replace=replace, scope=scope)


def install_plugin_result(
    self: Any,
    path: str,
    *,
    replace: bool = False,
    scope: str = "user",
) -> CommandExecutionResult:
    return tool_registry_runtime.install_plugin_result(self, path, replace=replace, scope=scope)


def remove_plugin(self: Any, plugin_name: str) -> ToolEvent:
    return tool_registry_runtime.remove_plugin(self, plugin_name)


def remove_plugin_result(self: Any, plugin_name: str) -> CommandExecutionResult:
    return tool_registry_runtime.remove_plugin_result(self, plugin_name)


def plugin_command_specs(self: Any) -> List[Dict[str, str]]:
    return tool_registry_runtime.plugin_command_specs(self)


def run_plugin_command(self: Any, name: str, arg_text: str, runtime: Any) -> Optional[tuple[str, list[ToolEvent]]]:
    return tool_registry_runtime.run_plugin_command(self, name, arg_text, runtime)


def run_plugin_command_result(self: Any, name: str, arg_text: str, runtime: Any) -> Optional[CommandExecutionResult]:
    return tool_registry_runtime.run_plugin_command_result(self, name, arg_text, runtime)


def invoke_plugin_tool(self: Any, name: str, *args: Any, **kwargs: Any) -> ToolEvent:
    return tool_registry_runtime.invoke_plugin_tool(self, name, *args, **kwargs)


def invoke_plugin_tool_result(self: Any, name: str, *args: Any, **kwargs: Any) -> CommandExecutionResult:
    return tool_registry_runtime.invoke_plugin_tool_result(self, name, *args, **kwargs)


def bind_tool_registry_helper_methods(
    tool_registry_cls: type[Any],
    *,
    capabilities_method: Any | None = None,
) -> None:
    tool_registry_cls.workspace_root = workspace_root
    tool_registry_cls.file_workspace_root = file_workspace_root
    tool_registry_cls._resolve_shell_cwd = resolve_shell_cwd
    tool_registry_cls.set_workspace_root = set_workspace_root
    tool_registry_cls._legacy_capabilities = legacy_capabilities
    tool_registry_cls.capabilities = capabilities if capabilities_method is None else capabilities_method
    tool_registry_cls.set_mcp_runtime = set_mcp_runtime
    tool_registry_cls.get_mcp_runtime = get_mcp_runtime
    tool_registry_cls.list_plugins = list_plugins
    tool_registry_cls.list_plugins_result = list_plugins_result
    tool_registry_cls.enable_plugin = enable_plugin
    tool_registry_cls.enable_plugin_result = enable_plugin_result
    tool_registry_cls.disable_plugin = disable_plugin
    tool_registry_cls.disable_plugin_result = disable_plugin_result
    tool_registry_cls.disable_all_plugins = disable_all_plugins
    tool_registry_cls.disable_all_plugins_result = disable_all_plugins_result
    tool_registry_cls.reload_plugins = reload_plugins
    tool_registry_cls.reload_plugins_result = reload_plugins_result
    tool_registry_cls.install_plugin = install_plugin
    tool_registry_cls.install_plugin_result = install_plugin_result
    tool_registry_cls.remove_plugin = remove_plugin
    tool_registry_cls.remove_plugin_result = remove_plugin_result
    tool_registry_cls.plugin_command_specs = plugin_command_specs
    tool_registry_cls.run_plugin_command = run_plugin_command
    tool_registry_cls.run_plugin_command_result = run_plugin_command_result
    tool_registry_cls.invoke_plugin_tool = invoke_plugin_tool
    tool_registry_cls.invoke_plugin_tool_result = invoke_plugin_tool_result

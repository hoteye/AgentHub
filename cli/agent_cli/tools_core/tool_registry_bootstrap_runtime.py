from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.agent_cli import tools_registry_helpers
from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.host_platform import current_host_platform
from cli.agent_cli.tools_core import tool_registry_method_bindings_runtime
from cli.agent_cli.tools_core.project_loader import PROJECT_ROOT
from cli.agent_cli.tools_core.shell_bridge import ShellSessionManager


def initialize_tool_registry_state(
    registry: Any,
    *,
    project_root: Path = PROJECT_ROOT,
) -> None:
    registry._host_platform = current_host_platform()
    registry._office_tools = None
    registry._internal_policy_tools = None
    registry._web_search_tools = None
    registry.HARNESS_ROOT = str(project_root.resolve())
    # `HARNESS_ROOT` stays pinned to the AgentHub codebase. `WORKSPACE_ROOT`
    # tracks the active session directory and is the default base for shell and
    # relative tool paths. `PROJECT_ROOT` tracks the broader file boundary.
    registry.WORKSPACE_ROOT = str(project_root.resolve())
    registry.PROJECT_ROOT = registry.WORKSPACE_ROOT
    registry._plugin_manager = PluginManager(cwd=registry.WORKSPACE_ROOT)
    registry._browser_client = None
    registry._browser_proxy_client = None
    registry._shell_sessions = ShellSessionManager(
        host_platform=registry._host_platform,
        workspace_root_getter=lambda: registry.WORKSPACE_ROOT,
    )
    registry._runtime_policy_status_getter = None
    registry._request_patch_approval_fn = None
    registry._mcp_runtime = None
    registry._file_read_state = {}


def bind_tool_registry_runtime(
    registry_cls: type[Any],
    *,
    capabilities_method: Any | None = None,
) -> None:
    tools_registry_helpers.bind_tool_registry_helper_methods(
        registry_cls,
        capabilities_method=capabilities_method,
    )
    tool_registry_method_bindings_runtime.bind_tool_library_methods(registry_cls)

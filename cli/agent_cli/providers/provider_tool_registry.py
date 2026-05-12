from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.providers import plugin_tool_visibility_runtime as plugin_tool_visibility_runtime_helpers

PluginManagerFactory = Callable[[], Optional[PluginManager]]
FunctionNameFromSpec = Callable[[Any], str]


def _manager_provider_specs(manager: PluginManager | None) -> List[Dict[str, Any]]:
    if manager is None:
        return []
    items: List[Dict[str, Any]] = []
    for getter_name in ("provider_tool_specs", "mcp_provider_tool_specs"):
        getter = getattr(manager, getter_name, None)
        if not callable(getter):
            continue
        for item in list(getter() or []):
            if isinstance(item, dict):
                items.append(item)
    return items


def _visible_manager_function_names(
    *,
    manager: PluginManager | None,
    manager_specs: Sequence[Dict[str, Any]],
    tool_surface_profile: str,
    function_name_from_spec: FunctionNameFromSpec,
) -> List[str]:
    declarations_by_name = plugin_tool_visibility_runtime_helpers.plugin_tool_declarations_by_name(
        manager=manager,
        plugin_specs=manager_specs,
        function_name_from_spec=function_name_from_spec,
    )
    names: List[str] = []
    seen: set[str] = set()
    for item in manager_specs:
        function_name = function_name_from_spec(item)
        if not plugin_tool_visibility_runtime_helpers.plugin_tool_visible_for_profile(
            function_name=function_name,
            tool_surface_profile=tool_surface_profile,
            declarations_by_name=declarations_by_name,
        ):
            continue
        if function_name and function_name not in seen:
            names.append(function_name)
            seen.add(function_name)
    return names


def plugin_visible_provider_tool_names(
    *,
    tool_surface_profile: str = "",
    plugin_manager_factory: PluginManagerFactory | None = None,
    function_name_from_spec: FunctionNameFromSpec,
) -> List[str]:
    manager = plugin_manager_factory() if plugin_manager_factory is not None else PluginManager()
    manager_specs = _manager_provider_specs(manager)
    return _visible_manager_function_names(
        manager=manager,
        manager_specs=manager_specs,
        tool_surface_profile=tool_surface_profile,
        function_name_from_spec=function_name_from_spec,
    )


def provider_tool_names(
    *,
    builtin_tool_order: Sequence[str],
    tool_surface_profile: str = "",
    plugin_manager_factory: PluginManagerFactory | None = None,
    function_name_from_spec: FunctionNameFromSpec,
) -> List[str]:
    names = list(builtin_tool_order)
    seen = set(names)
    manager = plugin_manager_factory() if plugin_manager_factory is not None else PluginManager()
    manager_specs = _manager_provider_specs(manager)
    for function_name in _visible_manager_function_names(
        manager=manager,
        manager_specs=manager_specs,
        tool_surface_profile=tool_surface_profile,
        function_name_from_spec=function_name_from_spec,
    ):
        if function_name and function_name not in seen:
            names.append(function_name)
            seen.add(function_name)
    return names


def merged_provider_tool_specs(
    *,
    builtin_provider_specs: Sequence[Dict[str, Any]],
    tool_surface_profile: str = "",
    plugin_manager_factory: PluginManagerFactory | None = None,
    function_name_from_spec: FunctionNameFromSpec,
) -> List[Dict[str, Any]]:
    specs = [dict(item) for item in list(builtin_provider_specs or [])]
    manager = plugin_manager_factory() if plugin_manager_factory is not None else PluginManager()
    manager_specs = _manager_provider_specs(manager)
    declarations_by_name = plugin_tool_visibility_runtime_helpers.plugin_tool_declarations_by_name(
        manager=manager,
        plugin_specs=manager_specs,
        function_name_from_spec=function_name_from_spec,
    )
    for item in manager_specs:
        function_name = function_name_from_spec(item)
        if not function_name:
            continue
        if not plugin_tool_visibility_runtime_helpers.plugin_tool_visible_for_profile(
            function_name=function_name,
            tool_surface_profile=tool_surface_profile,
            declarations_by_name=declarations_by_name,
        ):
            continue
        specs = [
            existing
            for existing in specs
            if function_name_from_spec(existing) != function_name
        ]
        specs.append(item)
    return specs

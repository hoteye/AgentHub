from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from cli.agent_cli.host import plugin_index_runtime as _plugin_index_runtime
from cli.agent_cli.host import plugin_mutation_runtime as _plugin_mutation_runtime
from cli.agent_cli.host import plugin_types as _plugin_types

LoadedPlugin = _plugin_types.LoadedPlugin


def extract_source_dir(
    source_path: str,
    validate_plugin_dir_fn: Callable[[Path], Optional[str]],
) -> Tuple[Optional[Path], Optional[Path], str, Dict[str, Any]]:
    return _plugin_index_runtime.extract_source_dir(
        source_path,
        validate_plugin_dir_fn=validate_plugin_dir_fn,
    )


def write_plugin_enabled_config(config_path: Path, plugin_key: str, *, enabled: bool) -> None:
    _plugin_mutation_runtime.write_plugin_enabled_config(
        config_path=config_path,
        plugin_key=plugin_key,
        enabled=enabled,
    )


def remove_plugin_config_section(config_path: Path, plugin_key: str) -> None:
    _plugin_mutation_runtime.remove_plugin_config_section(
        config_path=config_path,
        plugin_key=plugin_key,
    )


def install_plugin(
    manager: Any,
    source_path: str,
    *,
    replace: bool = False,
    marketplace_name: Optional[str] = None,
    scope: Optional[str] = None,
) -> Dict[str, Any]:
    return _plugin_mutation_runtime.install_plugin(
        manager,
        source_path,
        replace=replace,
        marketplace_name=marketplace_name,
        scope=scope,
    )


def remove_plugin(manager: Any, plugin_name: str) -> Dict[str, Any]:
    return _plugin_mutation_runtime.remove_plugin(manager, plugin_name)


def list_plugins(manager: Any) -> List[Dict[str, Any]]:
    return _plugin_index_runtime.project_plugins(manager._plugins)


def enable_plugin(manager: Any, plugin_name: str) -> Dict[str, Any]:
    return _plugin_mutation_runtime.enable_plugin(manager, plugin_name)


def disable_plugin(manager: Any, plugin_name: str) -> Dict[str, Any]:
    return _plugin_mutation_runtime.disable_plugin(manager, plugin_name)


def disable_all_plugins(manager: Any) -> Dict[str, Any]:
    return _plugin_mutation_runtime.disable_all_plugins(manager)


def resolve_plugin(manager: Any, plugin_name: str) -> Optional[LoadedPlugin]:
    resolved = _plugin_index_runtime.resolve_plugin(manager._plugins, plugin_name)
    if isinstance(resolved, LoadedPlugin):
        return resolved
    return None

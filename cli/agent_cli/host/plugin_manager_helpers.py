from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from cli.agent_cli.gateway_core.models import (
    ConnectorRegistration,
    PolicyRegistration,
    TriggerRegistration,
)
from cli.agent_cli.host import plugin_config_runtime as _plugin_config_runtime
from cli.agent_cli.host import plugin_host_runtime as _plugin_host_runtime
from cli.agent_cli.host import plugin_index_runtime as _plugin_index_runtime
from cli.agent_cli.host import plugin_manager_helpers_runtime as _plugin_manager_helpers_runtime
from cli.agent_cli.host import plugin_manager_runtime as _plugin_manager_runtime
from cli.agent_cli.host import plugin_mutation_runtime as _plugin_mutation_runtime
from cli.agent_cli.host import plugin_reload_runtime as _plugin_reload_runtime
from cli.agent_cli.host import plugin_runtime_loader as _plugin_runtime_loader
from cli.agent_cli.host import plugin_types as _plugin_types
from cli.agent_cli.host.plugin_manifest import PluginManifest as HostPluginManifest
from cli.agent_cli.host.plugin_sources import (
    default_skill_roots as _default_skill_roots,
    load_apps_from_file as _load_apps_from_file,
    load_mcp_servers_from_file as _load_mcp_servers_from_file,
    read_reference_manifest as _read_reference_manifest,
    read_reference_manifest_as_plugin_manifest as _read_reference_manifest_as_plugin_manifest,
    read_legacy_compat_manifest_metadata as _read_legacy_compat_manifest_metadata,
)
from cli.agent_cli.host.plugin_store_runtime import (
    DEFAULT_APP_CONFIG_FILE,
    DEFAULT_MCP_CONFIG_FILE,
    DEFAULT_PLUGIN_SECTION_MARKETPLACE,
    LEGACY_COMPAT_HOME,
    PluginRegistrationConflictError,
    PluginStoreError,
    _find_project_root,
    default_reference_home,
)
from cli.agent_cli.workspace_context import read_merged_project_toml, workspace_trust_level

CommandHandler = _plugin_types.CommandHandler
ToolHandler = _plugin_types.ToolHandler
WorkflowHandler = _plugin_types.WorkflowHandler
PluginId = _plugin_types.PluginId
RegisteredWorkflowHandler = _plugin_types.RegisteredWorkflowHandler
PluginCommandRegistry = _plugin_types.PluginCommandRegistry
PluginToolRegistry = _plugin_types.PluginToolRegistry
LoadedPlugin = _plugin_types.LoadedPlugin


def required_plugin_files() -> Tuple[str, ...]:
    return _plugin_index_runtime.required_plugin_files()


def normalize_connector_registration(item: Any, *, plugin_name: str) -> Optional[ConnectorRegistration]:
    return _plugin_runtime_loader.normalize_connector_registration(item, plugin_name=plugin_name)


def normalize_trigger_registration(item: Any, *, plugin_name: str) -> Optional[TriggerRegistration]:
    return _plugin_runtime_loader.normalize_trigger_registration(item, plugin_name=plugin_name)


def normalize_policy_registration(item: Any, *, plugin_name: str) -> Optional[PolicyRegistration]:
    return _plugin_runtime_loader.normalize_policy_registration(item, plugin_name=plugin_name)


def normalize_workflow_handler_registration(item: Any, *, plugin_name: str) -> Optional[RegisteredWorkflowHandler]:
    normalized = _plugin_runtime_loader.normalize_workflow_handler_registration(
        item,
        plugin_name=plugin_name,
        workflow_handler_type=RegisteredWorkflowHandler,
    )
    if isinstance(normalized, RegisteredWorkflowHandler):
        return normalized
    return None


def call_runtime_builder(builder: Callable[..., Any], *, plugin_name: str) -> List[Any]:
    return _plugin_runtime_loader.call_runtime_builder(builder, plugin_name=plugin_name)


def ensure_unique_registration(
    seen: Dict[str, Any],
    *,
    key_name: str,
    key_value: str,
    plugin_name: str,
    item: Any,
) -> None:
    _plugin_runtime_loader.ensure_unique_registration(
        seen,
        key_name=key_name,
        key_value=key_value,
        plugin_name=plugin_name,
        item=item,
        conflict_error_type=PluginRegistrationConflictError,
    )


def ensure_project_root_on_path() -> None:
    root_text = str(_find_project_root())
    if root_text not in sys.path:
        sys.path.insert(0, root_text)


def load_enabled_state(state_path: Path) -> Dict[str, bool]:
    return _plugin_host_runtime.load_enabled_state(state_path)


def save_enabled_state(state_path: Path, enabled_map: Dict[str, bool]) -> None:
    _plugin_host_runtime.save_enabled_state(state_path, enabled_map)


def load_state(manager: "PluginManager") -> Dict[str, bool]:
    return load_enabled_state(manager.state_path)


def save_state(manager: "PluginManager", enabled_map: Dict[str, bool]) -> None:
    save_enabled_state(manager.state_path, enabled_map)


def clear_plugin_modules() -> None:
    _plugin_host_runtime.clear_plugin_modules(sys.modules)


def ensure_host_plugin_package(plugin_name: str, plugin_dir: Path) -> None:
    _plugin_host_runtime.ensure_host_plugin_package(plugin_name, plugin_dir, sys.modules)


def load_module_from_file(plugin_name: str, module_name: str, file_path: Path) -> Any:
    return _plugin_host_runtime.load_module_from_file(plugin_name, module_name, file_path, sys.modules)


def validate_plugin_dir(candidate_dir: Path, required_plugin_files_fn: Callable[[], Tuple[str, ...]]) -> Optional[str]:
    return _plugin_index_runtime.validate_plugin_dir(
        candidate_dir,
        read_reference_manifest_fn=_read_reference_manifest,
        required_plugin_files_fn=required_plugin_files_fn,
    )


def config_home_paths(config_path: Path, reference_home: Path, legacy_compat_home: Path) -> List[Path]:
    return _plugin_config_runtime.config_home_paths(
        config_path=config_path,
        reference_home=reference_home,
        default_reference_home=default_reference_home,
        legacy_compat_home=legacy_compat_home,
    )


def merged_workspace_config(manager: "PluginManager") -> Dict[str, Any]:
    return _plugin_config_runtime.merged_workspace_config(
        cwd=manager.cwd,
        home_config_paths=config_home_paths(
            config_path=manager.config_path,
            reference_home=manager.reference_home,
            legacy_compat_home=LEGACY_COMPAT_HOME,
        ),
        read_merged_project_toml_fn=read_merged_project_toml,
    )


def workspace_trust_level_from_paths(manager: "PluginManager") -> str:
    return _plugin_config_runtime.workspace_trust_level_from_paths(
        cwd=manager.cwd,
        home_config_paths=config_home_paths(
            config_path=manager.config_path,
            reference_home=manager.reference_home,
            legacy_compat_home=LEGACY_COMPAT_HOME,
        ),
        workspace_trust_level_fn=workspace_trust_level,
    )


def plugins_feature_enabled_from_config(config: Dict[str, Any]) -> bool:
    return _plugin_config_runtime.plugins_feature_enabled_from_config(config)


def configured_plugins_from_config(config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return _plugin_config_runtime.configured_plugins_from_config(config)


def plugin_enabled(value: Dict[str, Any], default: bool) -> bool:
    return _plugin_config_runtime.plugin_enabled(value, default)


def bundled_plugin_key(plugin_name: str) -> str:
    return _plugin_config_runtime.bundled_plugin_key(
        plugin_name,
        default_plugin_section_marketplace=DEFAULT_PLUGIN_SECTION_MARKETPLACE,
    )


def discover_bundled_sources(
    manager: "PluginManager",
    configured_plugins: Dict[str, Dict[str, Any]],
) -> List["_PluginSource"]:
    return _plugin_config_runtime.discover_bundled_sources(
        bundled_plugin_root=manager.bundled_plugin_root,
        configured_plugins=configured_plugins,
        read_legacy_compat_manifest_metadata_fn=_read_legacy_compat_manifest_metadata,
        bundled_plugin_key_fn=bundled_plugin_key,
        plugin_enabled_fn=plugin_enabled,
        plugin_source_type=_plugin_types._PluginSource,
    )


def configured_external_sources(
    manager: "PluginManager",
    configured_plugins: Dict[str, Dict[str, Any]],
) -> List["_plugin_types._PluginSource"]:
    return _plugin_config_runtime.configured_external_sources(
        configured_plugins=configured_plugins,
        bundled_sources=discover_bundled_sources(manager, configured_plugins),
        plugin_enabled_fn=plugin_enabled,
        parse_plugin_id_fn=PluginId.parse,
        plugin_store=manager.store,
        read_reference_manifest_as_plugin_manifest_fn=_read_reference_manifest_as_plugin_manifest,
        read_legacy_compat_manifest_metadata_fn=_read_legacy_compat_manifest_metadata,
        plugin_source_type=_plugin_types._PluginSource,
        plugin_store_error_type=PluginStoreError,
    )


def compat_reload(manager: "PluginManager") -> None:
    _plugin_reload_runtime.compat_reload(
        manager,
        read_legacy_compat_manifest_metadata_fn=_read_legacy_compat_manifest_metadata,
    )


def reference_reload(manager: "PluginManager") -> None:
    _plugin_reload_runtime.reference_reload(
        manager,
        loaded_plugin_type=LoadedPlugin,
        plugin_manifest_type=_plugin_types.PluginManifest,
        plugin_store_error_type=PluginStoreError,
    )


load_runtime_capabilities = _plugin_manager_helpers_runtime.load_runtime_capabilities


merge_loaded_plugin = _plugin_manager_helpers_runtime.merge_loaded_plugin


assign_state = _plugin_manager_helpers_runtime.assign_state


def reload_manager(manager: "PluginManager") -> None:
    _plugin_reload_runtime.reload(manager)


def extract_source_dir(source_path: str, validate_plugin_dir_fn: Callable[[Path], Optional[str]]) -> Tuple[Optional[Path], Optional[Path], str, Dict[str, Any]]:
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
    manager: "PluginManager",
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


def remove_plugin(manager: "PluginManager", plugin_name: str) -> Dict[str, Any]:
    return _plugin_mutation_runtime.remove_plugin(manager, plugin_name)


def list_plugins(manager: "PluginManager") -> List[Dict[str, Any]]:
    return _plugin_index_runtime.project_plugins(manager._plugins)


def enable_plugin(manager: "PluginManager", plugin_name: str) -> Dict[str, Any]:
    return _plugin_mutation_runtime.enable_plugin(manager, plugin_name)


def disable_plugin(manager: "PluginManager", plugin_name: str) -> Dict[str, Any]:
    return _plugin_mutation_runtime.disable_plugin(manager, plugin_name)


def disable_all_plugins(manager: "PluginManager") -> Dict[str, Any]:
    return _plugin_mutation_runtime.disable_all_plugins(manager)


def resolve_plugin(manager: "PluginManager", plugin_name: str) -> Optional[LoadedPlugin]:
    resolved = _plugin_index_runtime.resolve_plugin(manager._plugins, plugin_name)
    if isinstance(resolved, LoadedPlugin):
        return resolved
    return None

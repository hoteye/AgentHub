from __future__ import annotations

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
from cli.agent_cli.host import plugin_manager_helpers_runtime_config as _config_helpers
from cli.agent_cli.host import plugin_mutation_runtime as _plugin_mutation_runtime
from cli.agent_cli.host import plugin_reload_runtime as _plugin_reload_runtime
from cli.agent_cli.host import plugin_runtime_loader as _plugin_runtime_loader
from cli.agent_cli.host import plugin_manager_helpers_runtime_mutation as _mutation_helpers
from cli.agent_cli.host import plugin_manager_helpers_runtime_state as _state_helpers
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
    PluginRegistrationConflictError,
    PluginStoreError,
)

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


ensure_project_root_on_path = _state_helpers.ensure_project_root_on_path
load_enabled_state = _state_helpers.load_enabled_state
save_enabled_state = _state_helpers.save_enabled_state
clear_plugin_modules = _state_helpers.clear_plugin_modules
ensure_host_plugin_package = _state_helpers.ensure_host_plugin_package
load_module_from_file = _state_helpers.load_module_from_file


validate_plugin_dir = _config_helpers.validate_plugin_dir


config_home_paths = _state_helpers.config_home_paths
merged_workspace_config = _state_helpers.merged_workspace_config
workspace_trust_level_from_paths = _state_helpers.workspace_trust_level_from_paths


plugins_feature_enabled_from_config = _config_helpers.plugins_feature_enabled_from_config


configured_plugins_from_config = _config_helpers.configured_plugins_from_config


plugin_enabled = _config_helpers.plugin_enabled


bundled_plugin_key = _config_helpers.bundled_plugin_key


discover_bundled_sources = _config_helpers.discover_bundled_sources


configured_external_sources = _config_helpers.configured_external_sources


def compat_reload(manager: Any) -> None:
    _plugin_reload_runtime.compat_reload(
        manager,
        read_legacy_compat_manifest_metadata_fn=_read_legacy_compat_manifest_metadata,
    )


def reference_reload(manager: Any) -> None:
    _plugin_reload_runtime.reference_reload(
        manager,
        loaded_plugin_type=LoadedPlugin,
        plugin_manifest_type=_plugin_types.PluginManifest,
        plugin_store_error_type=PluginStoreError,
    )


def load_runtime_capabilities(
    manager: Any,
    *,
    plugin_name: str,
    plugin_dir: Path,
    manifest: HostPluginManifest,
    enabled: bool,
    config_name: str,
    source_kind: str,
    installed: bool,
) -> Tuple[LoadedPlugin, Dict[str, Any]]:
    return _plugin_reload_runtime.load_runtime_capabilities(
        manager,
        plugin_name=plugin_name,
        plugin_dir=plugin_dir,
        manifest=manifest,
        enabled=enabled,
        config_name=config_name,
        source_kind=source_kind,
        installed=installed,
        plugin_store_error_type=PluginStoreError,
        plugin_command_registry_type=PluginCommandRegistry,
        plugin_tool_registry_type=PluginToolRegistry,
        loaded_plugin_type=LoadedPlugin,
        default_skill_roots_fn=_default_skill_roots,
        load_mcp_servers_from_file_fn=_load_mcp_servers_from_file,
        load_apps_from_file_fn=_load_apps_from_file,
        default_mcp_config_file=DEFAULT_MCP_CONFIG_FILE,
        default_app_config_file=DEFAULT_APP_CONFIG_FILE,
    )


def merge_loaded_plugin(
    loaded: LoadedPlugin,
    runtime: Dict[str, Any],
    *,
    plugins: List[LoadedPlugin],
    commands: Dict[str, Any],
    tools: Dict[str, Any],
    connectors: Dict[str, ConnectorRegistration],
    triggers: Dict[str, TriggerRegistration],
    policies: Dict[str, PolicyRegistration],
    workflow_handlers: Dict[Tuple[str, str], RegisteredWorkflowHandler],
    seen_connector_registrations: Dict[str, ConnectorRegistration],
    seen_trigger_registrations: Dict[str, TriggerRegistration],
    seen_policy_registrations: Dict[str, PolicyRegistration],
    seen_workflow_handlers: Dict[Tuple[str, str], RegisteredWorkflowHandler],
) -> None:
    _plugin_reload_runtime.merge_loaded_plugin(
        loaded,
        runtime,
        plugins=plugins,
        commands=commands,
        tools=tools,
        connectors=connectors,
        triggers=triggers,
        policies=policies,
        workflow_handlers=workflow_handlers,
        seen_connector_registrations=seen_connector_registrations,
        seen_trigger_registrations=seen_trigger_registrations,
        seen_policy_registrations=seen_policy_registrations,
        seen_workflow_handlers=seen_workflow_handlers,
        workflow_handler_type=RegisteredWorkflowHandler,
        conflict_error_type=PluginRegistrationConflictError,
    )


def assign_state(
    manager: Any,
    *,
    plugins: List[LoadedPlugin],
    commands: Dict[str, Any],
    tools: Dict[str, Any],
    connectors: Dict[str, ConnectorRegistration],
    triggers: Dict[str, TriggerRegistration],
    policies: Dict[str, PolicyRegistration],
    workflow_handlers: Dict[Tuple[str, str], RegisteredWorkflowHandler],
) -> None:
    _plugin_reload_runtime.assign_state(
        manager,
        plugins=plugins,
        commands=commands,
        tools=tools,
        connectors=connectors,
        triggers=triggers,
        policies=policies,
        workflow_handlers=workflow_handlers,
    )


def reload_manager(manager: Any) -> None:
    _plugin_reload_runtime.reload(manager)


extract_source_dir = _mutation_helpers.extract_source_dir
write_plugin_enabled_config = _mutation_helpers.write_plugin_enabled_config
remove_plugin_config_section = _mutation_helpers.remove_plugin_config_section
install_plugin = _mutation_helpers.install_plugin
remove_plugin = _mutation_helpers.remove_plugin
list_plugins = _mutation_helpers.list_plugins
enable_plugin = _mutation_helpers.enable_plugin
disable_plugin = _mutation_helpers.disable_plugin
disable_all_plugins = _mutation_helpers.disable_all_plugins
resolve_plugin = _mutation_helpers.resolve_plugin

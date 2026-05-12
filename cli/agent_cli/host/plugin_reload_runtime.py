from __future__ import annotations

import importlib
from typing import Any, Dict, List, Tuple

from cli.agent_cli.host import plugin_reload_runtime_helpers as reload_helpers
from cli.agent_cli.host import plugin_runtime_loader as _plugin_runtime_loader


def compat_reload(manager: Any, *, read_legacy_compat_manifest_metadata_fn: Any) -> None:
    manager._ensure_project_root_on_path()
    importlib.invalidate_caches()
    manager._clear_plugin_modules()
    state = manager._load_state()
    plugins: List[Any] = []
    commands: Dict[str, Any] = {}
    tools: Dict[str, Any] = {}
    connectors: Dict[str, Any] = {}
    triggers: Dict[str, Any] = {}
    policies: Dict[str, Any] = {}
    workflow_handlers: Dict[Tuple[str, str], Any] = {}
    seen_connector_registrations: Dict[str, Any] = {}
    seen_trigger_registrations: Dict[str, Any] = {}
    seen_policy_registrations: Dict[str, Any] = {}
    seen_workflow_handlers: Dict[Tuple[str, str], Any] = {}
    if not manager.plugin_root.exists():
        assign_state(
            manager,
            plugins=[],
            commands={},
            tools={},
            connectors={},
            triggers={},
            policies={},
            workflow_handlers={},
        )
        return

    for plugin_dir in sorted(path for path in manager.plugin_root.iterdir() if path.is_dir()):
        if not (plugin_dir / "manifest.py").exists():
            continue
        plugin_name = plugin_dir.name
        manifest = read_legacy_compat_manifest_metadata_fn(plugin_dir)
        if manifest is None:
            continue
        enabled = bool(state.get(plugin_name, manifest.enabled_by_default))
        loaded, runtime = manager._load_runtime_capabilities(
            plugin_name=plugin_name,
            plugin_dir=plugin_dir,
            manifest=manifest,
            enabled=enabled,
            config_name=plugin_name,
            source_kind="legacy",
            installed=plugin_dir != manager.bundled_plugin_root / plugin_name,
        )
        manager._merge_loaded_plugin(
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
        )

    assign_state(
        manager,
        plugins=plugins,
        commands=commands,
        tools=tools,
        connectors=connectors,
        triggers=triggers,
        policies=policies,
        workflow_handlers=workflow_handlers,
    )


def reference_reload(
    manager: Any,
    *,
    loaded_plugin_type: type,
    plugin_manifest_type: type,
    plugin_store_error_type: type[Exception],
) -> None:
    cached = manager._cache_by_cwd.get(manager.cwd)
    if cached is not None:
        assign_state(manager, **cached)
        return
    manager._ensure_project_root_on_path()
    importlib.invalidate_caches()
    manager._clear_plugin_modules()
    merged_config = manager._merged_workspace_config()
    if not manager._plugins_feature_enabled_from_config(merged_config):
        empty_state = reload_helpers.plugin_registry_state(
            plugins=[],
            commands={},
            tools={},
            connectors={},
            triggers={},
            policies={},
            workflow_handlers={},
        )
        manager._cache_by_cwd[manager.cwd] = empty_state
        assign_state(manager, **empty_state)
        return
    configured_plugins = manager._configured_plugins_from_config(merged_config)
    plugin_sources = [
        *manager._discover_bundled_sources(configured_plugins),
        *manager._configured_external_sources(configured_plugins),
    ]
    plugins: List[Any] = []
    commands: Dict[str, Any] = {}
    tools: Dict[str, Any] = {}
    connectors: Dict[str, Any] = {}
    triggers: Dict[str, Any] = {}
    policies: Dict[str, Any] = {}
    workflow_handlers: Dict[Tuple[str, str], Any] = {}
    seen_connector_registrations: Dict[str, Any] = {}
    seen_trigger_registrations: Dict[str, Any] = {}
    seen_policy_registrations: Dict[str, Any] = {}
    seen_workflow_handlers: Dict[Tuple[str, str], Any] = {}
    for source in plugin_sources:
        if source.manifest is not None and not source.enabled:
            reload_helpers.append_unloaded_plugin(
                plugins,
                loaded_plugin_type=loaded_plugin_type,
                plugin_manifest_type=plugin_manifest_type,
                plugin_name=source.plugin_name,
                manifest=source.manifest,
                enabled=False,
                config_name=source.config_name,
                root=source.root,
                installed=source.installed,
                source_kind=source.source_kind,
            )
            continue
        if source.manifest is None and not source.enabled:
            reload_helpers.append_unloaded_plugin(
                plugins,
                loaded_plugin_type=loaded_plugin_type,
                plugin_manifest_type=plugin_manifest_type,
                plugin_name=source.plugin_name,
                manifest=None,
                enabled=False,
                config_name=source.config_name,
                root=source.root,
                installed=source.installed,
                source_kind=source.source_kind,
            )
            continue
        try:
            if source.manifest is None and source.source_kind == "configured":
                raise plugin_store_error_type(f"invalid plugin key `{source.config_name}`; expected <plugin>@<marketplace>")
            manifest = source.manifest or reload_helpers.default_external_manifest(
                plugin_manifest_type=plugin_manifest_type,
                plugin_name=source.plugin_name,
            )
            loaded, runtime = manager._load_runtime_capabilities(
                plugin_name=manifest.name,
                plugin_dir=source.root,
                manifest=manifest,
                enabled=source.enabled,
                config_name=source.config_name,
                source_kind=source.source_kind,
                installed=source.installed,
            )
        except Exception as exc:
            reload_helpers.append_error_plugin(
                plugins,
                loaded_plugin_type=loaded_plugin_type,
                plugin_manifest_type=plugin_manifest_type,
                plugin_name=source.plugin_name,
                manifest=source.manifest,
                enabled=source.enabled,
                config_name=source.config_name,
                root=source.root,
                installed=source.installed,
                source_kind=source.source_kind,
                error=str(exc),
            )
            continue
        manager._merge_loaded_plugin(
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
        )
    state = reload_helpers.plugin_registry_state(
        plugins=plugins,
        commands=commands,
        tools=tools,
        connectors=connectors,
        triggers=triggers,
        policies=policies,
        workflow_handlers=workflow_handlers,
    )
    manager._cache_by_cwd[manager.cwd] = state
    assign_state(manager, **state)


def load_runtime_capabilities(
    manager: Any,
    *,
    plugin_name: str,
    plugin_dir: Any,
    manifest: Any,
    enabled: bool,
    config_name: str,
    source_kind: str,
    installed: bool,
    plugin_store_error_type: type[Exception],
    plugin_command_registry_type: type,
    plugin_tool_registry_type: type,
    loaded_plugin_type: type,
    default_skill_roots_fn: Any,
    load_mcp_servers_from_file_fn: Any,
    load_apps_from_file_fn: Any,
    default_mcp_config_file: str,
    default_app_config_file: str,
) -> Tuple[Any, Dict[str, Any]]:
    try:
        loaded, runtime = _plugin_runtime_loader.load_runtime_capabilities(
            plugin_name=plugin_name,
            plugin_dir=plugin_dir,
            manifest=manifest,
            enabled=enabled,
            config_name=config_name,
            source_kind=source_kind,
            installed=installed,
            required_plugin_files=manager._required_plugin_files(),
            default_skill_roots_fn=default_skill_roots_fn,
            load_mcp_servers_from_file_fn=load_mcp_servers_from_file_fn,
            load_apps_from_file_fn=load_apps_from_file_fn,
            ensure_host_plugin_package_fn=manager._ensure_host_plugin_package,
            load_module_from_file_fn=manager._load_module_from_file,
            plugin_command_registry_type=plugin_command_registry_type,
            plugin_tool_registry_type=plugin_tool_registry_type,
            loaded_plugin_type=loaded_plugin_type,
            default_mcp_config_file=default_mcp_config_file,
            default_app_config_file=default_app_config_file,
        )
    except ValueError as exc:
        raise plugin_store_error_type(str(exc)) from exc
    return loaded, runtime


def merge_loaded_plugin(
    loaded: Any,
    runtime: Dict[str, Any],
    *,
    plugins: List[Any],
    commands: Dict[str, Any],
    tools: Dict[str, Any],
    connectors: Dict[str, Any],
    triggers: Dict[str, Any],
    policies: Dict[str, Any],
    workflow_handlers: Dict[Tuple[str, str], Any],
    seen_connector_registrations: Dict[str, Any],
    seen_trigger_registrations: Dict[str, Any],
    seen_policy_registrations: Dict[str, Any],
    seen_workflow_handlers: Dict[Tuple[str, str], Any],
    workflow_handler_type: type,
    conflict_error_type: type[Exception],
) -> None:
    _plugin_runtime_loader.merge_loaded_plugin(
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
        workflow_handler_type=workflow_handler_type,
        conflict_error_type=conflict_error_type,
    )


def assign_state(
    manager: Any,
    *,
    plugins: List[Any],
    commands: Dict[str, Any],
    tools: Dict[str, Any],
    connectors: Dict[str, Any],
    triggers: Dict[str, Any],
    policies: Dict[str, Any],
    workflow_handlers: Dict[Tuple[str, str], Any],
) -> None:
    manager._plugins = list(plugins)
    manager._commands = dict(commands)
    manager._tools = dict(tools)
    manager._connectors = dict(connectors)
    manager._triggers = dict(triggers)
    manager._policies = dict(policies)
    manager._workflow_handlers = dict(workflow_handlers)


def reload(manager: Any) -> None:
    cache_by_cwd = getattr(manager, "_cache_by_cwd", None)
    if isinstance(cache_by_cwd, dict):
        cache_by_cwd.clear()
    if manager._compat_mode:
        manager._compat_reload()
        return
    manager._reference_reload()

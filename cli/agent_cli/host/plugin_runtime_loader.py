from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from cli.agent_cli.gateway_core.models import (
    ConnectorRegistration,
    PolicyRegistration,
    TriggerRegistration,
    connector_registration_from_mapping,
    policy_registration_from_mapping,
    trigger_registration_from_mapping,
)
from cli.agent_cli.host import plugin_runtime_loader_runtime as _runtime
from cli.agent_cli.host.plugin_sources import read_plugin_capability_declarations


def normalize_connector_registration(item: Any, *, plugin_name: str) -> Optional[ConnectorRegistration]:
    normalized = _runtime.normalize_mapping_registration(
        item,
        plugin_name=plugin_name,
        registration_type=ConnectorRegistration,
        from_mapping_fn=connector_registration_from_mapping,
    )
    return normalized if isinstance(normalized, ConnectorRegistration) else None


def normalize_trigger_registration(item: Any, *, plugin_name: str) -> Optional[TriggerRegistration]:
    normalized = _runtime.normalize_mapping_registration(
        item,
        plugin_name=plugin_name,
        registration_type=TriggerRegistration,
        from_mapping_fn=trigger_registration_from_mapping,
    )
    return normalized if isinstance(normalized, TriggerRegistration) else None


def normalize_policy_registration(item: Any, *, plugin_name: str) -> Optional[PolicyRegistration]:
    normalized = _runtime.normalize_mapping_registration(
        item,
        plugin_name=plugin_name,
        registration_type=PolicyRegistration,
        from_mapping_fn=policy_registration_from_mapping,
    )
    return normalized if isinstance(normalized, PolicyRegistration) else None


def normalize_workflow_handler_registration(
    item: Any,
    *,
    plugin_name: str,
    workflow_handler_type: type,
) -> Any | None:
    return _runtime.normalize_workflow_handler_registration(
        item,
        plugin_name=plugin_name,
        workflow_handler_type=workflow_handler_type,
    )


def call_runtime_builder(builder: Callable[..., Any], *, plugin_name: str) -> List[Any]:
    return _runtime.call_runtime_builder(builder, plugin_name=plugin_name)


def ensure_unique_registration(
    seen: Dict[str, Any],
    *,
    key_name: str,
    key_value: str,
    plugin_name: str,
    item: Any,
    conflict_error_type: type[Exception],
) -> None:
    _runtime.ensure_unique_registration(
        seen,
        key_name=key_name,
        key_value=key_value,
        plugin_name=plugin_name,
        item=item,
        conflict_error_type=conflict_error_type,
    )


def load_runtime_capabilities(
    *,
    plugin_name: str,
    plugin_dir: Path,
    manifest: Any,
    enabled: bool,
    config_name: str,
    source_kind: str,
    installed: bool,
    required_plugin_files: Tuple[str, ...],
    default_skill_roots_fn: Callable[[Path], List[Path]],
    load_mcp_servers_from_file_fn: Callable[[Path, Path], Dict[str, Dict[str, Any]]],
    load_apps_from_file_fn: Callable[[Path, Path], List[Dict[str, Any]]],
    ensure_host_plugin_package_fn: Callable[[str, Path], None],
    load_module_from_file_fn: Callable[[str, str, Path], Any],
    plugin_command_registry_type: type,
    plugin_tool_registry_type: type,
    loaded_plugin_type: type,
    default_mcp_config_file: str,
    default_app_config_file: str,
) -> Tuple[Any, Dict[str, Any]]:
    skill_roots = default_skill_roots_fn(plugin_dir)
    mcp_servers = load_mcp_servers_from_file_fn(plugin_dir, plugin_dir / default_mcp_config_file)
    apps = load_apps_from_file_fn(plugin_dir, plugin_dir / default_app_config_file)
    capability_declarations = list(read_plugin_capability_declarations(plugin_dir, plugin_name=plugin_name) or [])
    capability_declaration_errors: list[str] = []
    if not enabled:
        loaded = loaded_plugin_type(
            manifest=manifest,
            plugin_name=plugin_name,
            enabled=False,
            command_count=0,
            tool_count=0,
            connector_count=0,
            trigger_count=0,
            policy_count=0,
            workflow_count=0,
            provider_hooks={},
            runtime_hooks={},
            connector_registrations=[],
            trigger_registrations=[],
            policy_registrations=[],
            workflow_handlers=[],
            config_name=config_name,
            root=plugin_dir,
            skill_roots=skill_roots,
            mcp_servers=mcp_servers,
            apps=apps,
            installed=installed,
            source_kind=source_kind,
        )
        if hasattr(loaded, "capability_declarations"):
            loaded.capability_declarations = list(capability_declarations)
        if hasattr(loaded, "capability_declaration_errors"):
            loaded.capability_declaration_errors = list(capability_declaration_errors)
        setattr(loaded, "plugin_capability_declarations", capability_declarations)
        setattr(loaded, "plugin_capability_declaration_errors", capability_declaration_errors)
        return (
            loaded,
            {},
        )
    if not plugin_dir.exists() or not plugin_dir.is_dir():
        raise ValueError("path does not exist or is not a directory")
    provider_hooks: Any = {}
    runtime_hooks: Any = {}
    command_registry = plugin_command_registry_type(plugin_name)
    tool_registry = plugin_tool_registry_type(plugin_name)
    if all((plugin_dir / name).exists() for name in required_plugin_files):
        ensure_host_plugin_package_fn(plugin_name, plugin_dir)
        commands_module = load_module_from_file_fn(plugin_name, "commands", plugin_dir / "commands.py")
        tools_module = load_module_from_file_fn(plugin_name, "tools", plugin_dir / "tools.py")
        provider_module = load_module_from_file_fn(plugin_name, "provider", plugin_dir / "provider.py")
        runtime_module = load_module_from_file_fn(plugin_name, "runtime", plugin_dir / "runtime.py")
        if hasattr(commands_module, "register_commands"):
            commands_module.register_commands(command_registry)
        if hasattr(tools_module, "register_tools"):
            tools_module.register_tools(tool_registry)
        provider_hooks = provider_module.provider_hooks() if hasattr(provider_module, "provider_hooks") else {}
        runtime_hooks = runtime_module.runtime_hooks() if hasattr(runtime_module, "runtime_hooks") else {}
    loaded = loaded_plugin_type(
        manifest=manifest,
        plugin_name=plugin_name,
        enabled=enabled,
        command_count=len(command_registry.items),
        tool_count=len(tool_registry.items),
        connector_count=0,
        trigger_count=0,
        policy_count=0,
        workflow_count=0,
        provider_hooks=provider_hooks,
        runtime_hooks=runtime_hooks,
        connector_registrations=[],
        trigger_registrations=[],
        policy_registrations=[],
        workflow_handlers=[],
        config_name=config_name,
        root=plugin_dir,
        skill_roots=skill_roots,
        mcp_servers=mcp_servers,
        apps=apps,
        installed=installed,
        source_kind=source_kind,
    )
    if hasattr(loaded, "capability_declarations"):
        loaded.capability_declarations = list(capability_declarations)
    if hasattr(loaded, "capability_declaration_errors"):
        loaded.capability_declaration_errors = list(capability_declaration_errors)
    setattr(loaded, "plugin_capability_declarations", capability_declarations)
    setattr(loaded, "plugin_capability_declaration_errors", capability_declaration_errors)
    return (
        loaded,
        {
            "command_registry": command_registry,
            "tool_registry": tool_registry,
            "provider_hooks": provider_hooks,
            "runtime_hooks": runtime_hooks,
            "capability_declarations": capability_declarations,
            "capability_declaration_errors": capability_declaration_errors,
            "plugin_capability_declarations": capability_declarations,
        },
    )


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
    command_registry = runtime.get("command_registry")
    tool_registry = runtime.get("tool_registry")
    runtime_hooks = runtime.get("runtime_hooks")
    connector_items: List[ConnectorRegistration] = []
    trigger_items: List[TriggerRegistration] = []
    policy_items: List[PolicyRegistration] = []
    workflow_items: List[Any] = []
    connector_items = _runtime.collect_runtime_registration_items(
        runtime_hooks=runtime_hooks,
        loaded_plugin_name=loaded.plugin_name,
        builder_name="build_connector_registrations",
        normalize_fn=normalize_connector_registration,
        key_attr="connector_key",
        key_name="connector_key",
        seen=seen_connector_registrations,
        conflict_error_type=conflict_error_type,
    )
    trigger_items = _runtime.collect_runtime_registration_items(
        runtime_hooks=runtime_hooks,
        loaded_plugin_name=loaded.plugin_name,
        builder_name="build_trigger_registrations",
        normalize_fn=normalize_trigger_registration,
        key_attr="trigger_key",
        key_name="trigger_key",
        seen=seen_trigger_registrations,
        conflict_error_type=conflict_error_type,
    )
    policy_items = _runtime.collect_runtime_registration_items(
        runtime_hooks=runtime_hooks,
        loaded_plugin_name=loaded.plugin_name,
        builder_name="build_policy_registrations",
        normalize_fn=normalize_policy_registration,
        key_attr="policy_key",
        key_name="policy_key",
        seen=seen_policy_registrations,
        conflict_error_type=conflict_error_type,
    )
    workflow_items = _runtime.collect_workflow_handler_items(
        runtime_hooks=runtime_hooks,
        loaded_plugin_name=loaded.plugin_name,
        workflow_handler_type=workflow_handler_type,
        seen_workflow_handlers=seen_workflow_handlers,
        conflict_error_type=conflict_error_type,
    )
    loaded.connector_registrations = connector_items
    loaded.trigger_registrations = trigger_items
    loaded.policy_registrations = policy_items
    loaded.workflow_handlers = workflow_items
    loaded.connector_count = len(connector_items)
    loaded.trigger_count = len(trigger_items)
    loaded.policy_count = len(policy_items)
    loaded.workflow_count = len(workflow_items)
    plugins.append(loaded)
    if not loaded.is_active():
        return
    for item in (command_registry.items if command_registry is not None else []):
        commands[item.name] = item
    for item in (tool_registry.items if tool_registry is not None else []):
        tools[item.name] = item
    for item in connector_items:
        connectors[item.connector_key] = item
    for item in trigger_items:
        triggers[item.trigger_key] = item
    for item in policy_items:
        policies[item.policy_key] = item
    for item in workflow_items:
        workflow_handlers[(item.plugin_name, item.workflow_name)] = item

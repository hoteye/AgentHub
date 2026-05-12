from __future__ import annotations

from typing import Any, Dict, List, Tuple


def default_external_manifest(*, plugin_manifest_type: type, plugin_name: str) -> Any:
    return plugin_manifest_type(
        name=plugin_name,
        version="0.0.0",
        description="",
        distribution="external",
    )


def append_unloaded_plugin(
    plugins: List[Any],
    *,
    loaded_plugin_type: type,
    plugin_manifest_type: type,
    plugin_name: str,
    manifest: Any | None,
    enabled: bool,
    config_name: str,
    root: Any,
    installed: bool,
    source_kind: str,
) -> None:
    plugins.append(
        loaded_plugin_type(
            manifest=manifest or default_external_manifest(plugin_manifest_type=plugin_manifest_type, plugin_name=plugin_name),
            plugin_name=plugin_name,
            enabled=enabled,
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
            root=root,
            installed=installed,
            source_kind=source_kind,
        )
    )


def append_error_plugin(
    plugins: List[Any],
    *,
    loaded_plugin_type: type,
    plugin_manifest_type: type,
    plugin_name: str,
    manifest: Any | None,
    enabled: bool,
    config_name: str,
    root: Any,
    installed: bool,
    source_kind: str,
    error: str,
) -> None:
    plugins.append(
        loaded_plugin_type(
            manifest=manifest or default_external_manifest(plugin_manifest_type=plugin_manifest_type, plugin_name=plugin_name),
            plugin_name=plugin_name,
            enabled=enabled,
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
            root=root,
            error=error,
            installed=installed,
            source_kind=source_kind,
        )
    )


def plugin_registry_state(
    *,
    plugins: List[Any],
    commands: Dict[str, Any],
    tools: Dict[str, Any],
    connectors: Dict[str, Any],
    triggers: Dict[str, Any],
    policies: Dict[str, Any],
    workflow_handlers: Dict[Tuple[str, str], Any],
) -> Dict[str, Any]:
    return {
        "plugins": plugins,
        "commands": commands,
        "tools": tools,
        "connectors": connectors,
        "triggers": triggers,
        "policies": policies,
        "workflow_handlers": workflow_handlers,
    }

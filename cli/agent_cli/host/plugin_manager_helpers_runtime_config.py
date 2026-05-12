from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from cli.agent_cli.host import plugin_config_runtime as _plugin_config_runtime
from cli.agent_cli.host import plugin_index_runtime as _plugin_index_runtime
from cli.agent_cli.host import plugin_types as _plugin_types
from cli.agent_cli.host.plugin_store_runtime import (
    DEFAULT_PLUGIN_SECTION_MARKETPLACE,
    PluginStoreError,
)
from cli.agent_cli.host.plugin_sources import (
    read_reference_manifest as _read_reference_manifest,
    read_reference_manifest_as_plugin_manifest as _read_reference_manifest_as_plugin_manifest,
    read_legacy_compat_manifest_metadata as _read_legacy_compat_manifest_metadata,
)

PluginId = _plugin_types.PluginId


def validate_plugin_dir(candidate_dir: Path, required_plugin_files_fn: Callable[[], Tuple[str, ...]]) -> Optional[str]:
    return _plugin_index_runtime.validate_plugin_dir(
        candidate_dir,
        read_reference_manifest_fn=_read_reference_manifest,
        required_plugin_files_fn=required_plugin_files_fn,
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
    manager: Any,
    configured_plugins: Dict[str, Dict[str, Any]],
) -> List[Any]:
    return _plugin_config_runtime.discover_bundled_sources(
        bundled_plugin_root=manager.bundled_plugin_root,
        configured_plugins=configured_plugins,
        read_legacy_compat_manifest_metadata_fn=_read_legacy_compat_manifest_metadata,
        bundled_plugin_key_fn=bundled_plugin_key,
        plugin_enabled_fn=plugin_enabled,
        plugin_source_type=_plugin_types._PluginSource,
    )


def configured_external_sources(
    manager: Any,
    configured_plugins: Dict[str, Dict[str, Any]],
) -> List[Any]:
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

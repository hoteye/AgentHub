from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List


def config_home_paths(
    *,
    config_path: Path,
    reference_home: Path,
    default_reference_home: Callable[[], Path],
    legacy_compat_home: Path,
) -> List[Path]:
    paths = [config_path]
    legacy_config_path = legacy_compat_home / "config.toml"
    if reference_home == default_reference_home() and legacy_config_path != config_path:
        paths.append(legacy_config_path)
    return paths


def merged_workspace_config(
    *,
    cwd: Path,
    home_config_paths: List[Path],
    read_merged_project_toml_fn: Callable[..., tuple[Dict[str, Any], Any]],
) -> Dict[str, Any]:
    merged, _ = read_merged_project_toml_fn(cwd=cwd, home_config_paths=home_config_paths)
    return merged


def workspace_trust_level_from_paths(
    *,
    cwd: Path,
    home_config_paths: List[Path],
    workspace_trust_level_fn: Callable[..., str],
) -> str:
    return workspace_trust_level_fn(cwd, home_config_paths=home_config_paths)


def plugins_feature_enabled_from_config(config: Dict[str, Any]) -> bool:
    features = config.get("features")
    if not isinstance(features, dict):
        return True
    value = features.get("plugins")
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def configured_plugins_from_config(config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    raw = config.get("plugins")
    if not isinstance(raw, dict):
        return {}
    result: Dict[str, Dict[str, Any]] = {}
    for key, value in raw.items():
        result[str(key)] = dict(value) if isinstance(value, dict) else {}
    return result


def plugin_enabled(value: Dict[str, Any], default: bool) -> bool:
    if "enabled" not in value:
        return default
    enabled = value.get("enabled")
    if isinstance(enabled, bool):
        return enabled
    return str(enabled or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def bundled_plugin_key(plugin_name: str, *, default_plugin_section_marketplace: str) -> str:
    return f"{plugin_name}@{default_plugin_section_marketplace}"


def discover_bundled_sources(
    *,
    bundled_plugin_root: Path,
    configured_plugins: Dict[str, Dict[str, Any]],
    read_legacy_compat_manifest_metadata_fn: Callable[[Path], Any],
    bundled_plugin_key_fn: Callable[[str], str],
    plugin_enabled_fn: Callable[[Dict[str, Any], bool], bool],
    plugin_source_type: Any,
) -> List[Any]:
    if not bundled_plugin_root.exists():
        return []
    sources: List[Any] = []
    for plugin_dir in sorted(path for path in bundled_plugin_root.iterdir() if path.is_dir()):
        manifest = read_legacy_compat_manifest_metadata_fn(plugin_dir)
        if manifest is None:
            continue
        config_name = bundled_plugin_key_fn(manifest.name)
        enabled = plugin_enabled_fn(configured_plugins.get(config_name) or {}, manifest.enabled_by_default)
        sources.append(
            plugin_source_type(
                config_name=config_name,
                plugin_name=manifest.name,
                root=plugin_dir,
                enabled=enabled,
                manifest=manifest,
                source_kind="bundled",
                installed=False,
            )
        )
    return sources


def configured_external_sources(
    *,
    configured_plugins: Dict[str, Dict[str, Any]],
    bundled_sources: List[Any],
    plugin_enabled_fn: Callable[[Dict[str, Any], bool], bool],
    parse_plugin_id_fn: Callable[[str], Any],
    plugin_store: Any,
    read_reference_manifest_as_plugin_manifest_fn: Callable[[Path], Any],
    read_legacy_compat_manifest_metadata_fn: Callable[[Path], Any],
    plugin_source_type: Any,
    plugin_store_error_type: Any,
) -> List[Any]:
    bundled_keys = {item.config_name for item in bundled_sources}
    sources: List[Any] = []
    for config_name, payload in sorted(configured_plugins.items()):
        if config_name in bundled_keys:
            continue
        enabled = plugin_enabled_fn(payload, False)
        try:
            plugin_id = parse_plugin_id_fn(config_name)
        except plugin_store_error_type:
            sources.append(
                plugin_source_type(
                    config_name=config_name,
                    plugin_name=config_name,
                    root=plugin_store.root,
                    enabled=enabled,
                    manifest=None,
                    source_kind="configured",
                    installed=True,
                )
            )
            continue
        root = plugin_store.plugin_root(plugin_id)
        manifest = read_reference_manifest_as_plugin_manifest_fn(root) or read_legacy_compat_manifest_metadata_fn(root)
        plugin_name = manifest.name if manifest is not None else plugin_id.plugin_name
        sources.append(
            plugin_source_type(
                config_name=config_name,
                plugin_name=plugin_name,
                root=root,
                enabled=enabled,
                manifest=manifest,
                source_kind="installed",
                installed=True,
            )
        )
    return sources

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from cli.agent_cli.host.plugin_manifest import PluginManifest
from cli.agent_cli.host import plugin_sources_runtime as _plugin_sources_runtime

_REFERENCE_PLUGIN_MANIFEST_PATH = Path(".agent_cli_legacy-plugin") / "plugin.json"
_DEFAULT_SKILLS_DIR_NAME = "skills"


def _safe_resolve(path: Path) -> Path:
    return _plugin_sources_runtime.safe_resolve(path)


def read_reference_manifest(root: Path) -> Optional[Dict[str, Any]]:
    return _plugin_sources_runtime.read_json_dict(root / _REFERENCE_PLUGIN_MANIFEST_PATH)


def _normalize_manifest(item: Any, *, plugin_name: str) -> PluginManifest:
    return _plugin_sources_runtime.normalize_manifest(item, plugin_name=plugin_name)


def read_reference_manifest_as_plugin_manifest(root: Path) -> Optional[PluginManifest]:
    payload = read_reference_manifest(root)
    if payload is None:
        return None
    return _plugin_sources_runtime.reference_manifest_as_plugin_manifest(payload, root=root)


def read_legacy_compat_manifest_metadata(root: Path) -> Optional[PluginManifest]:
    return _plugin_sources_runtime.read_legacy_compat_manifest_metadata(root)


def read_plugin_capability_declarations(root: Path, *, plugin_name: str | None = None) -> List[Dict[str, Any]]:
    return _plugin_sources_runtime.read_plugin_capability_declarations(root, plugin_name=plugin_name)


def default_skill_roots(plugin_root: Path) -> List[Path]:
    skills_dir = plugin_root / _DEFAULT_SKILLS_DIR_NAME
    if skills_dir.is_dir():
        return [_safe_resolve(skills_dir)]
    return []


def _normalize_plugin_mcp_value(plugin_root: Path, value: Any) -> Dict[str, Any]:
    return _plugin_sources_runtime.normalize_plugin_mcp_value(plugin_root, value)


def load_mcp_servers_from_file(plugin_root: Path, path: Path) -> Dict[str, Dict[str, Any]]:
    payload = _plugin_sources_runtime.read_json_dict(path)
    if payload is None:
        return {}
    return _plugin_sources_runtime.load_mcp_servers(plugin_root, payload)


def load_apps_from_file(plugin_root: Path, path: Path) -> List[Dict[str, Any]]:
    del plugin_root
    payload = _plugin_sources_runtime.read_json_dict(path)
    if payload is None:
        return []
    return _plugin_sources_runtime.load_apps(payload)

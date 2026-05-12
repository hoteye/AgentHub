from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict

from cli.agent_cli.host import plugin_store_runtime_helpers as _plugin_store_runtime_helpers
from cli.agent_cli.host.plugin_sources import (
    read_reference_manifest as _read_reference_manifest,
    read_legacy_compat_manifest_metadata as _read_legacy_compat_manifest_metadata,
)
from cli.agent_cli.host.plugin_types import PluginId, PluginStoreError
from cli.agent_cli.runtime_paths import project_local_data_dir, runtime_project_root


LOCAL_CONFIG_DIRNAME = ".agent_cli"
LEGACY_LOCAL_CONFIG_DIRNAME = ".agent_cli_legacy"
AGENT_CLI_HOME = Path(os.environ.get("AGENT_CLI_HOME") or (Path.home() / LOCAL_CONFIG_DIRNAME))
LEGACY_COMPAT_HOME = Path.home() / LEGACY_LOCAL_CONFIG_DIRNAME
DEFAULT_MARKETPLACE_NAME = "debug"
DEFAULT_PLUGIN_VERSION = "local"
DEFAULT_PLUGIN_SECTION_MARKETPLACE = "bundled"
DEFAULT_MCP_CONFIG_FILE = ".mcp.json"
DEFAULT_APP_CONFIG_FILE = ".app.json"
PLUGIN_CACHE_RELATIVE_DIR = Path("plugins") / "cache"


def _safe_resolve(path: Path) -> Path:
    return _plugin_store_runtime_helpers.safe_resolve(path)


def _find_project_root() -> Path:
    env_root = runtime_project_root()
    if (env_root / "plugins").exists():
        return env_root
    start = Path(__file__).resolve().parent
    for candidate in (start, *start.parents):
        if (candidate / "plugins").exists() and (
            (candidate / "document_tools").exists()
            or (candidate / "internal_policy_docs").exists()
            or (candidate / "tools").exists()
        ):
            return candidate
    return Path(__file__).resolve().parents[3]


def default_plugin_root() -> Path:
    return _find_project_root() / "plugins"


def default_plugin_state_path(*, project_root: Path | None = None) -> Path:
    return project_local_data_dir(root=project_root or _find_project_root()) / "plugin_state.json"


def default_reference_home() -> Path:
    if AGENT_CLI_HOME.exists() or not LEGACY_COMPAT_HOME.exists():
        return _safe_resolve(AGENT_CLI_HOME)
    return _safe_resolve(LEGACY_COMPAT_HOME)


def plugin_namespace_for_skill_path(path: str | Path) -> str | None:
    return _plugin_store_runtime_helpers.plugin_namespace_for_skill_path(
        path,
        read_reference_manifest_fn=_read_reference_manifest,
        read_legacy_compat_manifest_metadata_fn=_read_legacy_compat_manifest_metadata,
        safe_resolve_fn=_safe_resolve,
    )


class PluginRegistrationConflictError(ValueError):
    """Raised when plugin runtime registration keys collide."""


class PluginStore:
    def __init__(self, reference_home: Path) -> None:
        self.reference_home = _safe_resolve(reference_home)
        self.root = self.reference_home / PLUGIN_CACHE_RELATIVE_DIR

    def plugin_root(self, plugin_id: PluginId, plugin_version: str = DEFAULT_PLUGIN_VERSION) -> Path:
        return self.root / plugin_id.marketplace_name / plugin_id.plugin_name / plugin_version

    def install(
        self,
        source_path: Path,
        *,
        marketplace_name: str | None = None,
        replace: bool = False,
    ) -> Dict[str, Any]:
        if not source_path.is_dir():
            raise PluginStoreError(f"plugin source path is not a directory: {source_path}")
        plugin_name, plugin_version = _plugin_metadata_for_source(source_path)
        marketplace = str(marketplace_name or DEFAULT_MARKETPLACE_NAME).strip() or DEFAULT_MARKETPLACE_NAME
        if not re.fullmatch(r"[A-Za-z0-9_-]+", plugin_name):
            raise PluginStoreError(f"invalid plugin name: {plugin_name}")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", marketplace):
            raise PluginStoreError(f"invalid marketplace name: {marketplace}")
        plugin_id = PluginId(plugin_name=plugin_name, marketplace_name=marketplace)
        target = self.plugin_root(plugin_id, plugin_version=plugin_version)
        target.parent.mkdir(parents=True, exist_ok=True)
        replaced = target.exists()
        if replaced and not bool(replace):
            raise PluginStoreError(f"plugin already installed: {plugin_id.as_key()}")
        if replaced:
            shutil.rmtree(target)
        shutil.copytree(source_path, target)
        return {
            "plugin_id": plugin_id,
            "plugin_version": plugin_version,
            "installed_path": target,
            "replaced": replaced,
        }


def _plugin_name_for_source(source_path: Path) -> str:
    return _plugin_store_runtime_helpers.plugin_name_for_source(
        source_path,
        read_reference_manifest_fn=_read_reference_manifest,
        read_legacy_compat_manifest_metadata_fn=_read_legacy_compat_manifest_metadata,
        plugin_store_error_type=PluginStoreError,
    )


def _plugin_metadata_for_source(source_path: Path) -> tuple[str, str]:
    reference_manifest = _read_reference_manifest(source_path)
    if reference_manifest is not None:
        plugin_name = str(reference_manifest.get("name") or "").strip() or source_path.name
        plugin_version = str(reference_manifest.get("version") or "").strip() or DEFAULT_PLUGIN_VERSION
        return plugin_name, plugin_version
    manifest = _read_legacy_compat_manifest_metadata(source_path)
    if manifest is not None:
        plugin_version = str(getattr(manifest, "version", "") or "").strip() or DEFAULT_PLUGIN_VERSION
        return manifest.name, plugin_version
    raise PluginStoreError(f"missing or invalid plugin manifest: {source_path}")


__all__ = [
    "AGENT_CLI_HOME",
    "DEFAULT_APP_CONFIG_FILE",
    "DEFAULT_MARKETPLACE_NAME",
    "DEFAULT_MCP_CONFIG_FILE",
    "DEFAULT_PLUGIN_SECTION_MARKETPLACE",
    "DEFAULT_PLUGIN_VERSION",
    "LEGACY_COMPAT_HOME",
    "LOCAL_CONFIG_DIRNAME",
    "PLUGIN_CACHE_RELATIVE_DIR",
    "PluginRegistrationConflictError",
    "PluginStore",
    "default_reference_home",
    "default_plugin_root",
    "default_plugin_state_path",
    "plugin_namespace_for_skill_path",
    "_find_project_root",
]

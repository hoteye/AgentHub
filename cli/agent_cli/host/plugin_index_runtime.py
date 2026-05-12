from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple


def required_plugin_files() -> Tuple[str, ...]:
    return ("manifest.py", "commands.py", "tools.py", "provider.py", "runtime.py")


def validate_plugin_dir(
    candidate_dir: Path,
    *,
    read_reference_manifest_fn: Callable[[Path], Any],
    required_plugin_files_fn: Callable[[], Sequence[str]] = required_plugin_files,
) -> Optional[str]:
    if not candidate_dir.exists() or not candidate_dir.is_dir():
        return "plugin_dir_not_found"
    if read_reference_manifest_fn(candidate_dir) is not None:
        return None
    for name in required_plugin_files_fn():
        if not (candidate_dir / name).exists():
            return f"missing_required_file:{name}"
    return None


def extract_source_dir(
    source_path: str,
    *,
    validate_plugin_dir_fn: Callable[[Path], Optional[str]],
) -> Tuple[Optional[Path], Optional[Path], str, Dict[str, Any]]:
    source = Path(str(source_path or "").strip())
    if not str(source):
        return None, None, "dir", {"ok": False, "reason": "path_required"}
    if not source.exists():
        return None, None, "dir", {"ok": False, "reason": "path_not_found", "path": str(source)}
    staging_dir: Optional[Path] = None
    candidate_dir: Optional[Path] = None
    source_kind = "dir"
    if source.is_dir():
        candidate_dir = source
    else:
        source_kind = "zip"
        if source.suffix.lower() != ".zip":
            return None, None, source_kind, {"ok": False, "reason": "unsupported_source_type", "path": str(source)}
        staging_dir = Path(tempfile.mkdtemp(prefix="plugin_install_"))
        with zipfile.ZipFile(source, "r") as zf:
            zf.extractall(staging_dir)
        top_level_dirs = [item for item in staging_dir.iterdir() if item.is_dir()]
        if len(top_level_dirs) == 1:
            candidate_dir = top_level_dirs[0]
        else:
            return staging_dir, None, source_kind, {"ok": False, "reason": "zip_structure_invalid", "path": str(source)}
    if candidate_dir is None:
        return staging_dir, None, source_kind, {"ok": False, "reason": "candidate_not_found", "path": str(source)}
    validation_error = validate_plugin_dir_fn(candidate_dir)
    if validation_error is not None:
        return staging_dir, None, source_kind, {"ok": False, "reason": validation_error, "path": str(candidate_dir)}
    return staging_dir, candidate_dir, source_kind, {}


def resolve_plugin(plugins: Sequence[Any], plugin_name: str) -> Optional[Any]:
    requested = str(plugin_name or "").strip()
    if not requested:
        return None
    exact = next((item for item in plugins if item.plugin_name == requested or item.config_name == requested), None)
    if exact is not None:
        return exact
    matches = [item for item in plugins if item.plugin_name == requested]
    if len(matches) == 1:
        return matches[0]
    return None


def project_plugins(plugins: Sequence[Any]) -> List[Dict[str, Any]]:
    return [
        {
            "plugin_id": plugin.plugin_name if plugin.source_kind == "bundled" else (plugin.config_name or plugin.plugin_name),
            "config_name": plugin.config_name or plugin.plugin_name,
            "name": plugin.plugin_name,
            "version": plugin.manifest.version,
            "description": plugin.manifest.description,
            "api_version": plugin.manifest.api_version,
            "plugin_kind": plugin.manifest.plugin_kind,
            "distribution": plugin.manifest.distribution,
            "min_host_version": plugin.manifest.min_host_version,
            "enabled": plugin.enabled,
            "commercial": plugin.manifest.commercial,
            "dependencies": list(plugin.manifest.dependencies),
            "command_count": plugin.command_count,
            "tool_count": plugin.tool_count,
            "connector_count": plugin.connector_count,
            "trigger_count": plugin.trigger_count,
            "policy_count": plugin.policy_count,
            "workflow_count": plugin.workflow_count,
            "root": str(plugin.root),
            "error": plugin.error,
            "skill_root_count": len(plugin.skill_roots),
            "app_count": len(plugin.apps),
            "mcp_server_count": len(plugin.mcp_servers),
        }
        for plugin in plugins
    ]

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from cli.agent_cli import provider as provider_module
from cli.agent_cli.workspace_context import find_project_root, project_root_markers


def _safe_resolve(path: str | Path | None) -> Path:
    candidate = Path(path or ".").expanduser()
    try:
        return candidate.resolve()
    except OSError:
        return candidate


def _fallback_git_project_root(path: Path) -> Path:
    for ancestor in [path, *path.parents]:
        if (ancestor / ".git").exists():
            return ancestor
    return path


def resolve_user_provider_config_path() -> Path:
    return Path(provider_module.AGENT_CLI_CONFIG_TOML)


def resolve_user_provider_auth_path() -> Path:
    return Path(provider_module.AGENT_CLI_AUTH_JSON)


def resolve_private_provider_auth_write_path() -> Path:
    return resolve_user_provider_auth_path()


def resolve_private_provider_auth_read_paths() -> list[Path]:
    paths: list[Path] = []
    legacy_path = Path(provider_module.LEGACY_COMPAT_AUTH_JSON)
    if not str(os.environ.get("AGENT_CLI_HOME") or "").strip():
        paths.append(legacy_path)
    paths.append(resolve_user_provider_auth_path())
    unique: list[Path] = []
    for path in paths:
        if path not in unique:
            unique.append(path)
    return unique


def load_user_provider_selection() -> dict[str, str]:
    reader = getattr(provider_module, "_read_user_model_selection_toml", None)
    if not callable(reader):
        return {}
    try:
        payload = dict(reader() or {})
    except Exception:
        return {}
    selection: dict[str, str] = {}
    for key in ("model_provider", "model", "model_reasoning_effort"):
        value: Any = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            selection[key] = text
    return selection


def load_provider_auth_payload(*, path: Path | None = None) -> dict[str, Any]:
    target = Path(path or resolve_user_provider_auth_path())
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def write_provider_auth_payload(payload: dict[str, Any], *, path: Path | None = None) -> Path:
    target = Path(path or resolve_user_provider_auth_path())
    target.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(dict(payload or {}), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    target.write_text(rendered, encoding="utf-8")
    return target


def persist_provider_auth_value(*, key: str, value: Any, path: Path | None = None) -> Path:
    target = Path(path or resolve_user_provider_auth_path())
    payload = load_provider_auth_payload(path=target)
    payload[str(key or "").strip()] = str(value or "").strip()
    return write_provider_auth_payload(payload, path=target)


def resolve_effective_home_provider_config_path(
    *,
    cwd: str | Path | None = None,
) -> Path:
    resolved_cwd = _safe_resolve(cwd)
    try:
        resolution = provider_module.resolve_provider_paths(
            cwd=resolved_cwd,
            strict_isolation=True,
        )
    except Exception:
        return resolve_user_provider_config_path()
    return Path(getattr(resolution, "config_path", resolve_user_provider_config_path()))


def resolve_project_provider_config_write_path(
    *,
    cwd: str | Path | None = None,
) -> Path:
    has_explicit_cwd = cwd is not None and str(cwd).strip() != ""
    resolved_cwd = _safe_resolve(cwd)
    home_config_path = resolve_effective_home_provider_config_path(cwd=resolved_cwd)
    try:
        resolution = provider_module.resolve_provider_paths(cwd=resolved_cwd)
    except Exception:
        resolution = None
    if resolution is not None and bool(getattr(resolution, "used_project_local", False)):
        config_path = Path(resolution.config_path)
        if not has_explicit_cwd or config_path != home_config_path:
            return config_path

    try:
        markers = project_root_markers(resolved_cwd)
        project_root = _safe_resolve(find_project_root(resolved_cwd, markers or [".git"]))
    except Exception:
        project_root = resolved_cwd
    if project_root == resolved_cwd and not (resolved_cwd / ".git").exists():
        project_root = _safe_resolve(_fallback_git_project_root(resolved_cwd))
    return project_root / ".agent_cli" / "config.toml"


__all__ = [
    "load_provider_auth_payload",
    "load_user_provider_selection",
    "persist_provider_auth_value",
    "resolve_private_provider_auth_read_paths",
    "resolve_private_provider_auth_write_path",
    "resolve_user_provider_auth_path",
    "resolve_user_provider_config_path",
    "resolve_effective_home_provider_config_path",
    "resolve_project_provider_config_write_path",
    "write_provider_auth_payload",
]

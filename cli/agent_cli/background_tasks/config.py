from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Sequence

from cli.agent_cli.provider_persistence_paths_runtime import (
    resolve_effective_home_provider_config_path,
)
from cli.agent_cli.workspace_context import (
    AGENT_CLI_HOME,
    LEGACY_COMPAT_HOME,
    merge_nested_mappings,
    read_merged_project_toml,
)


@dataclass(frozen=True)
class HueyConfig:
    backend: str = "sqlite"
    path: Path = Path("cli/.local/state/huey/agenthub_huey.db")
    results_dir: Path = Path("cli/.local/state/huey/results")
    worker_count: int = 1
    immediate: bool = False


@dataclass(frozen=True)
class BackgroundTasksConfig:
    enabled: bool = False
    provider: str = "huey"
    huey: HueyConfig = HueyConfig()
    source_paths: tuple[Path, ...] = ()


def _safe_resolve(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser()


def _read_toml_mapping(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("rb") as handle:
            payload = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _as_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _as_path(value: Any, default: Path, *, cwd: Path) -> Path:
    raw = str(value or "").strip()
    if not raw:
        candidate = default
    else:
        candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        return _safe_resolve(candidate)
    return _safe_resolve(cwd / candidate)


def _normalize_explicit_paths(paths: Sequence[Path] | None) -> list[Path]:
    normalized: list[Path] = []
    for raw_path in paths or ():
        candidate = _safe_resolve(Path(raw_path))
        if not candidate.exists() or candidate in normalized:
            continue
        normalized.append(candidate)
    return normalized


def _default_home_config_candidates(*, cwd: Path) -> list[Path]:
    return _normalize_explicit_paths(
        (
            LEGACY_COMPAT_HOME / "config.toml",
            AGENT_CLI_HOME / "config.toml",
            resolve_effective_home_provider_config_path(cwd=cwd),
        )
    )


def _merge_config_maps(
    cwd: Path,
    *,
    home_config_paths: Sequence[Path] | None = None,
    project_config_path: str | Path | None = None,
    home_config_path: str | Path | None = None,
) -> tuple[Dict[str, Any], tuple[Path, ...]]:
    explicit_home_paths = _normalize_explicit_paths(
        home_config_paths
        if home_config_paths is not None
        else [Path(home_config_path)]
        if home_config_path is not None
        else _default_home_config_candidates(cwd=cwd)
    )
    if project_config_path is None:
        merged, discovered_paths = read_merged_project_toml(cwd=cwd, home_config_paths=explicit_home_paths)
        return merged, tuple(discovered_paths)

    merged: Dict[str, Any] = {}
    source_paths: list[Path] = []
    for candidate in explicit_home_paths:
        merged = merge_nested_mappings(merged, _read_toml_mapping(candidate))
        source_paths.append(candidate)

    project_candidate = _safe_resolve(Path(project_config_path))
    if project_candidate.exists():
        merged = merge_nested_mappings(merged, _read_toml_mapping(project_candidate))
        source_paths.append(project_candidate)
    return merged, tuple(source_paths)


def read_background_tasks_config(
    *,
    cwd: str | Path | None = None,
    project_root: str | Path | None = None,
    home_config_paths: Sequence[Path] | None = None,
    project_config_path: str | Path | None = None,
    home_config_path: str | Path | None = None,
) -> BackgroundTasksConfig:
    base_cwd = cwd if cwd is not None else project_root if project_root is not None else os.getcwd()
    resolved_cwd = _safe_resolve(Path(base_cwd))
    config, source_paths = _merge_config_maps(
        resolved_cwd,
        home_config_paths=home_config_paths,
        project_config_path=project_config_path,
        home_config_path=home_config_path,
    )
    section = config.get("background_tasks")
    block = section if isinstance(section, dict) else {}
    huey_section = block.get("huey")
    huey_block = huey_section if isinstance(huey_section, dict) else {}

    default_huey = HueyConfig()
    huey_config = HueyConfig(
        backend=str(huey_block.get("backend") or default_huey.backend).strip() or default_huey.backend,
        path=_as_path(huey_block.get("path"), default_huey.path, cwd=resolved_cwd),
        results_dir=_as_path(huey_block.get("results_dir"), default_huey.results_dir, cwd=resolved_cwd),
        worker_count=_as_int(huey_block.get("worker_count"), default_huey.worker_count),
        immediate=_as_bool(huey_block.get("immediate"), default_huey.immediate),
    )
    return BackgroundTasksConfig(
        enabled=_as_bool(block.get("enabled"), False),
        provider=str(block.get("provider") or "huey").strip() or "huey",
        huey=huey_config,
        source_paths=source_paths,
    )


load_background_tasks_config = read_background_tasks_config
resolve_background_tasks_config = read_background_tasks_config

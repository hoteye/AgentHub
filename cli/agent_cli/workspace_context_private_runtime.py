from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from cli.agent_cli import workspace_context_config_runtime as workspace_context_config_runtime_service
from cli.agent_cli import workspace_context_prompt_runtime as workspace_context_prompt_runtime_service
from cli.agent_cli import workspace_context_projection_runtime as workspace_context_projection_runtime_helpers


def merge_nested_mappings(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, dict) and isinstance(value, dict):
            merged[key] = merge_nested_mappings(existing, value)
        else:
            merged[key] = value
    return merged


def safe_resolve(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser()


def read_toml(path: Path) -> Dict[str, Any]:
    return workspace_context_config_runtime_service.read_toml(path)


def read_json(path: Path) -> Dict[str, Any]:
    return workspace_context_config_runtime_service.read_json(path)


def config_list(config: Dict[str, Any], key: str) -> Optional[List[str]]:
    return workspace_context_config_runtime_service.config_list(config, key)


def parse_skill_file(
    path: Path,
    *,
    safe_resolve_fn: Callable[[Path], Path],
    skill_factory: Callable[..., Any],
) -> Optional[Any]:
    parsed = workspace_context_prompt_runtime_service.parse_skill_file(
        path,
        safe_resolve=safe_resolve_fn,
        skill_factory=skill_factory,
    )
    return parsed if isinstance(parsed, skill_factory) else None


def repo_skill_roots(
    cwd: Path,
    project_root: Path,
    markers: List[str],
    *,
    dirs_between_project_root_and_cwd: Callable[[str | Path, str | Path], List[Path]],
    safe_resolve_fn: Callable[[Path], Path],
    agents_dirname: str,
    legacy_repo_config_dirname: str,
    skills_dirname: str,
) -> List[Path]:
    return workspace_context_prompt_runtime_service.repo_skill_roots(
        cwd,
        project_root,
        markers,
        dirs_between_project_root_and_cwd=dirs_between_project_root_and_cwd,
        safe_resolve=safe_resolve_fn,
        agents_dirname=agents_dirname,
        legacy_repo_config_dirname=legacy_repo_config_dirname,
        skills_dirname=skills_dirname,
    )


def text_digest(value: str) -> str:
    return workspace_context_projection_runtime_helpers.text_digest(value)


def json_digest(value: Dict[str, Any]) -> str:
    return workspace_context_projection_runtime_helpers.json_digest(value)


def path_signature(path: Path, *, safe_resolve_fn: Callable[[Path], Path]) -> Dict[str, Any]:
    return workspace_context_projection_runtime_helpers.path_signature(path, safe_resolve=safe_resolve_fn)


def workspace_instructions_excerpt(
    current: Dict[str, Any],
    *,
    max_chars: int,
) -> str:
    return workspace_context_projection_runtime_helpers.workspace_instructions_excerpt(
        current,
        max_chars=max_chars,
    )

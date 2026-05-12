from __future__ import annotations

import fnmatch
import json
import tomllib
from pathlib import Path
from typing import Any, Callable, Sequence

from cli.agent_cli import workspace_context_config_runtime_helpers as workspace_context_config_runtime_helpers_service


def read_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("rb") as handle:
            payload = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def workspace_config_candidates(
    cwd: Path,
    *,
    safe_resolve: Callable[[Path], Path],
    project_local_data_dir_candidates: Sequence[str],
    home_config_paths: Sequence[Path],
) -> list[Path]:
    candidates: list[Path] = []
    for current in list(reversed(list(cwd.parents))) + [cwd]:
        for dirname in project_local_data_dir_candidates:
            candidate = current / dirname / "config.toml"
            if candidate.exists():
                candidates.append(safe_resolve(candidate))
                break
    for candidate in home_config_paths:
        if candidate.exists():
            candidates.insert(0, safe_resolve(candidate))
    return candidates


def existing_home_config_paths(
    *,
    safe_resolve: Callable[[Path], Path],
    home_config_paths: Sequence[Path],
) -> list[Path]:
    for path in home_config_paths:
        candidate = Path(path)
        if candidate.exists():
            return [safe_resolve(candidate)]
    return []


def merged_home_workspace_config(
    *,
    merge_nested_mappings: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    existing_home_config_paths_fn: Callable[..., list[Path]],
    read_toml_fn: Callable[[Path], dict[str, Any]],
    home_config_paths: Sequence[Path],
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for path in existing_home_config_paths_fn(home_config_paths=home_config_paths):
        merged = merge_nested_mappings(merged, read_toml_fn(path))
    return merged


def config_list(config: dict[str, Any], key: str) -> list[str] | None:
    value = config.get(key)
    if value is None or not isinstance(value, list):
        return None
    return [str(item or "").strip() for item in value if str(item or "").strip()]


def merged_workspace_config(
    cwd: str | Path,
    *,
    safe_resolve: Callable[[Path], Path],
    workspace_config_candidates_fn: Callable[..., list[Path]],
    merge_nested_mappings: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    read_toml_fn: Callable[[Path], dict[str, Any]],
    home_config_paths: Sequence[Path],
) -> dict[str, Any]:
    resolved_cwd = safe_resolve(Path(cwd))
    merged: dict[str, Any] = {}
    for path in workspace_config_candidates_fn(resolved_cwd, home_config_paths=home_config_paths):
        merged = merge_nested_mappings(merged, read_toml_fn(path))
    return merged


def _extract_frontmatter(text: str) -> str | None:
    return workspace_context_config_runtime_helpers_service.extract_frontmatter(text)


def _strip_frontmatter(text: str) -> str:
    return workspace_context_config_runtime_helpers_service.strip_frontmatter(text)


def _parse_frontmatter_value(text: str) -> str:
    return workspace_context_config_runtime_helpers_service.parse_frontmatter_value(text)


def _parse_rule_frontmatter(text: str) -> dict[str, Any]:
    return workspace_context_config_runtime_helpers_service.parse_rule_frontmatter(text)


def _rule_enabled(payload: dict[str, Any]) -> bool:
    return workspace_context_config_runtime_helpers_service.rule_enabled(payload)


def _rule_priority(payload: dict[str, Any]) -> int:
    return workspace_context_config_runtime_helpers_service.rule_priority(payload)


def _rule_paths(payload: dict[str, Any]) -> list[str]:
    return workspace_context_config_runtime_helpers_service.rule_paths(payload)


def _relative_cwd_path(cwd: Path, directory: Path) -> str:
    return workspace_context_config_runtime_helpers_service.relative_cwd_path(cwd, directory)


def _rule_matches_cwd(*, cwd: Path, directory: Path, payload: dict[str, Any]) -> bool:
    return workspace_context_config_runtime_helpers_service.rule_matches_cwd(
        cwd=cwd,
        directory=directory,
        payload=payload,
    )


def _discover_rule_docs(*, cwd: Path, directory: Path, safe_resolve: Callable[[Path], Path]) -> list[Path]:
    rule_root = directory / ".agenthub" / "rules"
    if not rule_root.is_dir():
        return []
    try:
        candidates = sorted(rule_root.glob("*.md"))
    except OSError:
        return []
    selected: list[tuple[int, Path]] = []
    for path in candidates:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        payload = _parse_rule_frontmatter(text)
        if not _rule_enabled(payload):
            continue
        if not _rule_matches_cwd(cwd=cwd, directory=directory, payload=payload):
            continue
        selected.append((_rule_priority(payload), safe_resolve(path)))
    selected.sort(key=lambda item: (item[0], str(item[1])))
    return [path for _, path in selected]


def discover_project_doc_paths(
    cwd: str | Path,
    *,
    safe_resolve: Callable[[Path], Path],
    project_root_markers_fn: Callable[[str | Path], list[str]],
    find_project_root_fn: Callable[[str | Path, list[str]], Path],
    dirs_between_project_root_and_cwd_fn: Callable[[str | Path, str | Path], list[Path]],
    project_doc_fallback_filenames_fn: Callable[[str | Path], list[str]],
    local_project_doc_filename: str,
    default_project_doc_filename: str,
) -> list[Path]:
    resolved_cwd = safe_resolve(Path(cwd))
    markers = project_root_markers_fn(resolved_cwd)
    root = find_project_root_fn(resolved_cwd, markers)
    search_dirs = dirs_between_project_root_and_cwd_fn(resolved_cwd, root) if markers else [resolved_cwd]
    preferred_names = [
        local_project_doc_filename,
        default_project_doc_filename,
        str(Path(".agenthub") / default_project_doc_filename),
        *project_doc_fallback_filenames_fn(resolved_cwd),
    ]
    paths: list[Path] = []
    seen: set[Path] = set()
    for directory in search_dirs:
        selected_primary: Path | None = None
        for name in preferred_names:
            candidate = directory / name
            if candidate.exists() and candidate.is_file():
                selected_primary = safe_resolve(candidate)
                break
        if selected_primary is not None and selected_primary not in seen:
            seen.add(selected_primary)
            paths.append(selected_primary)
        for rule_doc in _discover_rule_docs(cwd=resolved_cwd, directory=directory, safe_resolve=safe_resolve):
            if rule_doc in seen:
                continue
            seen.add(rule_doc)
            paths.append(rule_doc)
    return paths


def read_project_docs(
    cwd: str | Path,
    *,
    max_total_bytes: int,
    discover_project_doc_paths_fn: Callable[[str | Path], list[Path]],
) -> str | None:
    if max_total_bytes <= 0:
        return None
    remaining = max_total_bytes
    parts: list[str] = []
    for path in discover_project_doc_paths_fn(cwd):
        if remaining <= 0:
            break
        try:
            data = path.read_bytes()[:remaining]
        except OSError:
            continue
        text = data.decode("utf-8", errors="replace").strip()
        if not text:
            continue
        path_parts = {part.strip().lower() for part in path.parts}
        if ".agenthub" in path_parts and "rules" in path_parts:
            text = _strip_frontmatter(text).strip()
            if not text:
                continue
        parts.append(text)
        remaining -= len(data)
    return "\n\n".join(parts) if parts else None


def discover_project_local_paths(
    filename: str,
    *,
    cwd: str | Path,
    safe_resolve: Callable[[Path], Path],
    workspace_trust_level_fn: Callable[[str | Path], str],
    project_root_markers_fn: Callable[[str | Path], list[str]],
    find_project_root_fn: Callable[[str | Path, list[str]], Path],
    dirs_between_project_root_and_cwd_fn: Callable[[str | Path, str | Path], list[Path]],
    project_local_data_dir_candidates: Sequence[str],
) -> list[Path]:
    resolved_cwd = safe_resolve(Path(cwd))
    if workspace_trust_level_fn(resolved_cwd) != "trusted":
        return []
    markers = project_root_markers_fn(resolved_cwd)
    project_root = find_project_root_fn(resolved_cwd, markers)
    search_dirs = dirs_between_project_root_and_cwd_fn(resolved_cwd, project_root) if markers else [resolved_cwd]
    paths: list[Path] = []
    for directory in search_dirs:
        for dirname in project_local_data_dir_candidates:
            candidate = directory / dirname / filename
            if candidate.exists():
                paths.append(safe_resolve(candidate))
                break
    return paths


def merge_project_file_configs(
    *,
    cwd: str | Path,
    filename: str,
    discover_project_local_paths_fn: Callable[..., list[Path]],
    safe_resolve: Callable[[Path], Path],
    merge_nested_mappings: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]],
    reader_fn: Callable[[Path], dict[str, Any]],
    home_config_paths: Sequence[Path] | None,
) -> tuple[dict[str, Any], list[Path]]:
    paths = discover_project_local_paths_fn(filename, cwd=cwd, home_config_paths=home_config_paths)
    if home_config_paths:
        for path in reversed([safe_resolve(Path(item)) for item in home_config_paths if Path(item).exists()]):
            if path not in paths:
                paths.insert(0, path)
    merged: dict[str, Any] = {}
    for path in paths:
        merged = merge_nested_mappings(merged, reader_fn(path))
    return merged, paths

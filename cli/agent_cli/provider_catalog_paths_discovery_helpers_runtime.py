from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional


def iter_project_roots(
    *,
    cwd: str | Path | None = None,
    app_dir: Path,
    runtime_project_root_fn: Callable[[], Path],
) -> List[Path]:
    roots: List[Path] = []
    runtime_root = runtime_project_root_fn()
    search_start = Path(cwd).resolve() if cwd is not None else Path.cwd().resolve()
    for base in (search_start, app_dir, runtime_root):
        try:
            resolved = base.resolve()
        except OSError:
            resolved = base
        if base == search_start:
            lineage = [resolved]
            current = resolved
            if resolved == runtime_root or runtime_root in resolved.parents:
                while current != runtime_root:
                    current = current.parent
                    lineage.append(current)
            else:
                while current != current.parent:
                    current = current.parent
                    lineage.append(current)
        elif resolved == runtime_root or runtime_root in resolved.parents:
            lineage = [resolved]
            current = resolved
            while current != runtime_root:
                current = current.parent
                lineage.append(current)
        else:
            lineage = [resolved]
        for candidate in lineage:
            if candidate not in roots:
                roots.append(candidate)
    return roots


def find_project_provider_file(
    filename: str,
    *,
    cwd: str | Path | None = None,
    iter_project_roots_fn: Callable[..., List[Path]],
    local_config_dir_candidates: tuple[str, ...] | list[str],
) -> Optional[Path]:
    for root in iter_project_roots_fn(cwd=cwd):
        for dirname in local_config_dir_candidates:
            candidate = root / dirname / filename
            if candidate.exists():
                return candidate
    return None


def related_provider_roots(
    *,
    cwd: str | Path,
    app_dir: Path,
    runtime_project_root_fn: Callable[[], Path],
) -> List[Path]:
    resolved_cwd = Path(cwd).resolve()
    roots: List[Path] = []

    def _append_lineage(base: Path) -> None:
        current = base
        while True:
            if current not in roots:
                roots.append(current)
            if current == current.parent:
                break
            current = current.parent

    _append_lineage(resolved_cwd)
    try:
        resolved_app_dir = app_dir.resolve()
    except OSError:
        resolved_app_dir = app_dir
    if resolved_app_dir in resolved_cwd.parents or resolved_cwd in resolved_app_dir.parents:
        _append_lineage(resolved_app_dir)
    runtime_root = runtime_project_root_fn()
    if runtime_root in resolved_cwd.parents or resolved_cwd in runtime_root.parents:
        _append_lineage(runtime_root)
    return roots


def discover_provider_project_local_paths(
    filename: str,
    *,
    cwd: str | Path,
    home_config_paths: List[Path] | None = None,
    related_provider_roots_fn: Callable[..., List[Path]],
    workspace_trust_level_fn: Callable[..., str],
    project_local_data_dir_candidates: tuple[str, ...] | list[str],
) -> List[Path]:
    trust_home_paths = list(home_config_paths or []) or [Path("__agenthub_missing__")]
    if workspace_trust_level_fn(cwd, home_config_paths=trust_home_paths) == "untrusted":
        return []
    discovered: List[Path] = []
    for root in related_provider_roots_fn(cwd=cwd):
        for dirname in project_local_data_dir_candidates:
            candidate = root / dirname / filename
            if candidate.exists():
                resolved = candidate.resolve()
                if resolved not in discovered:
                    discovered.append(resolved)
                break
    return sorted(discovered, key=lambda path: (len(path.parts), str(path)))

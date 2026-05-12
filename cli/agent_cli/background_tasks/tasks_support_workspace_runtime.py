from __future__ import annotations

import difflib
import json
import shutil
from pathlib import Path
from typing import Any


_IGNORED_WORKSPACE_ROOTS = {
    ".git",
    ".pytest_cache",
}

_IGNORED_WORKSPACE_PREFIXES = (
    ".config/orchestration/",
    "cli/.local/",
)

_IGNORED_WORKSPACE_SUFFIXES = {
    ".pyc",
    ".pyo",
}


def stage_workspace_ignore(source_root: Path, storage: Any):
    root_resolved = source_root.resolve()

    def _relative(path_value: Path | None) -> Path | None:
        if path_value is None:
            return None
        try:
            return path_value.resolve().relative_to(root_resolved)
        except (OSError, RuntimeError, ValueError):
            return None

    ignored_relative_paths: set[Path] = set()
    relative_results = _relative(getattr(storage, "results_dir", None))
    if relative_results is not None and relative_results.parts:
        ignored_relative_paths.add(relative_results)
    relative_db = _relative(getattr(storage, "db_path", None))
    if relative_db is not None and relative_db.parts:
        ignored_relative_paths.add(relative_db)

    def _ignore(current_dir: str, names: list[str]) -> set[str]:
        if not ignored_relative_paths:
            return set()
        try:
            current_relative = Path(current_dir).resolve().relative_to(root_resolved)
        except (OSError, RuntimeError, ValueError):
            current_relative = Path(".")
        ignored: set[str] = set()
        for name in names:
            candidate = (current_relative / name) if current_relative != Path(".") else Path(name)
            if candidate in ignored_relative_paths:
                ignored.add(name)
        return ignored

    return _ignore


def prepare_stage_workspace(task_id: str, *, source_root: Path, storage: Any) -> Path:
    if not source_root.exists():
        raise FileNotFoundError(f"workspace root does not exist: {source_root}")
    stage_root = storage.results_dir / f"{task_id}_workspace"
    if stage_root.exists():
        shutil.rmtree(stage_root)
    shutil.copytree(
        source_root,
        stage_root,
        symlinks=True,
        ignore=stage_workspace_ignore(source_root, storage),
    )
    return stage_root.resolve()


def _ignore_workspace_path(relative_path: str) -> bool:
    normalized = str(relative_path or "").strip().replace("\\", "/").strip("/")
    if not normalized:
        return True
    parts = Path(normalized).parts
    if any(part == "__pycache__" for part in parts):
        return True
    if parts and parts[0] in _IGNORED_WORKSPACE_ROOTS:
        return True
    if any(normalized == prefix[:-1] or normalized.startswith(prefix) for prefix in _IGNORED_WORKSPACE_PREFIXES):
        return True
    return Path(normalized).suffix.lower() in _IGNORED_WORKSPACE_SUFFIXES


def workspace_file_index(root: Path) -> dict[str, Path]:
    if not root.exists():
        return {}
    items: dict[str, Path] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            relative_path = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if _ignore_workspace_path(relative_path):
            continue
        items[relative_path] = path
    return items


def safe_read_text(path: Path | None) -> tuple[bool, list[str]]:
    if path is None or not path.exists():
        return (False, [])
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return (False, [])
    return (True, text.splitlines())


def diff_preview(
    *,
    relative_path: str,
    before_path: Path | None,
    after_path: Path | None,
) -> tuple[bool, str]:
    before_ok, before_lines = safe_read_text(before_path)
    after_ok, after_lines = safe_read_text(after_path)
    if not before_ok and before_path is not None and before_path.exists():
        return (True, "")
    if not after_ok and after_path is not None and after_path.exists():
        return (True, "")
    diff_lines = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
            lineterm="",
        )
    )
    if len(diff_lines) > 160:
        diff_lines = diff_lines[:160] + ["... diff truncated ..."]
    return (False, "\n".join(diff_lines))


def collect_workspace_changes(source_root: Path, stage_root: Path) -> list[dict[str, Any]]:
    source_files = workspace_file_index(source_root)
    stage_files = workspace_file_index(stage_root)
    changes: list[dict[str, Any]] = []
    for relative_path in sorted(set(source_files) | set(stage_files)):
        source_path = source_files.get(relative_path)
        stage_path = stage_files.get(relative_path)
        if source_path is None:
            change_type = "add"
        elif stage_path is None:
            change_type = "delete"
        else:
            try:
                if source_path.read_bytes() == stage_path.read_bytes():
                    continue
            except OSError:
                pass
            change_type = "update"
        binary, rendered_diff = diff_preview(
            relative_path=relative_path,
            before_path=source_path,
            after_path=stage_path,
        )
        payload: dict[str, Any] = {
            "path": relative_path,
            "change_type": change_type,
            "binary": bool(binary),
        }
        if rendered_diff:
            payload["diff_preview"] = rendered_diff
        target_path = stage_path if stage_path is not None and stage_path.exists() else source_path
        if target_path is not None:
            try:
                payload["size_bytes"] = int(target_path.stat().st_size)
            except OSError:
                pass
        changes.append(payload)
    return changes


def load_review_payload(path_text: Any) -> dict[str, Any]:
    path = Path(str(path_text or "").strip()).expanduser()
    if not str(path).strip():
        raise ValueError("missing review_path")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"failed to read review_path: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid review payload: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("review payload must be a JSON object")
    return payload

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Callable, Optional

from cli.agent_cli.tools_core.file_query_match_runtime import iter_files


def extract_glob_base_directory(pattern: str) -> tuple[str, str]:
    text = str(pattern or "").strip()
    match = re.search(r"[*?[{]", text)
    if match is None:
        return os.path.dirname(text), os.path.basename(text)

    static_prefix = text[: match.start()]
    last_sep_index = max(static_prefix.rfind("/"), static_prefix.rfind(os.sep))
    if last_sep_index == -1:
        return "", text

    base_dir = static_prefix[:last_sep_index]
    relative_pattern = text[last_sep_index + 1 :]
    if not base_dir and last_sep_index == 0:
        base_dir = os.sep
    if os.name == "nt" and re.fullmatch(r"[A-Za-z]:", base_dir):
        base_dir += os.sep
    return base_dir, relative_pattern


def rg_glob_files(
    *,
    workspace_root: Path,
    target: Path,
    pattern: str,
    limit: int,
    which_fn: Callable[[str], str | None],
    run_fn: Callable[..., Any],
    relative_text_fn: Callable[[Path, Path], str],
    file_tool_error_cls: type[Exception],
) -> Optional[dict[str, Any]]:
    if not which_fn("rg"):
        return None
    command = [
        "rg",
        "--files",
        "--glob",
        str(pattern),
        "--sort=modified",
        "--no-ignore",
        "--hidden",
    ]
    result = run_fn(
        command,
        cwd=str(target),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode not in {0, 1}:
        stderr_text = str(result.stderr or "").strip() or "unknown rg failure"
        raise file_tool_error_cls(f"rg failed: {stderr_text}")
    paths: list[str] = []
    seen: set[str] = set()
    for raw_line in str(result.stdout or "").splitlines():
        raw_path = str(raw_line or "").strip()
        if not raw_path:
            continue
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = target / candidate
        try:
            normalized = relative_text_fn(candidate.resolve(), workspace_root).replace("\\", "/")
        except OSError:
            normalized = relative_text_fn(candidate, workspace_root).replace("\\", "/")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        paths.append(normalized)
        if len(paths) > int(limit):
            break
    return {
        "paths": paths[:limit],
        "truncated": len(paths) > int(limit),
    }


def python_glob_files(
    *,
    workspace_root: Path,
    target: Path,
    pattern: str,
    limit: int,
    relative_text_fn: Callable[[Path, Path], str],
) -> dict[str, Any]:
    candidates: list[tuple[float, str]] = []
    for item in iter_files(target):
        try:
            relative_to_target = item.relative_to(target).as_posix()
        except ValueError:
            continue
        if not Path(relative_to_target).match(str(pattern)):
            continue
        rel_path = relative_text_fn(item, workspace_root).replace("\\", "/")
        try:
            sort_key = float(item.stat().st_mtime)
        except OSError:
            sort_key = 0.0
        candidates.append((sort_key, rel_path))

    candidates.sort(key=lambda item: (item[0], item[1]))
    limited = [path for _, path in candidates[:limit]]
    return {
        "paths": limited,
        "truncated": len(candidates) > int(limit),
    }

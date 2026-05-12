from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


def entry_kind(path: Path) -> str:
    try:
        if path.is_symlink():
            return "symlink"
        if path.is_dir():
            return "dir"
        if path.is_file():
            return "file"
    except OSError:
        return "other"
    return "other"


def collect_list_dir_entries(base_dir: Path, *, depth: int, file_tool_error_cls: type[Exception]) -> List[Dict[str, Any]]:
    collected: List[Dict[str, Any]] = []

    def walk(current_dir: Path, relative_prefix: Path, remaining_depth: int) -> None:
        try:
            children = sorted(current_dir.iterdir(), key=lambda item: item.name)
        except OSError as exc:
            raise file_tool_error_cls(f"failed to read directory: {exc}") from exc
        for child in children:
            relative_path = (relative_prefix / child.name) if str(relative_prefix) else Path(child.name)
            relative_text_value = relative_path.as_posix()
            kind = entry_kind(child)
            collected.append({"kind": kind, "path": relative_text_value})
            if kind == "dir" and remaining_depth > 1:
                walk(child, relative_path, remaining_depth - 1)

    walk(base_dir, Path(""), int(depth))
    return collected

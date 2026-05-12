from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from cli.agent_cli.tools_core.file_query_path_runtime import (
    resolve_workspace_path,
)
from cli.agent_cli.tools_core.file_query_request_runtime import normalize_requested_path


@dataclass(slots=True, frozen=True)
class ListDirRequest:
    requested_path: str
    target: Path
    offset: int
    limit: int
    depth: int


def _list_dir_positive_value(
    value: int,
    *,
    default: int,
    error_text: str,
    file_tool_error_cls: type[Exception],
) -> int:
    resolved = int(value or default)
    if resolved <= 0:
        raise file_tool_error_cls(error_text)
    return resolved


def prepare_list_dir_request(
    *,
    workspace_root: Path,
    cwd_root: Path,
    dir_path: Optional[str],
    offset: int,
    limit: int,
    depth: int,
    default_offset: int,
    default_limit: int,
    default_depth: int,
    file_tool_error_cls: type[Exception],
) -> ListDirRequest:
    requested_path = normalize_requested_path(dir_path)
    resolved_offset = _list_dir_positive_value(
        int(offset or default_offset),
        default=default_offset,
        error_text="offset must be a 1-indexed entry number",
        file_tool_error_cls=file_tool_error_cls,
    )
    resolved_limit = _list_dir_positive_value(
        int(limit or default_limit),
        default=default_limit,
        error_text="limit must be greater than zero",
        file_tool_error_cls=file_tool_error_cls,
    )
    resolved_depth = _list_dir_positive_value(
        int(depth or default_depth),
        default=default_depth,
        error_text="depth must be greater than zero",
        file_tool_error_cls=file_tool_error_cls,
    )
    requested_dir_path = str(dir_path or "").strip()
    if requested_dir_path and not Path(requested_dir_path).is_absolute():
        raise file_tool_error_cls("dir_path must be an absolute path")
    target = resolve_workspace_path(
        workspace_root,
        dir_path,
        default_root=cwd_root,
        file_tool_error_cls=file_tool_error_cls,
    )
    if not target.exists():
        raise file_tool_error_cls(f"path not found: {dir_path or '.'}")
    if not target.is_dir():
        raise file_tool_error_cls(f"path is not a directory: {dir_path or '.'}")
    return ListDirRequest(
        requested_path=requested_path,
        target=target,
        offset=resolved_offset,
        limit=resolved_limit,
        depth=resolved_depth,
    )


__all__ = [
    "ListDirRequest",
    "prepare_list_dir_request",
]

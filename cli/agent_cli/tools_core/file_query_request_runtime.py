from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from cli.agent_cli.tools_core.file_query_glob_runtime import extract_glob_base_directory
from cli.agent_cli.tools_core.file_query_path_runtime import (
    clamp_positive,
    resolve_workspace_path,
)


@dataclass(frozen=True)
class GlobQueryRequest:
    requested_path: str
    requested_pattern: str
    search_pattern: str
    target: Path
    max_items: int


@dataclass(frozen=True)
class GrepQueryRequest:
    requested_path: str
    normalized_pattern: str
    normalized_include: str | None
    target: Path
    max_items: int


def normalize_requested_path(path: Optional[str]) -> str:
    return str(path or "").strip() or "."


def normalize_required_query_text(
    value: str | None,
    *,
    field_name: str,
    file_tool_error_cls: type[Exception],
) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise file_tool_error_cls(f"{field_name} must not be empty")
    return normalized


def _requested_target_text(raw_path: str | None) -> str:
    return str(raw_path or "").strip() or "."


def resolve_existing_target(
    *,
    workspace_root: Path,
    cwd_root: Path,
    path: Optional[str],
    file_tool_error_cls: type[Exception],
    require_directory: bool = False,
    raw_value_for_error: str | None = None,
) -> Path:
    target = resolve_workspace_path(
        workspace_root,
        path,
        default_root=cwd_root,
        file_tool_error_cls=file_tool_error_cls,
    )
    target_text = _requested_target_text(raw_value_for_error if raw_value_for_error is not None else path)
    if not target.exists():
        raise file_tool_error_cls(f"path not found: {target_text}")
    if require_directory and not target.is_dir():
        raise file_tool_error_cls(f"path is not a directory: {target_text}")
    return target


def prepare_glob_request(
    *,
    workspace_root: Path,
    cwd_root: Path,
    pattern: str,
    path: Optional[str],
    limit: int,
    default_limit: int,
    maximum_limit: int,
    file_tool_error_cls: type[Exception],
) -> GlobQueryRequest:
    requested_path = normalize_requested_path(path)
    requested_pattern = normalize_required_query_text(
        pattern,
        field_name="pattern",
        file_tool_error_cls=file_tool_error_cls,
    )
    target = resolve_existing_target(
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        path=path,
        file_tool_error_cls=file_tool_error_cls,
        require_directory=True,
    )
    search_pattern = requested_pattern
    if Path(search_pattern).is_absolute():
        base_dir_text, relative_pattern = extract_glob_base_directory(search_pattern)
        target_text = base_dir_text or search_pattern
        target = resolve_existing_target(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            path=target_text,
            file_tool_error_cls=file_tool_error_cls,
            require_directory=True,
            raw_value_for_error=target_text,
        )
        search_pattern = str(relative_pattern or "").strip()
    if not search_pattern:
        raise file_tool_error_cls("pattern must not be empty")
    max_items = clamp_positive(
        int(limit or default_limit),
        default=default_limit,
        maximum=maximum_limit,
        file_tool_error_cls=file_tool_error_cls,
    )
    return GlobQueryRequest(
        requested_path=requested_path,
        requested_pattern=requested_pattern,
        search_pattern=search_pattern,
        target=target,
        max_items=max_items,
    )


def prepare_grep_request(
    *,
    workspace_root: Path,
    cwd_root: Path,
    pattern: str,
    include: Optional[str],
    path: Optional[str],
    limit: int,
    default_limit: int,
    maximum_limit: int,
    file_tool_error_cls: type[Exception],
) -> GrepQueryRequest:
    requested_path = normalize_requested_path(path)
    normalized_pattern = normalize_required_query_text(
        pattern,
        field_name="pattern",
        file_tool_error_cls=file_tool_error_cls,
    )
    target = resolve_existing_target(
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        path=path,
        file_tool_error_cls=file_tool_error_cls,
    )
    max_items = clamp_positive(
        int(limit or default_limit),
        default=default_limit,
        maximum=maximum_limit,
        file_tool_error_cls=file_tool_error_cls,
    )
    return GrepQueryRequest(
        requested_path=requested_path,
        normalized_pattern=normalized_pattern,
        normalized_include=str(include or "").strip() or None,
        target=target,
        max_items=max_items,
    )

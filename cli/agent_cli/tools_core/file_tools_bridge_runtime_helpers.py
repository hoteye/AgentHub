from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.tools_core import file_query_runtime
from cli.agent_cli.tools_core import file_read_runtime as file_read_helpers


def resolve_workspace_path(
    workspace_root: Path,
    raw_path: str | None,
    *,
    default_root: Path | None = None,
    file_tool_error_cls: type[Exception],
) -> Path:
    return file_query_runtime.resolve_workspace_path(
        workspace_root,
        raw_path,
        default_root=default_root,
        file_tool_error_cls=file_tool_error_cls,
    )


def relative_text(path: Path, workspace_root: Path) -> str:
    return file_query_runtime.relative_text(path, workspace_root)


def execute_glob_files(
    *,
    workspace_root: Path,
    cwd_root: Path,
    pattern: str,
    path: str | None = None,
    limit: int = 100,
    glob_default_limit: int,
    glob_max_limit: int,
    which_fn: Callable[[str], str | None],
    run_fn: Callable[..., Any],
    file_tool_error_cls: type[Exception],
) -> ToolEvent:
    return file_query_runtime.glob_files(
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        pattern=pattern,
        path=path,
        limit=limit,
        glob_default_limit=glob_default_limit,
        glob_max_limit=glob_max_limit,
        which_fn=which_fn,
        run_fn=run_fn,
        file_tool_error_cls=file_tool_error_cls,
    )


def execute_grep_files(
    *,
    workspace_root: Path,
    cwd_root: Path,
    pattern: str,
    include: str | None = None,
    path: str | None = None,
    limit: int = 100,
    grep_default_limit: int,
    grep_max_limit: int,
    which_fn: Callable[[str], str | None],
    run_fn: Callable[..., Any],
    file_tool_error_cls: type[Exception],
    output_mode: str = "files_with_matches",
    case_insensitive: bool = False,
    file_type: str | None = None,
    line_numbers: bool = False,
    after_context: int | None = None,
    before_context: int | None = None,
    context: int | None = None,
    offset: int = 0,
    multiline: bool = False,
) -> ToolEvent:
    return file_query_runtime.grep_files(
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        pattern=pattern,
        include=include,
        path=path,
        limit=limit,
        grep_default_limit=grep_default_limit,
        grep_max_limit=grep_max_limit,
        which_fn=which_fn,
        run_fn=run_fn,
        file_tool_error_cls=file_tool_error_cls,
        output_mode=output_mode,
        case_insensitive=case_insensitive,
        file_type=file_type,
        line_numbers=line_numbers,
        after_context=after_context,
        before_context=before_context,
        context=context,
        offset=offset,
        multiline=multiline,
    )


def execute_list_dir(
    *,
    workspace_root: Path,
    cwd_root: Path,
    dir_path: str | None = None,
    offset: int = 1,
    limit: int = 25,
    depth: int = 2,
    list_default_offset: int,
    list_default_limit: int,
    list_default_depth: int,
    file_tool_error_cls: type[Exception],
) -> ToolEvent:
    return file_query_runtime.list_dir(
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        dir_path=dir_path,
        offset=offset,
        limit=limit,
        depth=depth,
        list_default_offset=list_default_offset,
        list_default_limit=list_default_limit,
        list_default_depth=list_default_depth,
        file_tool_error_cls=file_tool_error_cls,
    )


def execute_file_list(
    *,
    workspace_root: Path,
    cwd_root: Path,
    path: str | None = None,
    limit: int = 50,
    list_dir_fn: Callable[..., ToolEvent],
) -> ToolEvent:
    return file_query_runtime.file_list(
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        path=path,
        limit=limit,
        list_dir_fn=list_dir_fn,
    )


def execute_file_search(
    *,
    workspace_root: Path,
    cwd_root: Path,
    query: str,
    path: str | None = None,
    limit: int = 20,
    grep_files_fn: Callable[..., ToolEvent],
) -> ToolEvent:
    return file_query_runtime.file_search(
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        query=query,
        path=path,
        limit=limit,
        grep_files_fn=grep_files_fn,
    )


def execute_file_read(
    *,
    workspace_root: Path,
    cwd_root: Path,
    path: str,
    offset: int | None = None,
    limit: int | None = None,
    max_chars: int | None = None,
    resolve_workspace_path_fn: Callable[..., Path],
    relative_text_fn: Callable[[Path, Path], str],
    file_tool_error_cls: type[Exception],
) -> ToolEvent:
    return file_read_helpers.file_read(
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        path=path,
        offset=offset,
        limit=limit,
        max_chars=max_chars,
        resolve_workspace_path_fn=resolve_workspace_path_fn,
        relative_text_fn=relative_text_fn,
        file_tool_error_cls=file_tool_error_cls,
    )


def execute_read_file(
    *,
    workspace_root: Path,
    cwd_root: Path,
    file_path: str,
    offset: int | None = None,
    limit: int | None = None,
    mode: str | None = None,
    indentation: dict[str, Any] | None = None,
    resolve_workspace_path_fn: Callable[..., Path],
    relative_text_fn: Callable[[Path, Path], str],
    file_tool_error_cls: type[Exception],
) -> ToolEvent:
    return file_read_helpers.read_file(
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        file_path=file_path,
        offset=offset,
        limit=limit,
        mode=mode,
        indentation=indentation,
        resolve_workspace_path_fn=resolve_workspace_path_fn,
        relative_text_fn=relative_text_fn,
        file_tool_error_cls=file_tool_error_cls,
    )


__all__ = [
    "execute_file_list",
    "execute_file_read",
    "execute_file_search",
    "execute_glob_files",
    "execute_grep_files",
    "execute_list_dir",
    "execute_read_file",
    "relative_text",
    "resolve_workspace_path",
]

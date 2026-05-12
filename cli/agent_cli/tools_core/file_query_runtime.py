from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.tools_core import file_query_runtime_helpers_runtime as file_query_runtime_helpers_runtime_service
from cli.agent_cli.tools_core.file_query_path_runtime import relative_text, resolve_workspace_path


def glob_files(
    *,
    workspace_root: Path,
    cwd_root: Path,
    pattern: str,
    path: Optional[str],
    limit: int,
    glob_default_limit: int,
    glob_max_limit: int,
    which_fn: Callable[[str], str | None],
    run_fn: Callable[..., Any],
    file_tool_error_cls: type[Exception],
) -> ToolEvent:
    return file_query_runtime_helpers_runtime_service.glob_files(
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


def grep_files(
    *,
    workspace_root: Path,
    cwd_root: Path,
    pattern: str,
    include: Optional[str],
    path: Optional[str],
    limit: int,
    grep_default_limit: int,
    grep_max_limit: int,
    which_fn: Callable[[str], str | None],
    run_fn: Callable[..., Any],
    file_tool_error_cls: type[Exception],
    output_mode: str = "files_with_matches",
    case_insensitive: bool = False,
    file_type: Optional[str] = None,
    line_numbers: bool = False,
    after_context: Optional[int] = None,
    before_context: Optional[int] = None,
    context: Optional[int] = None,
    offset: int = 0,
    multiline: bool = False,
) -> ToolEvent:
    return file_query_runtime_helpers_runtime_service.grep_files(
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


def list_dir(
    *,
    workspace_root: Path,
    cwd_root: Path,
    dir_path: Optional[str],
    offset: int,
    limit: int,
    depth: int,
    list_default_offset: int,
    list_default_limit: int,
    list_default_depth: int,
    file_tool_error_cls: type[Exception],
) -> ToolEvent:
    return file_query_runtime_helpers_runtime_service.list_dir(
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


def file_list(
    *,
    workspace_root: Path,
    cwd_root: Path,
    path: Optional[str],
    limit: int,
    list_dir_fn: Callable[..., ToolEvent],
) -> ToolEvent:
    return file_query_runtime_helpers_runtime_service.file_list(
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        path=path,
        limit=limit,
        list_dir_fn=list_dir_fn,
    )


def file_search(
    *,
    workspace_root: Path,
    cwd_root: Path,
    query: str,
    path: Optional[str],
    limit: int,
    grep_files_fn: Callable[..., ToolEvent],
) -> ToolEvent:
    return file_query_runtime_helpers_runtime_service.file_search(
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        query=query,
        path=path,
        limit=limit,
        grep_files_fn=grep_files_fn,
    )

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core.workspace_file_normalization_helpers_runtime import (
    normalize_file_list_request,
    normalize_file_list_result_request,
    normalize_file_search_request,
    normalize_file_search_result_request,
    normalize_glob_files_request,
    normalize_glob_files_result_request,
    normalize_grep_files_request,
    normalize_grep_files_result_request,
    normalize_list_dir_request,
    normalize_list_dir_result_request,
)
from cli.agent_cli.tools_core.workspace_file_projection_helpers_runtime import (
    project_file_list_event,
    project_file_list_result,
    project_file_search_event,
    project_file_search_result,
    project_glob_files_event,
    project_glob_files_result,
    project_grep_files_event,
    project_grep_files_result,
    project_list_dir_event,
    project_list_dir_result,
)


def glob_files(
    *,
    workspace_root: Path,
    cwd_root: Path,
    pattern: str,
    path: Optional[str] = None,
    limit: int = 100,
) -> ToolEvent:
    return project_glob_files_event(
        normalize_glob_files_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            pattern=pattern,
            path=path,
            limit=limit,
        )
    )


def glob_files_result(
    *,
    workspace_root: Path,
    cwd_root: Path,
    pattern: str,
    path: Optional[str] = None,
    limit: int = 100,
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    glob_files_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return project_glob_files_result(
        normalize_glob_files_result_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            pattern=pattern,
            path=path,
            limit=limit,
            call_structured_helper=call_structured_helper,
            result_from_event=result_from_event,
            glob_files_call=glob_files_call,
        )
    )


def grep_files(
    *,
    workspace_root: Path,
    cwd_root: Path,
    pattern: str,
    include: Optional[str] = None,
    path: Optional[str] = None,
    limit: int = 100,
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
    return project_grep_files_event(
        normalize_grep_files_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            pattern=pattern,
            include=include,
            path=path,
            limit=limit,
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
    )


def grep_files_result(
    *,
    workspace_root: Path,
    cwd_root: Path,
    pattern: str,
    include: Optional[str] = None,
    path: Optional[str] = None,
    limit: int = 100,
    output_mode: str = "files_with_matches",
    case_insensitive: bool = False,
    file_type: Optional[str] = None,
    line_numbers: bool = False,
    after_context: Optional[int] = None,
    before_context: Optional[int] = None,
    context: Optional[int] = None,
    offset: int = 0,
    multiline: bool = False,
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    grep_files_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return project_grep_files_result(
        normalize_grep_files_result_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            pattern=pattern,
            include=include,
            path=path,
            limit=limit,
            output_mode=output_mode,
            case_insensitive=case_insensitive,
            file_type=file_type,
            line_numbers=line_numbers,
            after_context=after_context,
            before_context=before_context,
            context=context,
            offset=offset,
            multiline=multiline,
            call_structured_helper=call_structured_helper,
            result_from_event=result_from_event,
            grep_files_call=grep_files_call,
        )
    )


def list_dir(
    *,
    workspace_root: Path,
    cwd_root: Path,
    dir_path: Optional[str] = None,
    offset: int = 1,
    limit: int = 25,
    depth: int = 2,
) -> ToolEvent:
    return project_list_dir_event(
        normalize_list_dir_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            dir_path=dir_path,
            offset=offset,
            limit=limit,
            depth=depth,
        )
    )


def list_dir_result(
    *,
    workspace_root: Path,
    cwd_root: Path,
    dir_path: Optional[str] = None,
    offset: int = 1,
    limit: int = 25,
    depth: int = 2,
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    list_dir_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return project_list_dir_result(
        normalize_list_dir_result_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            dir_path=dir_path,
            offset=offset,
            limit=limit,
            depth=depth,
            call_structured_helper=call_structured_helper,
            result_from_event=result_from_event,
            list_dir_call=list_dir_call,
        )
    )


def file_list(
    *,
    workspace_root: Path,
    cwd_root: Path,
    path: Optional[str] = None,
    limit: int = 50,
) -> ToolEvent:
    return project_file_list_event(
        normalize_file_list_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            path=path,
            limit=limit,
        )
    )


def file_list_result(
    *,
    workspace_root: Path,
    cwd_root: Path,
    path: Optional[str] = None,
    limit: int = 50,
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    file_list_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return project_file_list_result(
        normalize_file_list_result_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            path=path,
            limit=limit,
            call_structured_helper=call_structured_helper,
            result_from_event=result_from_event,
            file_list_call=file_list_call,
        )
    )


def file_search(
    *,
    workspace_root: Path,
    cwd_root: Path,
    query: str,
    path: Optional[str] = None,
    limit: int = 20,
) -> ToolEvent:
    return project_file_search_event(
        normalize_file_search_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            query=query,
            path=path,
            limit=limit,
        )
    )


def file_search_result(
    *,
    workspace_root: Path,
    cwd_root: Path,
    query: str,
    path: Optional[str] = None,
    limit: int = 20,
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    file_search_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return project_file_search_result(
        normalize_file_search_result_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            query=query,
            path=path,
            limit=limit,
            call_structured_helper=call_structured_helper,
            result_from_event=result_from_event,
            file_search_call=file_search_call,
        )
    )


__all__ = [
    "glob_files",
    "glob_files_result",
    "grep_files",
    "grep_files_result",
    "list_dir",
    "list_dir_result",
    "file_list",
    "file_list_result",
    "file_search",
    "file_search_result",
]

from __future__ import annotations

from pathlib import Path

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core import (
    file_tools_bridge_normalization_helpers_runtime,
    file_tools_bridge_projection_helpers_runtime,
)
from cli.agent_cli.tools_core import (
    file_tools_bridge_shared_runtime as file_tools_bridge_shared_runtime_service,
)


def glob_files(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    pattern: str,
    path: str | None = None,
    limit: int = file_tools_bridge_shared_runtime_service.GLOB_DEFAULT_LIMIT,
) -> ToolEvent:
    return file_tools_bridge_projection_helpers_runtime.project_glob_files_event(
        file_tools_bridge_normalization_helpers_runtime.normalize_glob_files_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            pattern=pattern,
            path=path,
            limit=limit,
            glob_default_limit=file_tools_bridge_shared_runtime_service.GLOB_DEFAULT_LIMIT,
            glob_max_limit=file_tools_bridge_shared_runtime_service.GLOB_MAX_LIMIT,
            which_fn=file_tools_bridge_shared_runtime_service.shutil.which,
            run_fn=file_tools_bridge_shared_runtime_service.subprocess.run,
            file_tool_error_cls=file_tools_bridge_shared_runtime_service.FileToolError,
        )
    )


def grep_files(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    pattern: str,
    include: str | None = None,
    path: str | None = None,
    limit: int = file_tools_bridge_shared_runtime_service.GREP_DEFAULT_LIMIT,
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
    return file_tools_bridge_projection_helpers_runtime.project_grep_files_event(
        file_tools_bridge_normalization_helpers_runtime.normalize_grep_files_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            pattern=pattern,
            include=include,
            path=path,
            limit=limit,
            grep_default_limit=file_tools_bridge_shared_runtime_service.GREP_DEFAULT_LIMIT,
            grep_max_limit=file_tools_bridge_shared_runtime_service.GREP_MAX_LIMIT,
            which_fn=file_tools_bridge_shared_runtime_service.shutil.which,
            run_fn=file_tools_bridge_shared_runtime_service.subprocess.run,
            file_tool_error_cls=file_tools_bridge_shared_runtime_service.FileToolError,
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


def list_dir(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    dir_path: str | None = None,
    offset: int = file_tools_bridge_shared_runtime_service.LIST_DEFAULT_OFFSET,
    limit: int = file_tools_bridge_shared_runtime_service.LIST_DEFAULT_LIMIT,
    depth: int = file_tools_bridge_shared_runtime_service.LIST_DEFAULT_DEPTH,
) -> ToolEvent:
    return file_tools_bridge_projection_helpers_runtime.project_list_dir_event(
        file_tools_bridge_normalization_helpers_runtime.normalize_list_dir_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            dir_path=dir_path,
            offset=offset,
            limit=limit,
            depth=depth,
            list_default_offset=file_tools_bridge_shared_runtime_service.LIST_DEFAULT_OFFSET,
            list_default_limit=file_tools_bridge_shared_runtime_service.LIST_DEFAULT_LIMIT,
            list_default_depth=file_tools_bridge_shared_runtime_service.LIST_DEFAULT_DEPTH,
            file_tool_error_cls=file_tools_bridge_shared_runtime_service.FileToolError,
        )
    )


def file_list(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    path: str | None = None,
    limit: int = 50,
) -> ToolEvent:
    return file_tools_bridge_projection_helpers_runtime.project_file_list_event(
        file_tools_bridge_normalization_helpers_runtime.normalize_file_list_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            path=path,
            limit=limit,
            list_dir_fn=list_dir,
        )
    )


def file_search(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    query: str,
    path: str | None = None,
    limit: int = 20,
) -> ToolEvent:
    return file_tools_bridge_projection_helpers_runtime.project_file_search_event(
        file_tools_bridge_normalization_helpers_runtime.normalize_file_search_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            query=query,
            path=path,
            limit=limit,
            grep_files_fn=grep_files,
        )
    )


def glob_files_result(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    pattern: str,
    path: str | None = None,
    limit: int = file_tools_bridge_shared_runtime_service.GLOB_DEFAULT_LIMIT,
) -> CommandExecutionResult:
    return file_tools_bridge_projection_helpers_runtime.project_glob_files_result(
        file_tools_bridge_normalization_helpers_runtime.normalize_glob_files_result_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            pattern=pattern,
            path=path,
            limit=limit,
            glob_files_fn=glob_files,
            structured_result_from_event_fn=file_tools_bridge_shared_runtime_service.structured_result_from_event,
        )
    )


def grep_files_result(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    pattern: str,
    include: str | None = None,
    path: str | None = None,
    limit: int = file_tools_bridge_shared_runtime_service.GREP_DEFAULT_LIMIT,
    output_mode: str = "files_with_matches",
    case_insensitive: bool = False,
    file_type: str | None = None,
    line_numbers: bool = False,
    after_context: int | None = None,
    before_context: int | None = None,
    context: int | None = None,
    offset: int = 0,
    multiline: bool = False,
) -> CommandExecutionResult:
    return file_tools_bridge_projection_helpers_runtime.project_grep_files_result(
        file_tools_bridge_normalization_helpers_runtime.normalize_grep_files_result_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            pattern=pattern,
            include=include,
            path=path,
            limit=limit,
            grep_files_fn=grep_files,
            structured_result_from_event_fn=file_tools_bridge_shared_runtime_service.structured_result_from_event,
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


def list_dir_result(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    dir_path: str | None = None,
    offset: int = file_tools_bridge_shared_runtime_service.LIST_DEFAULT_OFFSET,
    limit: int = file_tools_bridge_shared_runtime_service.LIST_DEFAULT_LIMIT,
    depth: int = file_tools_bridge_shared_runtime_service.LIST_DEFAULT_DEPTH,
) -> CommandExecutionResult:
    return file_tools_bridge_projection_helpers_runtime.project_list_dir_result(
        file_tools_bridge_normalization_helpers_runtime.normalize_list_dir_result_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            dir_path=dir_path,
            offset=offset,
            limit=limit,
            depth=depth,
            list_dir_fn=list_dir,
            structured_result_from_event_fn=file_tools_bridge_shared_runtime_service.structured_result_from_event,
        )
    )


def file_list_result(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    path: str | None = None,
    limit: int = 50,
) -> CommandExecutionResult:
    return file_tools_bridge_projection_helpers_runtime.project_file_list_result(
        file_tools_bridge_normalization_helpers_runtime.normalize_file_list_result_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            path=path,
            limit=limit,
            file_list_fn=file_list,
            structured_result_from_event_fn=file_tools_bridge_shared_runtime_service.structured_result_from_event,
        )
    )


def file_search_result(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    query: str,
    path: str | None = None,
    limit: int = 20,
) -> CommandExecutionResult:
    return file_tools_bridge_projection_helpers_runtime.project_file_search_result(
        file_tools_bridge_normalization_helpers_runtime.normalize_file_search_result_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            query=query,
            path=path,
            limit=limit,
            file_search_fn=file_search,
            structured_result_from_event_fn=file_tools_bridge_shared_runtime_service.structured_result_from_event,
        )
    )


__all__ = [
    "file_list",
    "file_list_result",
    "file_search",
    "file_search_result",
    "glob_files",
    "glob_files_result",
    "grep_files",
    "grep_files_result",
    "list_dir",
    "list_dir_result",
]

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core.file_tools_bridge_pure_helpers_runtime import (
    Payload,
    build_file_tools_bridge_payload,
)


def _normalize_cwd_root(workspace_root: Path, cwd_root: Path | None) -> Path:
    return cwd_root or workspace_root


def normalize_glob_files_request(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    pattern: str,
    path: str | None = None,
    limit: int = 100,
    glob_default_limit: int,
    glob_max_limit: int,
    which_fn: Callable[[str], str | None],
    run_fn: Callable[..., Any],
    file_tool_error_cls: type[Exception],
) -> Payload:
    return build_file_tools_bridge_payload(
        workspace_root=workspace_root,
        cwd_root=_normalize_cwd_root(workspace_root, cwd_root),
        pattern=pattern,
        path=path,
        limit=limit,
        glob_default_limit=glob_default_limit,
        glob_max_limit=glob_max_limit,
        which_fn=which_fn,
        run_fn=run_fn,
        file_tool_error_cls=file_tool_error_cls,
    )


def normalize_glob_files_result_request(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    pattern: str,
    path: str | None = None,
    limit: int = 100,
    glob_files_fn: Callable[..., ToolEvent],
    structured_result_from_event_fn: Callable[..., CommandExecutionResult],
) -> Payload:
    return build_file_tools_bridge_payload(
        workspace_root=workspace_root,
        cwd_root=_normalize_cwd_root(workspace_root, cwd_root),
        pattern=pattern,
        path=path,
        limit=limit,
        glob_files_fn=glob_files_fn,
        structured_result_from_event_fn=structured_result_from_event_fn,
    )


def normalize_grep_files_request(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
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
) -> Payload:
    return build_file_tools_bridge_payload(
        workspace_root=workspace_root,
        cwd_root=_normalize_cwd_root(workspace_root, cwd_root),
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


def normalize_grep_files_result_request(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    pattern: str,
    include: str | None = None,
    path: str | None = None,
    limit: int = 100,
    grep_files_fn: Callable[..., ToolEvent],
    structured_result_from_event_fn: Callable[..., CommandExecutionResult],
    output_mode: str = "files_with_matches",
    case_insensitive: bool = False,
    file_type: str | None = None,
    line_numbers: bool = False,
    after_context: int | None = None,
    before_context: int | None = None,
    context: int | None = None,
    offset: int = 0,
    multiline: bool = False,
) -> Payload:
    return build_file_tools_bridge_payload(
        workspace_root=workspace_root,
        cwd_root=_normalize_cwd_root(workspace_root, cwd_root),
        pattern=pattern,
        include=include,
        path=path,
        limit=limit,
        grep_files_fn=grep_files_fn,
        structured_result_from_event_fn=structured_result_from_event_fn,
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


def normalize_list_dir_request(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    dir_path: str | None = None,
    offset: int = 1,
    limit: int = 25,
    depth: int = 2,
    list_default_offset: int,
    list_default_limit: int,
    list_default_depth: int,
    file_tool_error_cls: type[Exception],
) -> Payload:
    return build_file_tools_bridge_payload(
        workspace_root=workspace_root,
        cwd_root=_normalize_cwd_root(workspace_root, cwd_root),
        dir_path=dir_path,
        offset=offset,
        limit=limit,
        depth=depth,
        list_default_offset=list_default_offset,
        list_default_limit=list_default_limit,
        list_default_depth=list_default_depth,
        file_tool_error_cls=file_tool_error_cls,
    )


def normalize_list_dir_result_request(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    dir_path: str | None = None,
    offset: int = 1,
    limit: int = 25,
    depth: int = 2,
    list_dir_fn: Callable[..., ToolEvent],
    structured_result_from_event_fn: Callable[..., CommandExecutionResult],
) -> Payload:
    return build_file_tools_bridge_payload(
        workspace_root=workspace_root,
        cwd_root=_normalize_cwd_root(workspace_root, cwd_root),
        dir_path=dir_path,
        offset=offset,
        limit=limit,
        depth=depth,
        list_dir_fn=list_dir_fn,
        structured_result_from_event_fn=structured_result_from_event_fn,
    )


def normalize_file_list_request(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    path: str | None = None,
    limit: int = 50,
    list_dir_fn: Callable[..., ToolEvent],
) -> Payload:
    return build_file_tools_bridge_payload(
        workspace_root=workspace_root,
        cwd_root=_normalize_cwd_root(workspace_root, cwd_root),
        path=path,
        limit=limit,
        list_dir_fn=list_dir_fn,
    )


def normalize_file_list_result_request(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    path: str | None = None,
    limit: int = 50,
    file_list_fn: Callable[..., ToolEvent],
    structured_result_from_event_fn: Callable[..., CommandExecutionResult],
) -> Payload:
    return build_file_tools_bridge_payload(
        workspace_root=workspace_root,
        cwd_root=_normalize_cwd_root(workspace_root, cwd_root),
        path=path,
        limit=limit,
        file_list_fn=file_list_fn,
        structured_result_from_event_fn=structured_result_from_event_fn,
    )


def normalize_file_search_request(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    query: str,
    path: str | None = None,
    limit: int = 20,
    grep_files_fn: Callable[..., ToolEvent],
) -> Payload:
    return build_file_tools_bridge_payload(
        workspace_root=workspace_root,
        cwd_root=_normalize_cwd_root(workspace_root, cwd_root),
        query=query,
        path=path,
        limit=limit,
        grep_files_fn=grep_files_fn,
    )


def normalize_file_search_result_request(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    query: str,
    path: str | None = None,
    limit: int = 20,
    file_search_fn: Callable[..., ToolEvent],
    structured_result_from_event_fn: Callable[..., CommandExecutionResult],
) -> Payload:
    return build_file_tools_bridge_payload(
        workspace_root=workspace_root,
        cwd_root=_normalize_cwd_root(workspace_root, cwd_root),
        query=query,
        path=path,
        limit=limit,
        file_search_fn=file_search_fn,
        structured_result_from_event_fn=structured_result_from_event_fn,
    )


def normalize_file_read_request(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    path: str,
    offset: int | None = None,
    limit: int | None = None,
    max_chars: int | None = None,
    resolve_workspace_path_fn: Callable[..., Path],
    relative_text_fn: Callable[[Path, Path], str],
    file_tool_error_cls: type[Exception],
) -> Payload:
    return build_file_tools_bridge_payload(
        workspace_root=workspace_root,
        cwd_root=_normalize_cwd_root(workspace_root, cwd_root),
        path=path,
        offset=offset,
        limit=limit,
        max_chars=max_chars,
        resolve_workspace_path_fn=resolve_workspace_path_fn,
        relative_text_fn=relative_text_fn,
        file_tool_error_cls=file_tool_error_cls,
    )


def normalize_file_read_result_request(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    path: str,
    offset: int | None = None,
    limit: int | None = None,
    max_chars: int | None = None,
    file_read_fn: Callable[..., ToolEvent],
    structured_result_from_event_fn: Callable[..., CommandExecutionResult],
) -> Payload:
    return build_file_tools_bridge_payload(
        workspace_root=workspace_root,
        cwd_root=_normalize_cwd_root(workspace_root, cwd_root),
        path=path,
        offset=offset,
        limit=limit,
        max_chars=max_chars,
        file_read_fn=file_read_fn,
        structured_result_from_event_fn=structured_result_from_event_fn,
    )


def normalize_read_file_request(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    file_path: str,
    offset: int | None = None,
    limit: int | None = None,
    mode: str | None = None,
    indentation: dict[str, Any] | None = None,
    resolve_workspace_path_fn: Callable[..., Path],
    relative_text_fn: Callable[[Path, Path], str],
    file_tool_error_cls: type[Exception],
) -> Payload:
    return build_file_tools_bridge_payload(
        workspace_root=workspace_root,
        cwd_root=_normalize_cwd_root(workspace_root, cwd_root),
        file_path=file_path,
        offset=offset,
        limit=limit,
        mode=mode,
        indentation=indentation,
        resolve_workspace_path_fn=resolve_workspace_path_fn,
        relative_text_fn=relative_text_fn,
        file_tool_error_cls=file_tool_error_cls,
    )


def normalize_read_file_result_request(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    file_path: str,
    offset: int | None = None,
    limit: int | None = None,
    mode: str | None = None,
    indentation: dict[str, Any] | None = None,
    read_file_fn: Callable[..., ToolEvent],
    structured_result_from_event_fn: Callable[..., CommandExecutionResult],
) -> Payload:
    return build_file_tools_bridge_payload(
        workspace_root=workspace_root,
        cwd_root=_normalize_cwd_root(workspace_root, cwd_root),
        file_path=file_path,
        offset=offset,
        limit=limit,
        mode=mode,
        indentation=indentation,
        read_file_fn=read_file_fn,
        structured_result_from_event_fn=structured_result_from_event_fn,
    )


__all__ = [
    "normalize_file_list_request",
    "normalize_file_list_result_request",
    "normalize_file_read_request",
    "normalize_file_read_result_request",
    "normalize_file_search_request",
    "normalize_file_search_result_request",
    "normalize_glob_files_request",
    "normalize_glob_files_result_request",
    "normalize_grep_files_request",
    "normalize_grep_files_result_request",
    "normalize_list_dir_request",
    "normalize_list_dir_result_request",
    "normalize_read_file_request",
    "normalize_read_file_result_request",
]

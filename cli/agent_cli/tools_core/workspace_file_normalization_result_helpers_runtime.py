from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core.workspace_file_normalization_request_helpers_runtime import (
    normalize_apply_patch_request,
    normalize_file_list_request,
    normalize_file_read_request,
    normalize_file_search_request,
    normalize_glob_files_request,
    normalize_grep_files_request,
    normalize_list_dir_request,
    normalize_read_file_request,
)
from cli.agent_cli.tools_core.workspace_file_pure_helpers_runtime import (
    Payload,
    build_workspace_file_result_payload,
)


def normalize_apply_patch_result_request(
    *,
    patch_text: str,
    workspace_root: Path,
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    apply_patch_call: Callable[[str], ToolEvent],
) -> Payload:
    return _normalize_result_request(
        normalize_apply_patch_request(
            patch_text=patch_text,
            workspace_root=workspace_root,
        ),
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        fallback_arg_name="apply_patch_call",
        fallback_call=apply_patch_call,
    )


def normalize_glob_files_result_request(
    *,
    workspace_root: Path,
    cwd_root: Path,
    pattern: str,
    path: str | None = None,
    limit: int = 100,
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    glob_files_call: Callable[..., ToolEvent],
) -> Payload:
    return _normalize_result_request(
        normalize_glob_files_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            pattern=pattern,
            path=path,
            limit=limit,
        ),
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        fallback_arg_name="glob_files_call",
        fallback_call=glob_files_call,
    )


def normalize_grep_files_result_request(
    *,
    workspace_root: Path,
    cwd_root: Path,
    pattern: str,
    include: str | None = None,
    path: str | None = None,
    limit: int = 100,
    output_mode: str = "files_with_matches",
    case_insensitive: bool = False,
    file_type: str | None = None,
    line_numbers: bool = False,
    after_context: int | None = None,
    before_context: int | None = None,
    context: int | None = None,
    offset: int = 0,
    multiline: bool = False,
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    grep_files_call: Callable[..., ToolEvent],
) -> Payload:
    return _normalize_result_request(
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
        ),
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        fallback_arg_name="grep_files_call",
        fallback_call=grep_files_call,
    )


def normalize_list_dir_result_request(
    *,
    workspace_root: Path,
    cwd_root: Path,
    dir_path: str | None = None,
    offset: int = 1,
    limit: int = 25,
    depth: int = 2,
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    list_dir_call: Callable[..., ToolEvent],
) -> Payload:
    return _normalize_result_request(
        normalize_list_dir_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            dir_path=dir_path,
            offset=offset,
            limit=limit,
            depth=depth,
        ),
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        fallback_arg_name="list_dir_call",
        fallback_call=list_dir_call,
    )


def normalize_read_file_result_request(
    *,
    workspace_root: Path,
    cwd_root: Path,
    file_path: str,
    offset: int | None = None,
    limit: int | None = None,
    mode: str | None = None,
    indentation: dict[str, Any] | None = None,
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    read_file_call: Callable[..., ToolEvent],
) -> Payload:
    return _normalize_result_request(
        normalize_read_file_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            file_path=file_path,
            offset=offset,
            limit=limit,
            mode=mode,
            indentation=indentation,
        ),
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        fallback_arg_name="read_file_call",
        fallback_call=read_file_call,
    )


def normalize_file_list_result_request(
    *,
    workspace_root: Path,
    cwd_root: Path,
    path: str | None = None,
    limit: int = 50,
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    file_list_call: Callable[..., ToolEvent],
) -> Payload:
    return _normalize_result_request(
        normalize_file_list_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            path=path,
            limit=limit,
        ),
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        fallback_arg_name="file_list_call",
        fallback_call=file_list_call,
    )


def normalize_file_search_result_request(
    *,
    workspace_root: Path,
    cwd_root: Path,
    query: str,
    path: str | None = None,
    limit: int = 20,
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    file_search_call: Callable[..., ToolEvent],
) -> Payload:
    return _normalize_result_request(
        normalize_file_search_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            query=query,
            path=path,
            limit=limit,
        ),
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        fallback_arg_name="file_search_call",
        fallback_call=file_search_call,
    )


def normalize_file_read_result_request(
    *,
    workspace_root: Path,
    cwd_root: Path,
    path: str,
    offset: int | None = None,
    limit: int | None = None,
    max_chars: int | None = None,
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    file_read_call: Callable[..., ToolEvent],
) -> Payload:
    return _normalize_result_request(
        normalize_file_read_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            path=path,
            offset=offset,
            limit=limit,
            max_chars=max_chars,
        ),
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        fallback_arg_name="file_read_call",
        fallback_call=file_read_call,
    )


def _normalize_result_request(
    request_payload: Mapping[str, Any],
    *,
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    fallback_arg_name: str,
    fallback_call: Callable[..., ToolEvent],
) -> Payload:
    return build_workspace_file_result_payload(
        request_payload,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        fallback_arg_name=fallback_arg_name,
        fallback_call=fallback_call,
    )


__all__ = [
    "normalize_apply_patch_result_request",
    "normalize_file_list_result_request",
    "normalize_file_read_result_request",
    "normalize_file_search_result_request",
    "normalize_glob_files_result_request",
    "normalize_grep_files_result_request",
    "normalize_list_dir_result_request",
    "normalize_read_file_result_request",
]

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core import workspace_file_runtime


def glob_files(
    *,
    pattern: str,
    path: Optional[str] = None,
    limit: int = 100,
    workspace_root_factory: Callable[[], Path],
    cwd_root_factory: Callable[[], Path],
) -> ToolEvent:
    return workspace_file_runtime.glob_files(
        workspace_root=workspace_root_factory(),
        cwd_root=cwd_root_factory(),
        pattern=pattern,
        path=path,
        limit=limit,
    )


def glob_files_result(
    *,
    pattern: str,
    path: Optional[str] = None,
    limit: int = 100,
    workspace_root_factory: Callable[[], Path],
    cwd_root_factory: Callable[[], Path],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    glob_files_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return workspace_file_runtime.glob_files_result(
        workspace_root=workspace_root_factory(),
        cwd_root=cwd_root_factory(),
        pattern=pattern,
        path=path,
        limit=limit,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        glob_files_call=glob_files_call,
    )


def grep_files(
    *,
    pattern: str,
    include: Optional[str] = None,
    path: Optional[str] = None,
    limit: int = 100,
    workspace_root_factory: Callable[[], Path],
    cwd_root_factory: Callable[[], Path],
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
    return workspace_file_runtime.grep_files(
        workspace_root=workspace_root_factory(),
        cwd_root=cwd_root_factory(),
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


def grep_files_result(
    *,
    pattern: str,
    include: Optional[str] = None,
    path: Optional[str] = None,
    limit: int = 100,
    workspace_root_factory: Callable[[], Path],
    cwd_root_factory: Callable[[], Path],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    grep_files_call: Callable[..., ToolEvent],
    output_mode: str = "files_with_matches",
    case_insensitive: bool = False,
    file_type: Optional[str] = None,
    line_numbers: bool = False,
    after_context: Optional[int] = None,
    before_context: Optional[int] = None,
    context: Optional[int] = None,
    offset: int = 0,
    multiline: bool = False,
) -> CommandExecutionResult:
    return workspace_file_runtime.grep_files_result(
        workspace_root=workspace_root_factory(),
        cwd_root=cwd_root_factory(),
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


def list_dir(
    *,
    dir_path: Optional[str] = None,
    offset: int = 1,
    limit: int = 25,
    depth: int = 2,
    workspace_root_factory: Callable[[], Path],
    cwd_root_factory: Callable[[], Path],
) -> ToolEvent:
    return workspace_file_runtime.list_dir(
        workspace_root=workspace_root_factory(),
        cwd_root=cwd_root_factory(),
        dir_path=dir_path,
        offset=offset,
        limit=limit,
        depth=depth,
    )


def list_dir_result(
    *,
    dir_path: Optional[str] = None,
    offset: int = 1,
    limit: int = 25,
    depth: int = 2,
    workspace_root_factory: Callable[[], Path],
    cwd_root_factory: Callable[[], Path],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    list_dir_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return workspace_file_runtime.list_dir_result(
        workspace_root=workspace_root_factory(),
        cwd_root=cwd_root_factory(),
        dir_path=dir_path,
        offset=offset,
        limit=limit,
        depth=depth,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        list_dir_call=list_dir_call,
    )


def read_file(
    *,
    file_path: str,
    offset: int | None = None,
    limit: int | None = None,
    mode: str | None = None,
    indentation: Dict[str, Any] | None = None,
    workspace_root_factory: Callable[[], Path],
    cwd_root_factory: Callable[[], Path],
) -> ToolEvent:
    return workspace_file_runtime.read_file(
        workspace_root=workspace_root_factory(),
        cwd_root=cwd_root_factory(),
        file_path=file_path,
        offset=offset,
        limit=limit,
        mode=mode,
        indentation=indentation,
    )


def read_file_result(
    *,
    file_path: str,
    offset: int | None = None,
    limit: int | None = None,
    mode: str | None = None,
    indentation: Dict[str, Any] | None = None,
    workspace_root_factory: Callable[[], Path],
    cwd_root_factory: Callable[[], Path],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    read_file_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return workspace_file_runtime.read_file_result(
        workspace_root=workspace_root_factory(),
        cwd_root=cwd_root_factory(),
        file_path=file_path,
        offset=offset,
        limit=limit,
        mode=mode,
        indentation=indentation,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        read_file_call=read_file_call,
    )


def file_list(
    *,
    path: Optional[str] = None,
    limit: int = 50,
    workspace_root_factory: Callable[[], Path],
    cwd_root_factory: Callable[[], Path],
) -> ToolEvent:
    return workspace_file_runtime.file_list(
        workspace_root=workspace_root_factory(),
        cwd_root=cwd_root_factory(),
        path=path,
        limit=limit,
    )


def file_list_result(
    *,
    path: Optional[str] = None,
    limit: int = 50,
    workspace_root_factory: Callable[[], Path],
    cwd_root_factory: Callable[[], Path],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    file_list_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return workspace_file_runtime.file_list_result(
        workspace_root=workspace_root_factory(),
        cwd_root=cwd_root_factory(),
        path=path,
        limit=limit,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        file_list_call=file_list_call,
    )


def file_search(
    *,
    query: str,
    path: Optional[str] = None,
    limit: int = 20,
    workspace_root_factory: Callable[[], Path],
    cwd_root_factory: Callable[[], Path],
) -> ToolEvent:
    return workspace_file_runtime.file_search(
        workspace_root=workspace_root_factory(),
        cwd_root=cwd_root_factory(),
        query=query,
        path=path,
        limit=limit,
    )


def file_search_result(
    *,
    query: str,
    path: Optional[str] = None,
    limit: int = 20,
    workspace_root_factory: Callable[[], Path],
    cwd_root_factory: Callable[[], Path],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    file_search_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return workspace_file_runtime.file_search_result(
        workspace_root=workspace_root_factory(),
        cwd_root=cwd_root_factory(),
        query=query,
        path=path,
        limit=limit,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        file_search_call=file_search_call,
    )


def file_read(
    *,
    path: str,
    offset: int | None = None,
    limit: int | None = None,
    max_chars: int | None = None,
    workspace_root_factory: Callable[[], Path],
    cwd_root_factory: Callable[[], Path],
) -> ToolEvent:
    return workspace_file_runtime.file_read(
        workspace_root=workspace_root_factory(),
        cwd_root=cwd_root_factory(),
        path=path,
        offset=offset,
        limit=limit,
        max_chars=max_chars,
    )


def file_read_result(
    *,
    path: str,
    offset: int | None = None,
    limit: int | None = None,
    max_chars: int | None = None,
    workspace_root_factory: Callable[[], Path],
    cwd_root_factory: Callable[[], Path],
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    file_read_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    return workspace_file_runtime.file_read_result(
        workspace_root=workspace_root_factory(),
        cwd_root=cwd_root_factory(),
        path=path,
        offset=offset,
        limit=limit,
        max_chars=max_chars,
        call_structured_helper=call_structured_helper,
        result_from_event=result_from_event,
        file_read_call=file_read_call,
    )

from __future__ import annotations

from typing import Any, Optional

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core import tool_library_runtime


def glob_files(
    self: Any,
    pattern: str,
    *,
    path: Optional[str] = None,
    limit: int = 100,
) -> ToolEvent:
    return tool_library_runtime.glob_files(
        self,
        pattern,
        path=path,
        limit=limit,
    )


def glob_files_result(
    self: Any,
    pattern: str,
    *,
    path: Optional[str] = None,
    limit: int = 100,
) -> CommandExecutionResult:
    return tool_library_runtime.glob_files_result(
        self,
        pattern,
        path=path,
        limit=limit,
    )


def grep_files(
    self: Any,
    pattern: str,
    *,
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
    return tool_library_runtime.grep_files(
        self,
        pattern,
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
    self: Any,
    pattern: str,
    *,
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
) -> CommandExecutionResult:
    return tool_library_runtime.grep_files_result(
        self,
        pattern,
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


def list_dir(
    self: Any,
    *,
    dir_path: Optional[str] = None,
    offset: int = 1,
    limit: int = 25,
    depth: int = 2,
) -> ToolEvent:
    return tool_library_runtime.list_dir(
        self,
        dir_path=dir_path,
        offset=offset,
        limit=limit,
        depth=depth,
    )


def list_dir_result(
    self: Any,
    *,
    dir_path: Optional[str] = None,
    offset: int = 1,
    limit: int = 25,
    depth: int = 2,
) -> CommandExecutionResult:
    return tool_library_runtime.list_dir_result(
        self,
        dir_path=dir_path,
        offset=offset,
        limit=limit,
        depth=depth,
    )


def file_list(self: Any, *, path: Optional[str] = None, limit: int = 50) -> ToolEvent:
    return tool_library_runtime.file_list(
        self,
        path=path,
        limit=limit,
    )


def file_list_result(self: Any, *, path: Optional[str] = None, limit: int = 50) -> CommandExecutionResult:
    return tool_library_runtime.file_list_result(
        self,
        path=path,
        limit=limit,
    )


def file_search(
    self: Any,
    query: str,
    *,
    path: Optional[str] = None,
    limit: int = 20,
) -> ToolEvent:
    return tool_library_runtime.file_search(
        self,
        query=query,
        path=path,
        limit=limit,
    )


def file_search_result(
    self: Any,
    query: str,
    *,
    path: Optional[str] = None,
    limit: int = 20,
) -> CommandExecutionResult:
    return tool_library_runtime.file_search_result(
        self,
        query=query,
        path=path,
        limit=limit,
    )


FILE_QUERY_METHOD_BINDINGS = (
    ("glob_files", glob_files),
    ("glob_files_result", glob_files_result),
    ("grep_files", grep_files),
    ("grep_files_result", grep_files_result),
    ("list_dir", list_dir),
    ("list_dir_result", list_dir_result),
    ("file_list", file_list),
    ("file_list_result", file_list_result),
    ("file_search", file_search),
    ("file_search_result", file_search_result),
)

from __future__ import annotations

from typing import Any, Dict, Optional

from cli.agent_cli.tools_core import file_tools_runtime, tool_library_adapter_runtime


def glob_files(
    registry: Any,
    pattern: str,
    *,
    path: Optional[str] = None,
    limit: int = 100,
) -> Any:
    return tool_library_adapter_runtime.call_with_workspace_root(
        file_tools_runtime.glob_files,
        registry,
        pattern=pattern,
        path=path,
        limit=limit,
    )


def glob_files_result(
    registry: Any,
    pattern: str,
    *,
    path: Optional[str] = None,
    limit: int = 100,
) -> Any:
    return tool_library_adapter_runtime.call_structured_with_workspace_root(
        file_tools_runtime.glob_files_result,
        registry,
        fallback_arg="glob_files_call",
        fallback_call=registry.glob_files,
        pattern=pattern,
        path=path,
        limit=limit,
    )


def grep_files(
    registry: Any,
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
) -> Any:
    return tool_library_adapter_runtime.call_with_workspace_root(
        file_tools_runtime.grep_files,
        registry,
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
    registry: Any,
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
) -> Any:
    return tool_library_adapter_runtime.call_structured_with_workspace_root(
        file_tools_runtime.grep_files_result,
        registry,
        fallback_arg="grep_files_call",
        fallback_call=registry.grep_files,
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


def list_dir(
    registry: Any,
    *,
    dir_path: Optional[str] = None,
    offset: int = 1,
    limit: int = 25,
    depth: int = 2,
) -> Any:
    return tool_library_adapter_runtime.call_with_workspace_root(
        file_tools_runtime.list_dir,
        registry,
        dir_path=dir_path,
        offset=offset,
        limit=limit,
        depth=depth,
    )


def list_dir_result(
    registry: Any,
    *,
    dir_path: Optional[str] = None,
    offset: int = 1,
    limit: int = 25,
    depth: int = 2,
) -> Any:
    return tool_library_adapter_runtime.call_structured_with_workspace_root(
        file_tools_runtime.list_dir_result,
        registry,
        fallback_arg="list_dir_call",
        fallback_call=registry.list_dir,
        dir_path=dir_path,
        offset=offset,
        limit=limit,
        depth=depth,
    )


def read_file(
    registry: Any,
    file_path: str,
    *,
    offset: int | None = None,
    limit: int | None = None,
    mode: str | None = None,
    indentation: Dict[str, Any] | None = None,
) -> Any:
    return tool_library_adapter_runtime.call_with_workspace_root(
        file_tools_runtime.read_file,
        registry,
        file_path=file_path,
        offset=offset,
        limit=limit,
        mode=mode,
        indentation=indentation,
    )


def read_file_result(
    registry: Any,
    file_path: str,
    *,
    offset: int | None = None,
    limit: int | None = None,
    mode: str | None = None,
    indentation: Dict[str, Any] | None = None,
) -> Any:
    return tool_library_adapter_runtime.call_structured_with_workspace_root(
        file_tools_runtime.read_file_result,
        registry,
        fallback_arg="read_file_call",
        fallback_call=registry.read_file,
        file_path=file_path,
        offset=offset,
        limit=limit,
        mode=mode,
        indentation=indentation,
    )


def file_list(
    registry: Any,
    *,
    path: Optional[str] = None,
    limit: int = 50,
) -> Any:
    return tool_library_adapter_runtime.call_with_workspace_root(
        file_tools_runtime.file_list,
        registry,
        path=path,
        limit=limit,
    )


def file_list_result(
    registry: Any,
    *,
    path: Optional[str] = None,
    limit: int = 50,
) -> Any:
    return tool_library_adapter_runtime.call_structured_with_workspace_root(
        file_tools_runtime.file_list_result,
        registry,
        fallback_arg="file_list_call",
        fallback_call=registry.file_list,
        path=path,
        limit=limit,
    )


def file_search(
    registry: Any,
    query: str,
    *,
    path: Optional[str] = None,
    limit: int = 20,
) -> Any:
    return tool_library_adapter_runtime.call_with_workspace_root(
        file_tools_runtime.file_search,
        registry,
        query=query,
        path=path,
        limit=limit,
    )


def file_search_result(
    registry: Any,
    query: str,
    *,
    path: Optional[str] = None,
    limit: int = 20,
) -> Any:
    return tool_library_adapter_runtime.call_structured_with_workspace_root(
        file_tools_runtime.file_search_result,
        registry,
        fallback_arg="file_search_call",
        fallback_call=registry.file_search,
        query=query,
        path=path,
        limit=limit,
    )


def file_read(
    registry: Any,
    path: str,
    *,
    offset: int | None = None,
    limit: int | None = None,
    max_chars: int | None = None,
) -> Any:
    return tool_library_adapter_runtime.call_with_workspace_root(
        file_tools_runtime.file_read,
        registry,
        path=path,
        offset=offset,
        limit=limit,
        max_chars=max_chars,
    )


def file_read_result(
    registry: Any,
    path: str,
    *,
    offset: int | None = None,
    limit: int | None = None,
    max_chars: int | None = None,
) -> Any:
    return tool_library_adapter_runtime.call_structured_with_workspace_root(
        file_tools_runtime.file_read_result,
        registry,
        fallback_arg="file_read_call",
        fallback_call=registry.file_read,
        path=path,
        offset=offset,
        limit=limit,
        max_chars=max_chars,
    )

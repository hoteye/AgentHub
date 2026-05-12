from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core import apply_patch_bridge as apply_patch_bridge_module
from cli.agent_cli.tools_core import file_tools_bridge as file_tools_bridge_module


def apply_patch_result(
    *,
    patch_text: str,
    workspace_root: Path,
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    apply_patch_call: Callable[[str], ToolEvent],
) -> CommandExecutionResult:
    structured = call_structured_helper(
        apply_patch_bridge_module,
        "execute_apply_patch_result",
        patch_text=patch_text,
        workspace_root=workspace_root,
    )
    if structured is not None:
        return structured
    return result_from_event(
        "Apply workspace patch.",
        apply_patch_call(patch_text),
        tool_name="apply_patch",
        arguments={"patch": patch_text},
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
    structured = call_structured_helper(
        file_tools_bridge_module,
        "glob_files_result",
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        pattern=pattern,
        path=path,
        limit=limit,
    )
    if structured is not None:
        return structured
    return result_from_event(
        "Find workspace files by pattern.",
        glob_files_call(pattern, path=path, limit=limit),
        tool_name="glob_files",
        arguments={"pattern": pattern, "path": path, "limit": limit},
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
    structured = call_structured_helper(
        file_tools_bridge_module,
        "grep_files_result",
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
    if structured is not None:
        return structured
    return result_from_event(
        "Search workspace file paths.",
        grep_files_call(
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
        ),
        tool_name="grep_files",
        arguments={"pattern": pattern, "include": include, "path": path, "limit": limit},
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
    structured = call_structured_helper(
        file_tools_bridge_module,
        "list_dir_result",
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        dir_path=dir_path,
        offset=offset,
        limit=limit,
        depth=depth,
    )
    if structured is not None:
        return structured
    return result_from_event(
        "List workspace directory.",
        list_dir_call(dir_path=dir_path, offset=offset, limit=limit, depth=depth),
        tool_name="list_dir",
        arguments={"dir_path": dir_path or ".", "offset": offset, "limit": limit, "depth": depth},
    )


def read_file_result(
    *,
    workspace_root: Path,
    cwd_root: Path,
    file_path: str,
    offset: int | None = None,
    limit: int | None = None,
    mode: str | None = None,
    indentation: Dict[str, Any] | None = None,
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    read_file_call: Callable[..., ToolEvent],
) -> CommandExecutionResult:
    structured = call_structured_helper(
        file_tools_bridge_module,
        "read_file_result",
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        file_path=file_path,
        offset=offset,
        limit=limit,
        mode=mode,
        indentation=indentation,
    )
    if structured is not None:
        return structured
    arguments: Dict[str, Any] = {"file_path": file_path}
    if offset is not None:
        arguments["offset"] = offset
    if limit is not None:
        arguments["limit"] = limit
    if mode is not None:
        arguments["mode"] = mode
    if indentation is not None:
        arguments["indentation"] = indentation
    return result_from_event(
        "Read workspace file.",
        read_file_call(file_path, offset=offset, limit=limit, mode=mode, indentation=indentation),
        tool_name="read_file",
        arguments=arguments,
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
    structured = call_structured_helper(
        file_tools_bridge_module,
        "file_list_result",
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        path=path,
        limit=limit,
    )
    if structured is not None:
        return structured
    return result_from_event(
        "List workspace files.",
        file_list_call(path=path, limit=limit),
        tool_name="file_list",
        arguments={"path": path or ".", "limit": limit},
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
    structured = call_structured_helper(
        file_tools_bridge_module,
        "file_search_result",
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        query=query,
        path=path,
        limit=limit,
    )
    if structured is not None:
        return structured
    return result_from_event(
        "Search workspace files.",
        file_search_call(query, path=path, limit=limit),
        tool_name="file_search",
        arguments={"query": query, "path": path, "limit": limit},
    )


def file_read_result(
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
) -> CommandExecutionResult:
    structured = call_structured_helper(
        file_tools_bridge_module,
        "file_read_result",
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        path=path,
        offset=offset,
        limit=limit,
        max_chars=max_chars,
    )
    if structured is not None:
        return structured
    arguments: Dict[str, Any] = {"path": path}
    if offset is not None:
        arguments["offset"] = offset
    if limit is not None:
        arguments["limit"] = limit
    if max_chars is not None:
        arguments["max_chars"] = max_chars
    return result_from_event(
        "Read workspace file.",
        file_read_call(path, offset=offset, limit=limit, max_chars=max_chars),
        tool_name="file_read",
        arguments=arguments,
    )

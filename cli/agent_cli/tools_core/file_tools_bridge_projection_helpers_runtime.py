from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from cli.agent_cli.models import (
    CommandExecutionResult,
    ToolEvent,
    generic_tool_call_item_events,
    tool_event_result_text,
)
from cli.agent_cli.tools_core import file_read_runtime as file_read_helpers
from cli.agent_cli.tools_core import file_tools_bridge_runtime_helpers
from cli.agent_cli.tools_core.file_tools_bridge_pure_helpers_runtime import (
    project_file_tools_bridge_payload,
)


def structured_result_from_event(
    *,
    assistant_text: str,
    event: ToolEvent,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> CommandExecutionResult:
    result_text = tool_event_result_text(event)
    return CommandExecutionResult(
        assistant_text=str(result_text or assistant_text or ""),
        tool_events=[event],
        item_events=generic_tool_call_item_events(
            tool_name=str(tool_name or event.name or "").strip(),
            arguments=dict(arguments or {}) or None,
            ok=bool(event.ok),
            summary=str(event.summary or ""),
            structured_content=dict(event.payload or {}),
        ),
    )


def _event_result(
    *,
    assistant_text: str,
    tool_name: str,
    arguments: dict[str, Any],
    event_call: Callable[[], ToolEvent],
    structured_result_from_event_fn: Callable[..., CommandExecutionResult],
) -> CommandExecutionResult:
    return structured_result_from_event_fn(
        assistant_text=assistant_text,
        event=event_call(),
        tool_name=tool_name,
        arguments=arguments,
    )


def project_glob_files_event(payload: Mapping[str, Any]) -> ToolEvent:
    return project_file_tools_bridge_payload(file_tools_bridge_runtime_helpers.execute_glob_files, payload)


def build_glob_files_result(
    *,
    workspace_root: Path,
    cwd_root: Path,
    pattern: str,
    path: str | None = None,
    limit: int = 100,
    glob_files_fn: Callable[..., ToolEvent],
    structured_result_from_event_fn: Callable[..., CommandExecutionResult],
) -> CommandExecutionResult:
    return _event_result(
        assistant_text="Find workspace files by pattern.",
        tool_name="glob_files",
        arguments={
            "pattern": str(pattern or "").strip(),
            "path": str(path).strip() if path is not None else None,
            "limit": int(limit),
        },
        event_call=lambda: glob_files_fn(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            pattern=pattern,
            path=path,
            limit=limit,
        ),
        structured_result_from_event_fn=structured_result_from_event_fn,
    )


def project_glob_files_result(payload: Mapping[str, Any]) -> CommandExecutionResult:
    return project_file_tools_bridge_payload(build_glob_files_result, payload)


def project_grep_files_event(payload: Mapping[str, Any]) -> ToolEvent:
    return project_file_tools_bridge_payload(file_tools_bridge_runtime_helpers.execute_grep_files, payload)


def build_grep_files_result(
    *,
    workspace_root: Path,
    cwd_root: Path,
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
) -> CommandExecutionResult:
    return _event_result(
        assistant_text="Search workspace file paths.",
        tool_name="grep_files",
        arguments={
            "pattern": str(pattern or "").strip(),
            "include": str(include or "").strip() or None,
            "path": str(path).strip() if path is not None else None,
            "limit": int(limit),
        },
        event_call=lambda: grep_files_fn(
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
        structured_result_from_event_fn=structured_result_from_event_fn,
    )


def project_grep_files_result(payload: Mapping[str, Any]) -> CommandExecutionResult:
    return project_file_tools_bridge_payload(build_grep_files_result, payload)


def project_list_dir_event(payload: Mapping[str, Any]) -> ToolEvent:
    return project_file_tools_bridge_payload(file_tools_bridge_runtime_helpers.execute_list_dir, payload)


def build_list_dir_result(
    *,
    workspace_root: Path,
    cwd_root: Path,
    dir_path: str | None = None,
    offset: int = 1,
    limit: int = 25,
    depth: int = 2,
    list_dir_fn: Callable[..., ToolEvent],
    structured_result_from_event_fn: Callable[..., CommandExecutionResult],
) -> CommandExecutionResult:
    return _event_result(
        assistant_text="List workspace directory.",
        tool_name="list_dir",
        arguments={
            "dir_path": str(dir_path).strip() if dir_path is not None else ".",
            "offset": int(offset),
            "limit": int(limit),
            "depth": int(depth),
        },
        event_call=lambda: list_dir_fn(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            dir_path=dir_path,
            offset=offset,
            limit=limit,
            depth=depth,
        ),
        structured_result_from_event_fn=structured_result_from_event_fn,
    )


def project_list_dir_result(payload: Mapping[str, Any]) -> CommandExecutionResult:
    return project_file_tools_bridge_payload(build_list_dir_result, payload)


def project_file_list_event(payload: Mapping[str, Any]) -> ToolEvent:
    return project_file_tools_bridge_payload(file_tools_bridge_runtime_helpers.execute_file_list, payload)


def build_file_list_result(
    *,
    workspace_root: Path,
    cwd_root: Path,
    path: str | None = None,
    limit: int = 50,
    file_list_fn: Callable[..., ToolEvent],
    structured_result_from_event_fn: Callable[..., CommandExecutionResult],
) -> CommandExecutionResult:
    return _event_result(
        assistant_text="List workspace files.",
        tool_name="file_list",
        arguments={"path": str(path or ".").strip() or ".", "limit": int(limit)},
        event_call=lambda: file_list_fn(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            path=path,
            limit=limit,
        ),
        structured_result_from_event_fn=structured_result_from_event_fn,
    )


def project_file_list_result(payload: Mapping[str, Any]) -> CommandExecutionResult:
    return project_file_tools_bridge_payload(build_file_list_result, payload)


def project_file_search_event(payload: Mapping[str, Any]) -> ToolEvent:
    return project_file_tools_bridge_payload(file_tools_bridge_runtime_helpers.execute_file_search, payload)


def build_file_search_result(
    *,
    workspace_root: Path,
    cwd_root: Path,
    query: str,
    path: str | None = None,
    limit: int = 20,
    file_search_fn: Callable[..., ToolEvent],
    structured_result_from_event_fn: Callable[..., CommandExecutionResult],
) -> CommandExecutionResult:
    return _event_result(
        assistant_text="Search workspace files.",
        tool_name="file_search",
        arguments={
            "query": str(query or "").strip(),
            "path": str(path).strip() if path is not None else None,
            "limit": int(limit),
        },
        event_call=lambda: file_search_fn(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            query=query,
            path=path,
            limit=limit,
        ),
        structured_result_from_event_fn=structured_result_from_event_fn,
    )


def project_file_search_result(payload: Mapping[str, Any]) -> CommandExecutionResult:
    return project_file_tools_bridge_payload(build_file_search_result, payload)


def project_file_read_event(payload: Mapping[str, Any]) -> ToolEvent:
    return project_file_tools_bridge_payload(file_tools_bridge_runtime_helpers.execute_file_read, payload)


def build_file_read_result(
    *,
    workspace_root: Path,
    cwd_root: Path,
    path: str,
    offset: int | None = None,
    limit: int | None = None,
    max_chars: int | None = None,
    file_read_fn: Callable[..., ToolEvent],
    structured_result_from_event_fn: Callable[..., CommandExecutionResult],
) -> CommandExecutionResult:
    return file_read_helpers.file_read_result(
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        path=path,
        offset=offset,
        limit=limit,
        max_chars=max_chars,
        file_read_fn=file_read_fn,
        structured_result_from_event_fn=structured_result_from_event_fn,
    )


def project_file_read_result(payload: Mapping[str, Any]) -> CommandExecutionResult:
    return project_file_tools_bridge_payload(build_file_read_result, payload)


def project_read_file_event(payload: Mapping[str, Any]) -> ToolEvent:
    return project_file_tools_bridge_payload(file_tools_bridge_runtime_helpers.execute_read_file, payload)


def build_read_file_result(
    *,
    workspace_root: Path,
    cwd_root: Path,
    file_path: str,
    offset: int | None = None,
    limit: int | None = None,
    mode: str | None = None,
    indentation: dict[str, Any] | None = None,
    read_file_fn: Callable[..., ToolEvent],
    structured_result_from_event_fn: Callable[..., CommandExecutionResult],
) -> CommandExecutionResult:
    return file_read_helpers.read_file_result(
        workspace_root=workspace_root,
        cwd_root=cwd_root,
        file_path=file_path,
        offset=offset,
        limit=limit,
        mode=mode,
        indentation=indentation,
        read_file_fn=read_file_fn,
        structured_result_from_event_fn=structured_result_from_event_fn,
    )


def project_read_file_result(payload: Mapping[str, Any]) -> CommandExecutionResult:
    return project_file_tools_bridge_payload(build_read_file_result, payload)


__all__ = [
    "project_file_list_event",
    "project_file_list_result",
    "project_file_read_event",
    "project_file_read_result",
    "project_file_search_event",
    "project_file_search_result",
    "project_glob_files_event",
    "project_glob_files_result",
    "project_grep_files_event",
    "project_grep_files_result",
    "project_list_dir_event",
    "project_list_dir_result",
    "project_read_file_event",
    "project_read_file_result",
    "structured_result_from_event",
]

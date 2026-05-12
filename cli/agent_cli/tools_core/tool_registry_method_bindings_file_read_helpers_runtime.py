from __future__ import annotations

from typing import Any, Dict

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core import tool_library_runtime, tool_registry_file_guard_runtime


def read_file(
    self: Any,
    file_path: str,
    *,
    offset: int | None = None,
    limit: int | None = None,
    mode: str | None = None,
    indentation: Dict[str, Any] | None = None,
) -> ToolEvent:
    event = tool_library_runtime.read_file(
        self,
        file_path=file_path,
        offset=offset,
        limit=limit,
        mode=mode,
        indentation=indentation,
    )
    _remember_full_file_read(
        self,
        event=event,
        requested_path=file_path,
        offset=offset,
        limit=limit,
    )
    return event


def read_file_result(
    self: Any,
    file_path: str,
    *,
    offset: int | None = None,
    limit: int | None = None,
    mode: str | None = None,
    indentation: Dict[str, Any] | None = None,
) -> CommandExecutionResult:
    result = tool_library_runtime.read_file_result(
        self,
        file_path=file_path,
        offset=offset,
        limit=limit,
        mode=mode,
        indentation=indentation,
    )
    if result.tool_events:
        _remember_full_file_read(
            self,
            event=result.tool_events[-1],
            requested_path=file_path,
            offset=offset,
            limit=limit,
        )
    return result


def file_read(
    self: Any,
    path: str,
    *,
    offset: int | None = None,
    limit: int | None = None,
    max_chars: int | None = None,
) -> ToolEvent:
    event = tool_library_runtime.file_read(
        self,
        path=path,
        offset=offset,
        limit=limit,
        max_chars=max_chars,
    )
    _remember_full_file_read(
        self,
        event=event,
        requested_path=path,
        offset=offset,
        limit=limit,
        max_chars=max_chars,
    )
    return event


def file_read_result(
    self: Any,
    path: str,
    *,
    offset: int | None = None,
    limit: int | None = None,
    max_chars: int | None = None,
) -> CommandExecutionResult:
    result = tool_library_runtime.file_read_result(
        self,
        path=path,
        offset=offset,
        limit=limit,
        max_chars=max_chars,
    )
    if result.tool_events:
        _remember_full_file_read(
            self,
            event=result.tool_events[-1],
            requested_path=path,
            offset=offset,
            limit=limit,
            max_chars=max_chars,
        )
    return result


def _normalize_workspace_file_path(self: Any, raw_path: str) -> str:
    return tool_registry_file_guard_runtime.normalize_workspace_file_path(self, raw_path)


def _remember_full_file_read(
    self: Any,
    *,
    event: ToolEvent,
    requested_path: str,
    offset: int | None,
    limit: int | None,
    max_chars: int | None = None,
) -> None:
    tool_registry_file_guard_runtime.remember_full_file_read(
        self,
        event=event,
        requested_path=requested_path,
        offset=offset,
        limit=limit,
        max_chars=max_chars,
    )


FILE_READ_METHOD_BINDINGS = (
    ("read_file", read_file),
    ("read_file_result", read_file_result),
    ("file_read", file_read),
    ("file_read_result", file_read_result),
)

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core.workspace_file_normalization_helpers_runtime import (
    normalize_file_read_request,
    normalize_file_read_result_request,
    normalize_read_file_request,
    normalize_read_file_result_request,
)
from cli.agent_cli.tools_core.workspace_file_projection_helpers_runtime import (
    project_file_read_event,
    project_file_read_result,
    project_read_file_event,
    project_read_file_result,
)


def read_file(
    *,
    workspace_root: Path,
    cwd_root: Path,
    file_path: str,
    offset: int | None = None,
    limit: int | None = None,
    mode: str | None = None,
    indentation: Dict[str, Any] | None = None,
) -> ToolEvent:
    return project_read_file_event(
        normalize_read_file_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            file_path=file_path,
            offset=offset,
            limit=limit,
            mode=mode,
            indentation=indentation,
        )
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
    return project_read_file_result(
        normalize_read_file_result_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            file_path=file_path,
            offset=offset,
            limit=limit,
            mode=mode,
            indentation=indentation,
            call_structured_helper=call_structured_helper,
            result_from_event=result_from_event,
            read_file_call=read_file_call,
        )
    )


def file_read(
    *,
    workspace_root: Path,
    cwd_root: Path,
    path: str,
    offset: int | None = None,
    limit: int | None = None,
    max_chars: int | None = None,
) -> ToolEvent:
    return project_file_read_event(
        normalize_file_read_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            path=path,
            offset=offset,
            limit=limit,
            max_chars=max_chars,
        )
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
    return project_file_read_result(
        normalize_file_read_result_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            path=path,
            offset=offset,
            limit=limit,
            max_chars=max_chars,
            call_structured_helper=call_structured_helper,
            result_from_event=result_from_event,
            file_read_call=file_read_call,
        )
    )


__all__ = [
    "read_file",
    "read_file_result",
    "file_read",
    "file_read_result",
]

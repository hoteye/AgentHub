from __future__ import annotations

from pathlib import Path
from typing import Any

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core import (
    file_tools_bridge_normalization_helpers_runtime,
    file_tools_bridge_projection_helpers_runtime,
)
from cli.agent_cli.tools_core import (
    file_tools_bridge_shared_runtime as file_tools_bridge_shared_runtime_service,
)


def file_read(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    path: str,
    offset: int | None = None,
    limit: int | None = None,
    max_chars: int | None = None,
) -> ToolEvent:
    return file_tools_bridge_projection_helpers_runtime.project_file_read_event(
        file_tools_bridge_normalization_helpers_runtime.normalize_file_read_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            path=path,
            offset=offset,
            limit=limit,
            max_chars=max_chars,
            resolve_workspace_path_fn=file_tools_bridge_shared_runtime_service.resolve_workspace_path,
            relative_text_fn=file_tools_bridge_shared_runtime_service.relative_text,
            file_tool_error_cls=file_tools_bridge_shared_runtime_service.FileToolError,
        )
    )


def read_file(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    file_path: str,
    offset: int | None = None,
    limit: int | None = None,
    mode: str | None = None,
    indentation: dict[str, Any] | None = None,
) -> ToolEvent:
    return file_tools_bridge_projection_helpers_runtime.project_read_file_event(
        file_tools_bridge_normalization_helpers_runtime.normalize_read_file_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            file_path=file_path,
            offset=offset,
            limit=limit,
            mode=mode,
            indentation=indentation,
            resolve_workspace_path_fn=file_tools_bridge_shared_runtime_service.resolve_workspace_path,
            relative_text_fn=file_tools_bridge_shared_runtime_service.relative_text,
            file_tool_error_cls=file_tools_bridge_shared_runtime_service.FileToolError,
        )
    )


def file_read_result(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    path: str,
    offset: int | None = None,
    limit: int | None = None,
    max_chars: int | None = None,
) -> CommandExecutionResult:
    return file_tools_bridge_projection_helpers_runtime.project_file_read_result(
        file_tools_bridge_normalization_helpers_runtime.normalize_file_read_result_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            path=path,
            offset=offset,
            limit=limit,
            max_chars=max_chars,
            file_read_fn=file_read,
            structured_result_from_event_fn=file_tools_bridge_shared_runtime_service.structured_result_from_event,
        )
    )


def read_file_result(
    *,
    workspace_root: Path,
    cwd_root: Path | None = None,
    file_path: str,
    offset: int | None = None,
    limit: int | None = None,
    mode: str | None = None,
    indentation: dict[str, Any] | None = None,
) -> CommandExecutionResult:
    return file_tools_bridge_projection_helpers_runtime.project_read_file_result(
        file_tools_bridge_normalization_helpers_runtime.normalize_read_file_result_request(
            workspace_root=workspace_root,
            cwd_root=cwd_root,
            file_path=file_path,
            offset=offset,
            limit=limit,
            mode=mode,
            indentation=indentation,
            read_file_fn=read_file,
            structured_result_from_event_fn=file_tools_bridge_shared_runtime_service.structured_result_from_event,
        )
    )


__all__ = [
    "file_read",
    "file_read_result",
    "read_file",
    "read_file_result",
]

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core import (
    file_tools_bridge_projection_helpers_runtime,
    file_tools_bridge_runtime_helpers,
)


class FileToolError(ValueError):
    pass


GLOB_DEFAULT_LIMIT = 100
GLOB_MAX_LIMIT = 2000
GREP_DEFAULT_LIMIT = 100
GREP_MAX_LIMIT = 2000
LIST_DEFAULT_OFFSET = 1
LIST_DEFAULT_LIMIT = 25
LIST_DEFAULT_DEPTH = 2


def structured_result_from_event(
    *,
    assistant_text: str,
    event: ToolEvent,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
) -> CommandExecutionResult:
    return file_tools_bridge_projection_helpers_runtime.structured_result_from_event(
        assistant_text=assistant_text,
        event=event,
        tool_name=tool_name,
        arguments=arguments,
    )


def resolve_workspace_path(
    workspace_root: Path,
    raw_path: str | None,
    *,
    default_root: Path | None = None,
) -> Path:
    return file_tools_bridge_runtime_helpers.resolve_workspace_path(
        workspace_root=workspace_root,
        raw_path=raw_path,
        default_root=default_root,
        file_tool_error_cls=FileToolError,
    )


def relative_text(path: Path, workspace_root: Path) -> str:
    return file_tools_bridge_runtime_helpers.relative_text(path, workspace_root)


__all__ = [
    "FileToolError",
    "GLOB_DEFAULT_LIMIT",
    "GLOB_MAX_LIMIT",
    "GREP_DEFAULT_LIMIT",
    "GREP_MAX_LIMIT",
    "LIST_DEFAULT_DEPTH",
    "LIST_DEFAULT_LIMIT",
    "LIST_DEFAULT_OFFSET",
    "relative_text",
    "resolve_workspace_path",
    "shutil",
    "structured_result_from_event",
    "subprocess",
]

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core.apply_patch_bridge import execute_apply_patch
from cli.agent_cli.tools_core.file_tools_bridge import glob_files as execute_glob_files
from cli.agent_cli.tools_core.file_tools_bridge import grep_files as execute_grep_files
from cli.agent_cli.tools_core.file_tools_bridge import file_list as execute_file_list
from cli.agent_cli.tools_core.file_tools_bridge import file_read as execute_file_read
from cli.agent_cli.tools_core.file_tools_bridge import file_search as execute_file_search
from cli.agent_cli.tools_core.file_tools_bridge import list_dir as execute_list_dir
from cli.agent_cli.tools_core.file_tools_bridge import read_file as execute_read_file
from cli.agent_cli.tools_core.workspace_file_pure_helpers_runtime import (
    project_workspace_file_payload,
)
from cli.agent_cli.tools_core.workspace_file_result_runtime import (
    apply_patch_result as _apply_patch_result,
    file_list_result as _file_list_result,
    file_read_result as _file_read_result,
    file_search_result as _file_search_result,
    glob_files_result as _glob_files_result,
    grep_files_result as _grep_files_result,
    list_dir_result as _list_dir_result,
    read_file_result as _read_file_result,
)


def project_apply_patch_event(payload: Mapping[str, Any]) -> ToolEvent:
    return project_workspace_file_payload(execute_apply_patch, payload)


def project_apply_patch_result(payload: Mapping[str, Any]) -> CommandExecutionResult:
    return project_workspace_file_payload(_apply_patch_result, payload)


def project_glob_files_event(payload: Mapping[str, Any]) -> ToolEvent:
    return project_workspace_file_payload(execute_glob_files, payload)


def project_glob_files_result(payload: Mapping[str, Any]) -> CommandExecutionResult:
    return project_workspace_file_payload(_glob_files_result, payload)


def project_grep_files_event(payload: Mapping[str, Any]) -> ToolEvent:
    return project_workspace_file_payload(execute_grep_files, payload)


def project_grep_files_result(payload: Mapping[str, Any]) -> CommandExecutionResult:
    return project_workspace_file_payload(_grep_files_result, payload)


def project_list_dir_event(payload: Mapping[str, Any]) -> ToolEvent:
    return project_workspace_file_payload(execute_list_dir, payload)


def project_list_dir_result(payload: Mapping[str, Any]) -> CommandExecutionResult:
    return project_workspace_file_payload(_list_dir_result, payload)


def project_read_file_event(payload: Mapping[str, Any]) -> ToolEvent:
    return project_workspace_file_payload(execute_read_file, payload)


def project_read_file_result(payload: Mapping[str, Any]) -> CommandExecutionResult:
    return project_workspace_file_payload(_read_file_result, payload)


def project_file_list_event(payload: Mapping[str, Any]) -> ToolEvent:
    return project_workspace_file_payload(execute_file_list, payload)


def project_file_list_result(payload: Mapping[str, Any]) -> CommandExecutionResult:
    return project_workspace_file_payload(_file_list_result, payload)


def project_file_search_event(payload: Mapping[str, Any]) -> ToolEvent:
    return project_workspace_file_payload(execute_file_search, payload)


def project_file_search_result(payload: Mapping[str, Any]) -> CommandExecutionResult:
    return project_workspace_file_payload(_file_search_result, payload)


def project_file_read_event(payload: Mapping[str, Any]) -> ToolEvent:
    return project_workspace_file_payload(execute_file_read, payload)


def project_file_read_result(payload: Mapping[str, Any]) -> CommandExecutionResult:
    return project_workspace_file_payload(_file_read_result, payload)


__all__ = [
    "project_apply_patch_event",
    "project_apply_patch_result",
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
]

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core import workspace_file_runtime
from cli.agent_cli.tools_core.project_loader import find_project_root, json_safe, load_project_tool_module


class ApplyPatchBridgeCompat:
    @staticmethod
    def execute_apply_patch(*, patch_text: str, workspace_root: Path) -> ToolEvent:
        return workspace_file_runtime.apply_patch(
            patch_text=patch_text,
            workspace_root=workspace_root,
        )

    @staticmethod
    def execute_apply_patch_result(
        *,
        patch_text: str,
        workspace_root: Path,
        call_structured_helper: Callable[..., CommandExecutionResult | None],
        result_from_event: Callable[..., CommandExecutionResult],
        apply_patch_call: Callable[[str], ToolEvent],
    ) -> CommandExecutionResult:
        return workspace_file_runtime.apply_patch_result(
            patch_text=patch_text,
            workspace_root=workspace_root,
            call_structured_helper=call_structured_helper,
            result_from_event=result_from_event,
            apply_patch_call=apply_patch_call,
        )


def find_tools_project_root(*, tools_dir: Path) -> Path:
    return find_project_root(tools_dir)


def json_safe_value(value: Any) -> Any:
    return json_safe(value)


def load_project_tool(module_name: str, *, project_root: Path, tools_module_file: Path) -> Any:
    return load_project_tool_module(
        module_name,
        project_root=project_root,
        tools_module_file=tools_module_file,
    )

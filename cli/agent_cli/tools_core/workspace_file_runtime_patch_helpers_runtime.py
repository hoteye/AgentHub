from __future__ import annotations

from pathlib import Path
from typing import Callable

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core.workspace_file_normalization_helpers_runtime import (
    normalize_apply_patch_request,
    normalize_apply_patch_result_request,
)
from cli.agent_cli.tools_core.workspace_file_projection_helpers_runtime import (
    project_apply_patch_event,
    project_apply_patch_result,
)


def apply_patch(*, patch_text: str, workspace_root: Path) -> ToolEvent:
    return project_apply_patch_event(
        normalize_apply_patch_request(
            patch_text=patch_text,
            workspace_root=workspace_root,
        )
    )


def apply_patch_result(
    *,
    patch_text: str,
    workspace_root: Path,
    call_structured_helper: Callable[..., CommandExecutionResult | None],
    result_from_event: Callable[..., CommandExecutionResult],
    apply_patch_call: Callable[[str], ToolEvent],
) -> CommandExecutionResult:
    return project_apply_patch_result(
        normalize_apply_patch_result_request(
            patch_text=patch_text,
            workspace_root=workspace_root,
            call_structured_helper=call_structured_helper,
            result_from_event=result_from_event,
            apply_patch_call=apply_patch_call,
        )
    )


__all__ = [
    "apply_patch",
    "apply_patch_result",
]

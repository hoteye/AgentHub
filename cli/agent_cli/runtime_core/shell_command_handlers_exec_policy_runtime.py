from __future__ import annotations

from typing import Any

from cli.agent_cli.debug_timeline import json_ready, log_timeline, timeline_debug_enabled
from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.runtime_core import (
    shell_command_handlers_exec_helpers_apply_patch_runtime,
    shell_command_handlers_exec_helpers_blocking_runtime,
    shell_command_handlers_exec_helpers_execution_runtime,
    shell_command_handlers_pure_helpers_runtime,
)


def _tool_trace(stage: str, **payload: Any) -> None:
    if not timeline_debug_enabled():
        return
    log_timeline(stage, **json_ready(payload))


def _active_run_text(runtime: Any) -> str:
    return shell_command_handlers_exec_helpers_blocking_runtime.active_run_text(runtime)


def _user_explicitly_forbids_tool(user_text: str, tool_name: str) -> bool:
    return shell_command_handlers_exec_helpers_blocking_runtime.user_explicitly_forbids_tool(
        user_text, tool_name
    )


def _blocked_exec_command_refusal_text(command_text: str) -> str:
    return shell_command_handlers_exec_helpers_blocking_runtime.blocked_exec_command_refusal_text(
        command_text,
        looks_like_inline_apply_patch=(
            shell_command_handlers_exec_helpers_apply_patch_runtime.command_looks_like_inline_apply_patch
        ),
    )


def _blocked_exec_command_item_events(refusal_text: str) -> list[dict[str, Any]]:
    return shell_command_handlers_exec_helpers_blocking_runtime.blocked_exec_command_item_events(
        refusal_text
    )


def _blocked_exec_command_result(
    runtime: Any, *, command_text: str
) -> CommandExecutionResult | None:
    return shell_command_handlers_exec_helpers_blocking_runtime.blocked_exec_command_result(
        runtime,
        command_text=command_text,
        looks_like_inline_apply_patch=(
            shell_command_handlers_exec_helpers_apply_patch_runtime.command_looks_like_inline_apply_patch
        ),
        tool_trace=_tool_trace,
    )


def _codex_read_only_exec_failure_result(
    *,
    request: shell_command_handlers_pure_helpers_runtime.ExecCommandRequest,
    policy_payload: dict[str, Any],
) -> CommandExecutionResult:
    return (
        shell_command_handlers_exec_helpers_execution_runtime.codex_read_only_exec_failure_result(
            request=request,
            policy_payload=policy_payload,
        )
    )


def _request_shell_approval_for_exec(runtime: Any, command: str, **kwargs: Any) -> ToolEvent:
    return shell_command_handlers_exec_helpers_execution_runtime.request_shell_approval_for_exec(
        runtime, command, **kwargs
    )

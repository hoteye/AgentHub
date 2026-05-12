from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from cli.agent_cli.models import (
    CommandExecutionResult,
    ToolEvent,
)
from cli.agent_cli.runtime_core import shell_command_handlers_exec_helpers_runtime
from cli.agent_cli.runtime_core import shell_command_handlers_helpers
from cli.agent_cli.runtime_core import shell_command_handlers_shell_helpers_runtime
from cli.agent_cli.slash_parser import SlashInvocation


def handle_shell_command(
    runtime: Any,
    *,
    name: str,
    arg_text: str,
    slash_invocation: SlashInvocation | None = None,
    compact_arguments: Callable[[Dict[str, Any]], Dict[str, Any]],
    int_option: Callable[..., int | None],
    bool_option: Callable[..., bool],
    error_event: Callable[..., ToolEvent],
    error_result: Callable[..., CommandExecutionResult],
    text_only_result: Callable[[str], CommandExecutionResult],
    single_event_result: Callable[..., CommandExecutionResult],
    approval_request_text: Callable[[str, ToolEvent], str],
) -> Optional[Tuple[str, List[ToolEvent]] | CommandExecutionResult]:
    if name == "shell":
        return shell_command_handlers_shell_helpers_runtime.handle_shell_alias_command(
            runtime,
            arg_text=arg_text,
            single_event_result=single_event_result,
            approval_request_text=approval_request_text,
            error_event=error_event,
        )

    if name == "exec_command":
        return shell_command_handlers_exec_helpers_runtime.handle_exec_command(
            runtime,
            arg_text=arg_text,
            slash_invocation=slash_invocation,
            compact_arguments=compact_arguments,
            int_option=int_option,
            bool_option=bool_option,
            error_event=error_event,
            error_result=error_result,
            text_only_result=text_only_result,
            approval_request_text=approval_request_text,
        )

    if name == "write_stdin":
        return shell_command_handlers_helpers.handle_write_stdin_command(
            runtime,
            arg_text=arg_text,
            slash_invocation=slash_invocation,
            compact_arguments=compact_arguments,
            int_option=int_option,
            error_event=error_event,
            error_result=error_result,
            text_only_result=text_only_result,
        )

    return None

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.slash_parser import SlashInvocation
from cli.agent_cli.runtime_core import (
    thread_commands_target_runtime_command_helpers_runtime as command_helpers_runtime,
)
from cli.agent_cli.runtime_core import (
    thread_commands_target_runtime_wait_helpers_runtime as wait_helpers_runtime,
)

CommandHandlerResult = Optional[Tuple[str, List[ToolEvent]] | CommandExecutionResult]


def handle_send_input_command(
    *,
    runtime: Any,
    arg_text: str,
    parse_json_tool_arg: Callable[[str], Dict[str, Any]],
    bool_option: Callable[..., bool],
    text_only_result: Callable[[str], CommandExecutionResult],
    error_result: Callable[..., CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
    slash_invocation: SlashInvocation | None = None,
) -> CommandHandlerResult:
    return command_helpers_runtime.handle_send_input_command(
        runtime=runtime,
        arg_text=arg_text,
        parse_json_tool_arg=parse_json_tool_arg,
        bool_option=bool_option,
        text_only_result=text_only_result,
        error_result=error_result,
        error_event=error_event,
        slash_invocation=slash_invocation,
    )


def handle_resume_agent_command(
    *,
    runtime: Any,
    arg_text: str,
    parse_json_tool_arg: Callable[[str], Dict[str, Any]],
    text_only_result: Callable[[str], CommandExecutionResult],
    error_result: Callable[..., CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
    slash_invocation: SlashInvocation | None = None,
) -> CommandHandlerResult:
    return command_helpers_runtime.handle_resume_agent_command(
        runtime=runtime,
        arg_text=arg_text,
        parse_json_tool_arg=parse_json_tool_arg,
        text_only_result=text_only_result,
        error_result=error_result,
        error_event=error_event,
        slash_invocation=slash_invocation,
    )


def handle_wait_agent_command(
    *,
    runtime: Any,
    arg_text: str,
    parse_json_tool_arg: Callable[[str], Dict[str, Any]],
    int_option: Callable[..., int | None],
    text_only_result: Callable[[str], CommandExecutionResult],
    error_result: Callable[..., CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
    slash_invocation: SlashInvocation | None = None,
) -> CommandHandlerResult:
    return wait_helpers_runtime.handle_wait_agent_command(
        runtime=runtime,
        arg_text=arg_text,
        parse_json_tool_arg=parse_json_tool_arg,
        int_option=int_option,
        text_only_result=text_only_result,
        error_result=error_result,
        error_event=error_event,
        slash_invocation=slash_invocation,
    )


def handle_close_agent_command(
    *,
    runtime: Any,
    arg_text: str,
    parse_json_tool_arg: Callable[[str], Dict[str, Any]],
    text_only_result: Callable[[str], CommandExecutionResult],
    error_result: Callable[..., CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
    slash_invocation: SlashInvocation | None = None,
) -> CommandHandlerResult:
    return command_helpers_runtime.handle_close_agent_command(
        runtime=runtime,
        arg_text=arg_text,
        parse_json_tool_arg=parse_json_tool_arg,
        text_only_result=text_only_result,
        error_result=error_result,
        error_event=error_event,
        slash_invocation=slash_invocation,
    )


def handle_agent_workflow_command(
    *,
    runtime: Any,
    arg_text: str,
    parse_json_tool_arg: Callable[[str], Dict[str, Any]],
    int_option: Callable[..., int | None],
    text_only_result: Callable[[str], CommandExecutionResult],
    error_result: Callable[..., CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
    slash_invocation: SlashInvocation | None = None,
) -> CommandHandlerResult:
    return command_helpers_runtime.handle_agent_workflow_command(
        runtime=runtime,
        arg_text=arg_text,
        parse_json_tool_arg=parse_json_tool_arg,
        int_option=int_option,
        text_only_result=text_only_result,
        error_result=error_result,
        error_event=error_event,
        slash_invocation=slash_invocation,
    )


def handle_recover_agent_command(
    *,
    runtime: Any,
    arg_text: str,
    parse_json_tool_arg: Callable[[str], Dict[str, Any]],
    text_only_result: Callable[[str], CommandExecutionResult],
    error_result: Callable[..., CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
    slash_invocation: SlashInvocation | None = None,
) -> CommandHandlerResult:
    return command_helpers_runtime.handle_recover_agent_command(
        runtime=runtime,
        arg_text=arg_text,
        parse_json_tool_arg=parse_json_tool_arg,
        text_only_result=text_only_result,
        error_result=error_result,
        error_event=error_event,
        slash_invocation=slash_invocation,
    )


def handle_target_command(
    runtime: Any,
    *,
    name: str,
    arg_text: str,
    parse_json_tool_arg: Callable[[str], Dict[str, Any]],
    int_option: Callable[..., int | None],
    bool_option: Callable[..., bool],
    text_only_result: Callable[[str], CommandExecutionResult],
    error_result: Callable[..., CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
    slash_invocation: SlashInvocation | None = None,
) -> CommandHandlerResult:
    if name == "send_input":
        return handle_send_input_command(
            runtime=runtime,
            arg_text=arg_text,
            parse_json_tool_arg=parse_json_tool_arg,
            bool_option=bool_option,
            text_only_result=text_only_result,
            error_result=error_result,
            error_event=error_event,
            slash_invocation=slash_invocation,
        )
    if name == "resume_agent":
        return handle_resume_agent_command(
            runtime=runtime,
            arg_text=arg_text,
            parse_json_tool_arg=parse_json_tool_arg,
            text_only_result=text_only_result,
            error_result=error_result,
            error_event=error_event,
            slash_invocation=slash_invocation,
        )
    if name == "wait_agent":
        return handle_wait_agent_command(
            runtime=runtime,
            arg_text=arg_text,
            parse_json_tool_arg=parse_json_tool_arg,
            int_option=int_option,
            text_only_result=text_only_result,
            error_result=error_result,
            error_event=error_event,
            slash_invocation=slash_invocation,
        )
    if name == "close_agent":
        return handle_close_agent_command(
            runtime=runtime,
            arg_text=arg_text,
            parse_json_tool_arg=parse_json_tool_arg,
            text_only_result=text_only_result,
            error_result=error_result,
            error_event=error_event,
            slash_invocation=slash_invocation,
        )
    if name == "agent_workflow":
        return handle_agent_workflow_command(
            runtime=runtime,
            arg_text=arg_text,
            parse_json_tool_arg=parse_json_tool_arg,
            int_option=int_option,
            text_only_result=text_only_result,
            error_result=error_result,
            error_event=error_event,
            slash_invocation=slash_invocation,
        )
    if name == "recover_agent":
        return handle_recover_agent_command(
            runtime=runtime,
            arg_text=arg_text,
            parse_json_tool_arg=parse_json_tool_arg,
            text_only_result=text_only_result,
            error_result=error_result,
            error_event=error_event,
            slash_invocation=slash_invocation,
        )
    return None

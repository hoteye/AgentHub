from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.slash_parser import SlashInvocation
from cli.agent_cli.runtime_core.command_usage import (
    _agent_workflow_usage_text,
    _close_agent_usage_text,
    _recover_agent_usage_text,
    _resume_agent_usage_text,
    _send_input_usage_text,
)
from cli.agent_cli.runtime_core import thread_commands_agent_runtime
from cli.agent_cli.runtime_core import thread_commands_target_helpers_runtime

CommandHandlerResult = Optional[Tuple[str, List[ToolEvent]] | CommandExecutionResult]


def _parse_target_command_inputs(
    *,
    runtime: Any,
    arg_text: str,
    parse_json_tool_arg: Callable[[str], Dict[str, Any]],
    slash_invocation: SlashInvocation | None = None,
) -> tuple[dict[str, Any], tuple[list[Any], dict[str, Any]]]:
    return thread_commands_agent_runtime.parse_target_command_payload(
        runtime=runtime,
        arg_text=arg_text,
        parse_json_tool_arg=parse_json_tool_arg,
        slash_invocation=slash_invocation,
    )


def _run_single_target_command(
    *,
    runtime: Any,
    arg_text: str,
    parse_json_tool_arg: Callable[[str], Dict[str, Any]],
    text_only_result: Callable[[str], CommandExecutionResult],
    error_result: Callable[..., CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
    usage_text: Callable[[], str],
    runner_name: str,
    event_name: str,
    unavailable_summary: str,
    failed_summary: str,
    slash_invocation: SlashInvocation | None = None,
) -> CommandHandlerResult:
    payload, parsed_args = _parse_target_command_inputs(
        runtime=runtime,
        arg_text=arg_text,
        parse_json_tool_arg=parse_json_tool_arg,
        slash_invocation=slash_invocation,
    )
    command_values = thread_commands_target_helpers_runtime.resolve_single_target_command_values(
        payload=payload,
        parsed_args=parsed_args,
    )
    if not command_values.agent_id:
        return text_only_result(usage_text())
    return thread_commands_agent_runtime.run_target_command(
        runtime=runtime,
        runner_name=runner_name,
        event_name=event_name,
        unavailable_summary=unavailable_summary,
        failed_summary=failed_summary,
        runner_args=(command_values.agent_id,),
        runner_kwargs={"codex_style": command_values.codex_style},
        error_result=error_result,
        error_event=error_event,
        arguments=thread_commands_target_helpers_runtime.target_arguments(
            agent_id=command_values.agent_id,
            codex_style=command_values.codex_style,
        ),
        target_for_error=command_values.agent_id,
    )


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
    payload, parsed_args = _parse_target_command_inputs(
        runtime=runtime,
        arg_text=arg_text,
        parse_json_tool_arg=parse_json_tool_arg,
        slash_invocation=slash_invocation,
    )
    command_values = thread_commands_target_helpers_runtime.resolve_send_input_command_values(
        payload=payload,
        parsed_args=parsed_args,
        bool_option=bool_option,
    )
    if command_values.message_items_conflict:
        return error_result(
            error_event(
                "send_input",
                "send_input parse failed",
                error="Provide either message or items, but not both",
            ),
        )
    if not command_values.agent_id or not command_values.message_text:
        return text_only_result(_send_input_usage_text())
    arguments = thread_commands_target_helpers_runtime.send_input_arguments(
        use_id_style=bool(payload and command_values.codex_style),
        agent_id=command_values.agent_id,
        message_text=command_values.message_text,
        input_items=command_values.input_items,
        interrupt=command_values.interrupt,
    )
    return thread_commands_agent_runtime.run_target_command(
        runtime=runtime,
        runner_name="send_input_result",
        event_name="send_input",
        unavailable_summary="send_input unavailable",
        failed_summary="send_input failed",
        runner_args=(command_values.agent_id,),
        runner_kwargs={
            "message": command_values.message_text,
            "interrupt": command_values.interrupt,
            "input_items": command_values.input_items,
            "codex_style": command_values.codex_style,
        },
        error_result=error_result,
        error_event=error_event,
        arguments=arguments,
        target_for_error=command_values.agent_id,
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
    return _run_single_target_command(
        runtime=runtime,
        arg_text=arg_text,
        parse_json_tool_arg=parse_json_tool_arg,
        text_only_result=text_only_result,
        error_result=error_result,
        error_event=error_event,
        usage_text=_resume_agent_usage_text,
        runner_name="resume_agent_result",
        event_name="resume_agent",
        unavailable_summary="resume_agent unavailable",
        failed_summary="resume_agent failed",
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
    return _run_single_target_command(
        runtime=runtime,
        arg_text=arg_text,
        parse_json_tool_arg=parse_json_tool_arg,
        text_only_result=text_only_result,
        error_result=error_result,
        error_event=error_event,
        usage_text=_close_agent_usage_text,
        runner_name="close_agent_result",
        event_name="close_agent",
        unavailable_summary="close_agent unavailable",
        failed_summary="close_agent failed",
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
    payload, parsed_args = _parse_target_command_inputs(
        runtime=runtime,
        arg_text=arg_text,
        parse_json_tool_arg=parse_json_tool_arg,
        slash_invocation=slash_invocation,
    )
    command_values = thread_commands_target_helpers_runtime.resolve_agent_workflow_command_values(
        payload=payload,
        parsed_args=parsed_args,
    )
    if not command_values.agent_id:
        return text_only_result(_agent_workflow_usage_text())
    try:
        steps_limit, checkpoints_limit = thread_commands_target_helpers_runtime.validate_agent_workflow_limits(
            steps=command_values.steps,
            checkpoints=command_values.checkpoints,
            int_option=int_option,
        )
    except ValueError as exc:
        return text_only_result(str(exc))
    arguments = thread_commands_target_helpers_runtime.agent_workflow_arguments(
        agent_id=command_values.agent_id,
        steps_limit=steps_limit,
        checkpoints_limit=checkpoints_limit,
    )
    return thread_commands_agent_runtime.run_target_command(
        runtime=runtime,
        runner_name="agent_workflow_result",
        event_name="agent_workflow",
        unavailable_summary="agent_workflow unavailable",
        failed_summary="agent_workflow failed",
        runner_args=(command_values.agent_id,),
        runner_kwargs={"steps_limit": steps_limit, "checkpoints_limit": checkpoints_limit},
        error_result=error_result,
        error_event=error_event,
        arguments=arguments,
        target_for_error=command_values.agent_id,
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
    payload, parsed_args = _parse_target_command_inputs(
        runtime=runtime,
        arg_text=arg_text,
        parse_json_tool_arg=parse_json_tool_arg,
        slash_invocation=slash_invocation,
    )
    command_values = thread_commands_target_helpers_runtime.resolve_recover_agent_command_values(
        payload=payload,
        parsed_args=parsed_args,
    )
    if not command_values.agent_id:
        return text_only_result(_recover_agent_usage_text())
    arguments = thread_commands_target_helpers_runtime.recover_agent_arguments(
        agent_id=command_values.agent_id,
        action=command_values.action,
        step_id=command_values.step_id,
    )
    return thread_commands_agent_runtime.run_target_command(
        runtime=runtime,
        runner_name="recover_agent_result",
        event_name="recover_agent",
        unavailable_summary="recover_agent unavailable",
        failed_summary="recover_agent failed",
        runner_args=(command_values.agent_id,),
        runner_kwargs={"action": command_values.action, "step_id": command_values.step_id},
        error_result=error_result,
        error_event=error_event,
        arguments=arguments,
        target_for_error=command_values.agent_id,
    )


__all__ = [
    "handle_agent_workflow_command",
    "handle_close_agent_command",
    "handle_recover_agent_command",
    "handle_resume_agent_command",
    "handle_send_input_command",
]

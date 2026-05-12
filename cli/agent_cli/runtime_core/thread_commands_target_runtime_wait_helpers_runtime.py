from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.slash_parser import SlashInvocation
from cli.agent_cli.runtime_core.command_usage import _wait_agent_usage_text
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


def _run_wait_agents_command(
    *,
    runtime: Any,
    agent_ids: list[str],
    timeout_ms_text: str | None,
    reason: str | None,
    wait_required: Any,
    codex_style: bool,
    event_name: str,
    unavailable_summary: str,
    failed_summary: str,
    error_result: Callable[..., CommandExecutionResult],
    error_event: Callable[..., ToolEvent],
    arguments: dict[str, Any],
) -> CommandHandlerResult:
    runner = getattr(runtime, "wait_agents_result", None)
    if not callable(runner):
        return error_result(
            error_event(
                event_name,
                unavailable_summary,
                error="wait_agents_result runtime is unavailable",
                target=",".join(agent_ids),
            ),
            arguments=arguments,
        )
    try:
        return runner(
            agent_ids,
            **thread_commands_agent_runtime._filter_runner_kwargs(
                runner,
                {
                    "timeout_ms": timeout_ms_text,
                    "reason": reason,
                    "wait_required": wait_required,
                    "codex_style": codex_style,
                },
            ),
        )
    except Exception as exc:
        return error_result(
            error_event(
                event_name,
                failed_summary,
                error=str(exc),
                target=",".join(agent_ids),
            ),
            arguments=arguments,
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
    payload, parsed_args = _parse_target_command_inputs(
        runtime=runtime,
        arg_text=arg_text,
        parse_json_tool_arg=parse_json_tool_arg,
        slash_invocation=slash_invocation,
    )
    command_values = thread_commands_target_helpers_runtime.resolve_wait_command_values(
        payload=payload,
        parsed_args=parsed_args,
    )
    agent_ids = thread_commands_target_helpers_runtime.select_wait_agent_ids(command_values)
    if not agent_ids:
        return text_only_result(_wait_agent_usage_text())
    try:
        timeout_ms_text = thread_commands_target_helpers_runtime.validate_wait_timeout_text(
            ids=command_values.ids,
            timeout_ms=command_values.timeout_ms,
            int_option=int_option,
        )
    except ValueError as exc:
        return text_only_result(str(exc))
    if len(agent_ids) > 1:
        return _run_wait_agents_command(
            runtime=runtime,
            agent_ids=agent_ids,
            timeout_ms_text=timeout_ms_text,
            reason=command_values.reason,
            wait_required=command_values.wait_required,
            codex_style=bool(command_values.ids),
            event_name="wait_agent",
            unavailable_summary="wait_agent unavailable",
            failed_summary="wait_agent failed",
            error_result=error_result,
            error_event=error_event,
            arguments=thread_commands_target_helpers_runtime.wait_ids_arguments(
                agent_ids=agent_ids,
                timeout_ms_text=timeout_ms_text,
                reason=command_values.reason,
                wait_required=command_values.wait_required,
            ),
        )
    agent_id = agent_ids[0]
    if command_values.ids:
        return _run_wait_agents_command(
            runtime=runtime,
            agent_ids=agent_ids,
            timeout_ms_text=timeout_ms_text,
            reason=None,
            wait_required=None,
            codex_style=True,
            event_name="wait",
            unavailable_summary="wait unavailable",
            failed_summary="wait failed",
            error_result=error_result,
            error_event=error_event,
            arguments=thread_commands_target_helpers_runtime.wait_ids_arguments(
                agent_ids=agent_ids,
                timeout_ms_text=timeout_ms_text,
            ),
        )
    arguments = thread_commands_target_helpers_runtime.wait_target_arguments(
        agent_id=agent_id,
        timeout_ms_text=timeout_ms_text,
        reason=command_values.reason,
        wait_required=command_values.wait_required,
    )
    return thread_commands_agent_runtime.run_target_command(
        runtime=runtime,
        runner_name="wait_agent_result",
        event_name="wait_agent",
        unavailable_summary="wait_agent unavailable",
        failed_summary="wait_agent failed",
        runner_args=(agent_id,),
        runner_kwargs={
            "timeout_ms": timeout_ms_text,
            "reason": command_values.reason,
            "wait_required": command_values.wait_required,
        },
        error_result=error_result,
        error_event=error_event,
        arguments=arguments,
        target_for_error=agent_id,
    )


__all__ = ["handle_wait_agent_command"]

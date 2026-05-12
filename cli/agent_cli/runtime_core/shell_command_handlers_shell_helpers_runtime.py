from __future__ import annotations

from typing import Any, Callable, List, Optional, Tuple

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.runtime_core.command_usage import _shell_usage_text
from cli.agent_cli.runtime_core import shell_command_handlers_runtime

CommandHandlerResult = Optional[Tuple[str, List[ToolEvent]] | CommandExecutionResult]


def handle_shell_alias_command(
    runtime: Any,
    *,
    arg_text: str,
    single_event_result: Callable[..., CommandExecutionResult],
    approval_request_text: Callable[[str, ToolEvent], str],
    error_event: Callable[..., ToolEvent],
) -> CommandHandlerResult:
    if not arg_text:
        return _shell_usage_text(), []
    try:
        shell_action, shell_args = shell_command_handlers_runtime.parse_shell_action(arg_text)
    except ValueError as exc:
        return single_event_result(
            "Shell command parse failed.",
            error_event("shell", "shell parse failed", error=str(exc)),
            arguments={"raw": arg_text},
        )
    if shell_action == "start":
        if not shell_args:
            return _shell_usage_text(), []
        command = " ".join(shell_args).strip()
        result = runtime.begin_shell_request(
            command,
            exec_mode="session_start",
        )
        if result.get("status") == "approval_required":
            event = result.get("tool_event")
            return (approval_request_text("Request shell approval.", event), [event])
        command_result = result.get("command_result")
        if isinstance(command_result, CommandExecutionResult):
            return command_result
        return single_event_result(
            "Start shell session.",
            result.get("tool_event"),
            arguments={"command": command, "exec_mode": "session_start"},
        )
    if shell_action == "write":
        if len(shell_args) < 2:
            return _shell_usage_text(), []
        session_id = str(shell_args[0] or "").strip()
        chars = " ".join(shell_args[1:])
        result_getter = getattr(runtime, "write_shell_stdin_result", None)
        if callable(result_getter):
            structured = result_getter(session_id, chars)
            if isinstance(structured, CommandExecutionResult):
                return structured
        return single_event_result(
            "Write shell stdin.",
            runtime.write_shell_stdin(session_id, chars),
            arguments={"session_id": session_id, "chars": chars},
        )
    if shell_action in {"terminate", "stop"}:
        if len(shell_args) != 1:
            return _shell_usage_text(), []
        session_id = str(shell_args[0] or "").strip()
        result_getter = getattr(runtime, "terminate_shell_session_result", None)
        if callable(result_getter):
            structured = result_getter(session_id)
            if isinstance(structured, CommandExecutionResult):
                return structured
        return single_event_result(
            "Terminate shell session.",
            runtime.terminate_shell_session(session_id),
            arguments={"session_id": session_id},
        )
    command = " ".join(shell_args).strip()
    result = runtime.begin_shell_request(command)
    if result.get("status") == "approval_required":
        event = result.get("tool_event")
        return (approval_request_text("Request shell approval.", event), [event])
    command_result = result.get("command_result")
    if isinstance(command_result, CommandExecutionResult):
        return command_result
    return single_event_result(
        "Run shell command.",
        result.get("tool_event"),
        arguments={"command": command, "exec_mode": "exec_once"},
    )

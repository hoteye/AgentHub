from __future__ import annotations

from typing import Any, Dict

from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core import shell_result_runtime


def join_aggregated_output(stdout_text: str, stderr_text: str) -> str:
    return shell_result_runtime.join_aggregated_output(stdout_text, stderr_text)


def shell_exec_args(
    host_platform: HostPlatform,
    command: str,
    *,
    login: bool,
    shell: str | None,
) -> list[str]:
    return shell_result_runtime.shell_exec_args(
        host_platform,
        command,
        login=login,
        shell=shell,
    )


def trim_output(text: str, *, limit: int) -> tuple[str, bool, int]:
    return shell_result_runtime.trim_output(text, limit=limit)


def shell_command_result(
    assistant_text: str,
    event: ToolEvent,
    *,
    command: str | None = None,
) -> CommandExecutionResult:
    return shell_result_runtime.shell_command_result(
        assistant_text=assistant_text,
        event=event,
        command=command,
    )


def session_started_event_from_session(
    session: Dict[str, Any],
    *,
    command: str,
    exec_mode: str = "session_start",
) -> ToolEvent:
    return shell_result_runtime.session_started_event_from_session(
        session=session,
        command=command,
        exec_mode=exec_mode,
    )


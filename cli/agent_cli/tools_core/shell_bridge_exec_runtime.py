from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core import shell_command_runtime


def execute_shell(
    *,
    host_platform: HostPlatform,
    command: str,
    manager_factory: Callable[[HostPlatform], Any],
    cwd: str | None = None,
    timeout_sec: int = 60,
    login: bool = True,
    tty: bool = False,
    shell: str | None = None,
    max_output_chars: int = 12000,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> ToolEvent:
    return shell_command_runtime.execute_shell(
        host_platform=host_platform,
        command=command,
        manager_factory=manager_factory,
        cwd=cwd,
        timeout_sec=timeout_sec,
        login=login,
        tty=tty,
        shell=shell,
        max_output_chars=max_output_chars,
        on_activity=on_activity,
        cancel_event=cancel_event,
    )


def execute_shell_result(
    *,
    host_platform: HostPlatform,
    command: str,
    execute_shell_fn: Callable[..., ToolEvent],
    cwd: str | None = None,
    timeout_sec: int = 60,
    login: bool = True,
    tty: bool = False,
    shell: str | None = None,
    max_output_chars: int = 12000,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> CommandExecutionResult:
    return shell_command_runtime.execute_shell_result(
        host_platform=host_platform,
        command=command,
        execute_shell_fn=execute_shell_fn,
        cwd=cwd,
        timeout_sec=timeout_sec,
        login=login,
        tty=tty,
        shell=shell,
        max_output_chars=max_output_chars,
        on_activity=on_activity,
        cancel_event=cancel_event,
    )

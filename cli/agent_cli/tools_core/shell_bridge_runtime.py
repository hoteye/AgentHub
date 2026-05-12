from __future__ import annotations

import os
import shutil
import subprocess
import threading
import uuid
from dataclasses import dataclass
from typing import Any

from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.tools_core import shell_result_runtime
from cli.agent_cli.tools_core.shell_session_state import _ShellSession


@dataclass
class StartedShellSession:
    session_id: str
    session: _ShellSession
    normalized_command: str
    normalized_cwd: str | None
    normalized_shell: str | None


def build_started_shell_session(
    *,
    host_platform: HostPlatform,
    command: str,
    cwd: str | None,
    workspace_root: str | None,
    login: bool,
    tty: bool,
    shell: str | None,
    max_output_chars: int,
    cancel_event: threading.Event | None,
    pty_module: Any,
    shell_exec_args_builder,
) -> StartedShellSession:
    normalized_command = str(command or "").strip()
    if not normalized_command:
        raise ValueError("command must be a non-empty string")
    normalized_cwd = str(cwd or "").strip() or None
    normalized_shell = host_platform.normalize_shell_override(shell)
    resolved_shell = host_platform.resolve_shell_program(normalized_shell)
    use_pty = bool(
        tty
        and host_platform.family == "unix"
        and pty_module is not None
        and shutil.which(resolved_shell)
    )
    process, pty_master_fd, terminate_as_process_group = _launch_process(
        host_platform=host_platform,
        normalized_command=normalized_command,
        normalized_cwd=normalized_cwd,
        login=bool(login),
        normalized_shell=resolved_shell,
        use_pty=use_pty,
        pty_module=pty_module,
        shell_exec_args_builder=shell_exec_args_builder,
    )
    session_id = uuid.uuid4().hex
    session = _ShellSession(
        session_id=session_id,
        command=normalized_command,
        cwd=normalized_cwd,
        login=login,
        tty=tty,
        shell=resolved_shell,
        max_output_chars=max_output_chars,
        process=process,
        pty_master_fd=pty_master_fd,
        cancel_event=cancel_event,
        terminate_as_process_group=terminate_as_process_group,
        workspace_root=workspace_root,
    )
    return StartedShellSession(
        session_id=session_id,
        session=session,
        normalized_command=normalized_command,
        normalized_cwd=normalized_cwd,
        normalized_shell=resolved_shell,
    )


def build_started_session_payload(started: StartedShellSession, *, login: bool, tty: bool) -> dict[str, Any]:
    return shell_result_runtime.build_started_session_payload(
        session=started.session,
        session_id=started.session_id,
        command=started.normalized_command,
        cwd=started.normalized_cwd,
        login=bool(login),
        tty=bool(tty),
        shell=started.normalized_shell,
    )


def _launch_process(
    *,
    host_platform: HostPlatform,
    normalized_command: str,
    normalized_cwd: str | None,
    login: bool,
    normalized_shell: str | None,
    use_pty: bool,
    pty_module: Any,
    shell_exec_args_builder,
) -> tuple[subprocess.Popen[Any], int | None, bool]:
    popen_kwargs: dict[str, Any] = {}
    terminate_as_process_group = False
    if host_platform.family == "unix":
        popen_kwargs["start_new_session"] = True
        terminate_as_process_group = True
    if use_pty:
        master_fd, slave_fd = pty_module.openpty()
        try:
            process = subprocess.Popen(
                shell_exec_args_builder(
                    host_platform,
                    normalized_command,
                    login=login,
                    shell=normalized_shell,
                ),
                shell=False,
                cwd=normalized_cwd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                text=False,
                bufsize=0,
                close_fds=True,
                **popen_kwargs,
            )
        finally:
            try:
                os.close(slave_fd)
            except OSError:
                pass
        return process, master_fd, terminate_as_process_group
    process = subprocess.Popen(
        shell_exec_args_builder(
            host_platform,
            normalized_command,
            login=login,
            shell=normalized_shell,
        ),
        shell=False,
        cwd=normalized_cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        **popen_kwargs,
    )
    return process, None, terminate_as_process_group

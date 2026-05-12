from __future__ import annotations

from typing import Any, Dict

from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core import shell_command_runtime
from cli.agent_cli.tools_core import shell_stream_bridge
from cli.agent_cli.tools_core import shell_event_payloads
from cli.agent_cli.tools_core.shell_session_state import _ShellSession
from cli.agent_cli.tools_core.output_persistence_runtime import shell_background_contract_fields


def join_aggregated_output(stdout_text: str, stderr_text: str) -> str:
    return shell_stream_bridge.join_aggregated_output(stdout_text, stderr_text)


def trim_output(text: str, *, limit: int) -> tuple[str, bool, int]:
    return shell_stream_bridge.trim_output(text, limit=limit)


def shell_command_result(
    assistant_text: str,
    event: ToolEvent,
    *,
    command: str | None = None,
) -> CommandExecutionResult:
    return shell_command_runtime.shell_command_result(
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
    return shell_command_runtime.session_started_event_from_session(
        session=session,
        command=command,
        exec_mode=exec_mode,
    )


def build_started_session_payload(
    *,
    session: _ShellSession,
    session_id: str,
    command: str,
    cwd: str | None,
    login: bool,
    tty: bool,
    shell: str | None,
) -> Dict[str, Any]:
    payload = {
        "session_id": session_id,
        "call_id": session.call_id,
        "process_id": session.process_id,
        "command": command,
        "cwd": cwd,
        "login": bool(login),
        "tty": bool(tty),
        "shell": shell,
        "io_mode": session.io_mode,
        "started_at_ms": session.started_at_ms,
        "phase": "started",
        "status": "started",
        "source": "shell_session_manager",
        "lifecycle": shell_event_payloads.lifecycle_payload(
            phase="started",
            kind="begin",
            call_id=session.call_id,
            session_id=session_id,
            process_id=session.process_id,
            status="started",
        ),
    }
    payload.update(
        shell_background_contract_fields(
            payload,
            workspace_root=getattr(session, "workspace_root", None),
            task_id=getattr(session, "task_id", session_id),
            persist=True,
        )
    )
    return payload


def output_snapshot_payload(session: _ShellSession, incremental: Dict[str, str]) -> Dict[str, Any]:
    return shell_stream_bridge.output_snapshot_payload(session, incremental)


def final_status_fields(session: _ShellSession) -> Dict[str, Any]:
    return shell_stream_bridge.final_status_fields(session)


def shell_exec_args(
    host_platform: HostPlatform,
    command: str,
    *,
    login: bool,
    shell: str | None,
) -> list[str]:
    normalized = host_platform.normalize_shell_command(command)
    shell_program = host_platform.resolve_shell_program(shell)
    if host_platform.os == "windows":
        lowered = shell_program.lower()
        if lowered.endswith("cmd.exe") or lowered.endswith("\\cmd") or lowered == "cmd":
            raw = " ".join(str(command or "").strip().split())
            raw_lowered = raw.lower()
            normalized_lowered = normalized.lower()
            if raw_lowered in {"pwd", "cwd"} or normalized_lowered == "get-location":
                cmd_command = "cd"
            elif raw_lowered in {"ls", "dir"} or normalized_lowered == "get-childitem":
                cmd_command = "dir"
            elif raw_lowered in {"ls -a", "ls -la", "ls -al", "dir /a"} or normalized_lowered == "get-childitem -force":
                cmd_command = "dir /a"
            else:
                cmd_command = str(command or "").strip() or normalized
            return [shell_program, "/d", "/s", "/c", cmd_command]
        args = [shell_program]
        if not login:
            args.append("-NoProfile")
        args.extend(["-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", normalized])
        return args
    return [shell_program, "-lc" if login else "-c", normalized]

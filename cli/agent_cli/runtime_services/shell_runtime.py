from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from cli.agent_cli.host_platform import HostPlatform, current_host_platform
from cli.agent_cli.models import (
    CommandExecutionResult,
    ToolEvent,
)
from cli.agent_cli.runtime_services import (
    command_policy_runtime,
    shell_runtime_helpers,
    shell_runtime_invocation,
    shell_runtime_payload_runtime,
)
from cli.agent_cli.runtime_services.shell_runtime_core_helpers import (
    _command_policy_decision,
    _policy_denied_result,
    shell_result_from_event,
)


def normalize_shell_exec_mode(value: str | None) -> str:
    mode = str(value or "").strip().lower()
    if mode in {"start", "session", "session_start", "interactive"}:
        return "session_start"
    return "exec_once"


def host_platform(runtime: Any) -> HostPlatform:
    candidate = getattr(runtime.tools, "_host_platform", None)
    if isinstance(candidate, HostPlatform):
        return candidate
    return current_host_platform()


def normalize_shell_override(runtime: Any, shell: str | None) -> str | None:
    return host_platform(runtime).normalize_shell_override(shell)


def run_shell_command(
    runtime: Any,
    command: str,
    *,
    cwd: str | None = None,
    timeout_sec: int = 60,
    login: bool = True,
    tty: bool = False,
    shell: str | None = None,
    max_output_chars: int = 12000,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> ToolEvent:
    shell_fn = getattr(runtime.tools, "shell", None)
    normalized_command = str(command or "").strip()
    if not callable(shell_fn):
        return ToolEvent(
            name="shell",
            ok=False,
            summary="shell unsupported",
            payload={
                "command": normalized_command,
                "error": "shell tool unavailable",
                "status": "unsupported",
            },
        )
    decision = _command_policy_decision(normalized_command)
    if not decision.allowed:
        return command_policy_runtime.policy_denied_tool_event(
            tool_name="shell",
            decision=decision,
        )
    normalized_shell = normalize_shell_override(runtime, shell)
    options = shell_runtime_invocation.build_shell_options(
        cwd=cwd,
        timeout_sec=timeout_sec,
        login=login,
        tty=tty,
        shell=normalized_shell,
        max_output_chars=max_output_chars,
        on_activity=on_activity,
        cancel_event=cancel_event,
    )
    event = shell_runtime_invocation.invoke_shell_callable(
        shell_fn,
        decision.effective_command,
        options,
    )
    return command_policy_runtime.wrap_tool_event_with_policy(
        event,
        decision=decision,
    )


def run_shell_command_result(
    runtime: Any,
    command: str,
    *,
    cwd: str | None = None,
    timeout_sec: int = 60,
    login: bool = True,
    tty: bool = False,
    shell: str | None = None,
    max_output_chars: int = 12000,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> CommandExecutionResult:
    normalized_command = str(command or "").strip()
    decision = _command_policy_decision(normalized_command)
    if not decision.allowed:
        return _policy_denied_result(
            decision.error_message or "command denied by policy",
            decision,
            tool_name="shell",
        )
    normalized_shell = normalize_shell_override(runtime, shell)
    event = run_shell_command(
        runtime,
        normalized_command,
        cwd=cwd,
        timeout_sec=timeout_sec,
        login=login,
        tty=tty,
        shell=normalized_shell,
        max_output_chars=max_output_chars,
        on_activity=on_activity,
        cancel_event=cancel_event,
    )
    return shell_result_from_event("Run shell command.", event, command=normalized_command)


def start_shell_session(
    runtime: Any,
    command: str,
    *,
    cwd: str | None = None,
    login: bool = True,
    tty: bool = False,
    shell: str | None = None,
    max_output_chars: int = 12000,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
    trace: Callable[..., None],
) -> dict[str, Any]:
    start_fn = getattr(runtime.tools, "shell_start", None)
    normalized_command = str(command or "").strip()
    if not callable(start_fn):
        raise RuntimeError("interactive shell unsupported")
    decision = _command_policy_decision(normalized_command)
    if not decision.allowed:
        trace(
            "tool.runtime.shell_start.denied",
            command=normalized_command,
            error=decision.error_message,
            error_code=decision.error_code,
        )
        raise command_policy_runtime.CommandPolicyError(decision)
    normalized_shell = normalize_shell_override(runtime, shell)
    resolved_shell = host_platform(runtime).resolve_shell_program(normalized_shell)
    trace(
        "tool.runtime.shell_start.begin",
        command=normalized_command,
        effective_command=decision.effective_command,
        cwd=cwd,
        login=bool(login),
        tty=bool(tty),
        shell=resolved_shell,
        max_output_chars=int(max_output_chars),
    )
    options = shell_runtime_invocation.build_shell_options(
        cwd=cwd,
        login=login,
        tty=tty,
        shell=normalized_shell,
        max_output_chars=max_output_chars,
        on_activity=on_activity,
    )
    try:
        session = dict(
            shell_runtime_invocation.invoke_shell_callable(
                start_fn, decision.effective_command, options
            )
            or {}
        )
    except Exception as exc:
        trace(
            "tool.runtime.shell_start.failed",
            command=normalized_command,
            cwd=cwd,
            login=bool(login),
            tty=bool(tty),
            shell=normalized_shell,
            error=str(exc),
        )
        raise
    session_id = str(session.get("session_id") or "").strip()
    if not session_id:
        trace(
            "tool.runtime.shell_start.failed",
            command=normalized_command,
            cwd=cwd,
            login=bool(login),
            tty=bool(tty),
            shell=normalized_shell,
            error="shell_start did not return session_id",
        )
        raise RuntimeError("shell_start did not return session_id")
    policy_payload = decision.payload() if (decision.is_test_command or decision.metadata) else None
    session = shell_runtime_payload_runtime.apply_start_session_defaults(
        session,
        normalized_command=normalized_command,
        effective_command=decision.effective_command,
        policy_payload=policy_payload,
        cwd=cwd,
        login=login,
        tty=tty,
        shell=resolved_shell,
    )
    process_id = str(session.get("process_id") or session_id).strip() or session_id
    trace(
        "tool.runtime.shell_start.completed",
        command=normalized_command,
        effective_command=decision.effective_command,
        session_id=session_id,
        process_id=process_id,
        call_id=session.get("call_id"),
        cwd=session.get("cwd"),
        login=session.get("login"),
        tty=session.get("tty"),
        shell=session.get("shell"),
    )
    return session


def write_shell_stdin(
    runtime: Any,
    session_id: str,
    chars: str,
    *,
    yield_time_ms: int | float | None = None,
    allow_extended_empty_poll: bool = False,
    max_output_chars: int | None = None,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> ToolEvent:
    write_fn = getattr(runtime.tools, "shell_write_stdin", None)
    normalized_session_id = str(session_id or "").strip()
    if not callable(write_fn):
        return shell_runtime_helpers.unsupported_interactive_shell_event(
            "stdin",
            normalized_session_id,
        )
    return shell_runtime_invocation.invoke_shell_session_callable(
        write_fn,
        normalized_session_id,
        chars,
        yield_time_ms=yield_time_ms,
        allow_extended_empty_poll=allow_extended_empty_poll,
        max_output_chars=max_output_chars,
        on_activity=on_activity,
        cancel_event=cancel_event,
    )


def write_shell_stdin_result(
    runtime: Any,
    session_id: str,
    chars: str,
    *,
    yield_time_ms: int | float | None = None,
    allow_extended_empty_poll: bool = False,
    max_output_chars: int | None = None,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
    trace: Callable[..., None],
    preview_text: Callable[[Any], str],
) -> CommandExecutionResult:
    return shell_runtime_helpers.write_stdin_result(
        runtime,
        session_id,
        chars,
        yield_time_ms=yield_time_ms,
        allow_extended_empty_poll=allow_extended_empty_poll,
        max_output_chars=max_output_chars,
        on_activity=on_activity,
        cancel_event=cancel_event,
        trace=trace,
        preview_text=preview_text,
        write_shell_stdin_fn=write_shell_stdin,
        shell_result_from_event_fn=lambda assistant_text, event: shell_result_from_event(
            assistant_text, event
        ),
    )


def terminate_shell_session(
    runtime: Any,
    session_id: str,
    *,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
) -> ToolEvent:
    terminate_fn = getattr(runtime.tools, "shell_terminate", None)
    normalized_session_id = str(session_id or "").strip()
    if not callable(terminate_fn):
        return shell_runtime_helpers.unsupported_interactive_shell_event(
            "terminate",
            normalized_session_id,
        )
    return shell_runtime_invocation.invoke_session_control_callable(
        terminate_fn,
        normalized_session_id,
        on_activity=on_activity,
    )


def terminate_shell_session_result(
    runtime: Any,
    session_id: str,
    *,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
) -> CommandExecutionResult:
    return shell_runtime_helpers.session_control_result(
        runtime,
        session_id,
        result_attr="shell_terminate_result",
        on_activity=on_activity,
        fallback_event_fn=terminate_shell_session,
        shell_result_from_event_fn=lambda assistant_text, event: shell_result_from_event(
            assistant_text, event
        ),
        assistant_text="Terminate shell session.",
    )


def subscribe_shell_session(
    runtime: Any,
    session_id: str,
    *,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
) -> ToolEvent:
    subscribe_fn = getattr(runtime.tools, "shell_subscribe", None)
    normalized_session_id = str(session_id or "").strip()
    if not callable(subscribe_fn):
        return shell_runtime_helpers.unsupported_interactive_shell_event(
            "subscribe",
            normalized_session_id,
        )
    return shell_runtime_invocation.invoke_session_control_callable(
        subscribe_fn,
        normalized_session_id,
        on_activity=on_activity,
    )


def subscribe_shell_session_result(
    runtime: Any,
    session_id: str,
    *,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
) -> CommandExecutionResult:
    return shell_runtime_helpers.session_control_result(
        runtime,
        session_id,
        result_attr="shell_subscribe_result",
        on_activity=on_activity,
        fallback_event_fn=subscribe_shell_session,
        shell_result_from_event_fn=lambda assistant_text, event: shell_result_from_event(
            assistant_text, event
        ),
        assistant_text="Subscribe shell session.",
    )

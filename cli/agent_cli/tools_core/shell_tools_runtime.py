from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.tools_core.shell_bridge import execute_shell, execute_shell_result


def _resolve_on_activity(
    registry: Any,
    on_activity: Callable[[dict[str, Any]], None] | None,
) -> Callable[[dict[str, Any]], None] | None:
    callback = on_activity or getattr(registry, "_shell_activity_callback", None)
    if callback is None:
        return None
    suppress_activity = False
    suppressed_getter = getattr(registry, "_shell_activity_suppressed_getter", None)
    if callable(suppressed_getter):
        try:
            suppress_activity = bool(suppressed_getter())
        except Exception:
            suppress_activity = False
    if not suppress_activity:
        return callback

    def _suppressed_on_activity(payload: dict[str, Any]) -> None:
        del payload
        return None

    return _suppressed_on_activity


def _resolve_cancel_event(
    registry: Any,
    cancel_event: threading.Event | None,
) -> threading.Event | None:
    if cancel_event is not None:
        return cancel_event
    cancel_getter = getattr(registry, "_shell_cancel_event_getter", None)
    if callable(cancel_getter):
        return cancel_getter()
    return None


def shell(
    registry: Any,
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
    return execute_shell(
        host_platform=registry._host_platform,
        command=command,
        cwd=registry._resolve_shell_cwd(cwd),
        timeout_sec=timeout_sec,
        login=login,
        tty=tty,
        shell=shell,
        max_output_chars=max_output_chars,
        on_activity=_resolve_on_activity(registry, on_activity),
        cancel_event=_resolve_cancel_event(registry, cancel_event),
    )


def shell_result(
    registry: Any,
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
    return execute_shell_result(
        host_platform=registry._host_platform,
        command=command,
        cwd=registry._resolve_shell_cwd(cwd),
        timeout_sec=timeout_sec,
        login=login,
        tty=tty,
        shell=shell,
        max_output_chars=max_output_chars,
        on_activity=_resolve_on_activity(registry, on_activity),
        cancel_event=_resolve_cancel_event(registry, cancel_event),
    )


def shell_start(
    registry: Any,
    command: str,
    *,
    cwd: str | None = None,
    login: bool = True,
    tty: bool = False,
    shell: str | None = None,
    max_output_chars: int = 12000,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    return registry._shell_sessions.start_session(
        command=command,
        cwd=registry._resolve_shell_cwd(cwd),
        login=login,
        tty=tty,
        shell=shell,
        max_output_chars=max_output_chars,
        on_activity=_resolve_on_activity(registry, on_activity),
    )


def shell_start_result(
    registry: Any,
    command: str,
    *,
    cwd: str | None = None,
    login: bool = True,
    tty: bool = False,
    shell: str | None = None,
    max_output_chars: int = 12000,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
) -> CommandExecutionResult:
    return registry._shell_sessions.start_session_result(
        command=command,
        cwd=registry._resolve_shell_cwd(cwd),
        login=login,
        tty=tty,
        shell=shell,
        max_output_chars=max_output_chars,
        on_activity=_resolve_on_activity(registry, on_activity),
    )


def interrupt_shell_sessions(
    registry: Any,
    *,
    cancel_event: threading.Event | None,
    reason: str = "user_interrupt",
) -> dict[str, Any]:
    return registry._shell_sessions.interrupt_sessions_for_cancel_event(
        cancel_event,
        reason=reason,
    )


def shell_write_stdin(
    registry: Any,
    session_id: str,
    chars: str,
    *,
    yield_time_ms: int | float | None = None,
    allow_extended_empty_poll: bool = False,
    max_output_chars: int | None = None,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> ToolEvent:
    kwargs: dict[str, Any] = {
        "yield_time_ms": yield_time_ms,
        "allow_extended_empty_poll": allow_extended_empty_poll,
        "on_activity": _resolve_on_activity(registry, on_activity),
        "cancel_event": _resolve_cancel_event(registry, cancel_event),
    }
    if max_output_chars is not None:
        kwargs["max_output_chars"] = max_output_chars
    return registry._shell_sessions.write_stdin(session_id, chars, **kwargs)


def shell_write_stdin_result(
    registry: Any,
    session_id: str,
    chars: str,
    *,
    yield_time_ms: int | float | None = None,
    allow_extended_empty_poll: bool = False,
    max_output_chars: int | None = None,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> CommandExecutionResult:
    kwargs: dict[str, Any] = {
        "yield_time_ms": yield_time_ms,
        "allow_extended_empty_poll": allow_extended_empty_poll,
        "on_activity": _resolve_on_activity(registry, on_activity),
        "cancel_event": _resolve_cancel_event(registry, cancel_event),
    }
    if max_output_chars is not None:
        kwargs["max_output_chars"] = max_output_chars
    return registry._shell_sessions.write_stdin_result(session_id, chars, **kwargs)


def shell_terminate(
    registry: Any,
    session_id: str,
    *,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
) -> ToolEvent:
    return registry._shell_sessions.terminate(
        session_id,
        on_activity=_resolve_on_activity(registry, on_activity),
    )


def shell_terminate_result(
    registry: Any,
    session_id: str,
    *,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
) -> CommandExecutionResult:
    return registry._shell_sessions.terminate_result(
        session_id,
        on_activity=_resolve_on_activity(registry, on_activity),
    )


def shell_subscribe(
    registry: Any,
    session_id: str,
    *,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
) -> ToolEvent:
    return registry._shell_sessions.subscribe(
        session_id,
        on_activity=_resolve_on_activity(registry, on_activity),
    )


def shell_subscribe_result(
    registry: Any,
    session_id: str,
    *,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
) -> CommandExecutionResult:
    return registry._shell_sessions.subscribe_result(
        session_id,
        on_activity=_resolve_on_activity(registry, on_activity),
    )

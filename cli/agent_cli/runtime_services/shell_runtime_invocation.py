from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.models import CommandExecutionResult, ToolEvent


def build_shell_options(
    *,
    cwd: str | None = None,
    login: bool = True,
    tty: bool = False,
    shell: str | None = None,
    timeout_sec: int | None = None,
    max_output_chars: int = 12000,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: Any = None,
) -> dict[str, Any]:
    options: dict[str, Any] = {
        "login": bool(login),
        "tty": bool(tty),
        "max_output_chars": int(max_output_chars),
    }
    if timeout_sec is not None:
        options["timeout_sec"] = int(timeout_sec)
    if cwd is not None:
        options["cwd"] = cwd
    if shell is not None:
        options["shell"] = shell
    if on_activity is not None:
        options["on_activity"] = on_activity
    if cancel_event is not None:
        options["cancel_event"] = cancel_event
    return options


def invoke_shell_callable(fn: Callable[..., Any], command: str, options: dict[str, Any]) -> Any:
    try:
        return fn(command, **options)
    except TypeError:
        return fn(command)


def invoke_shell_session_callable(
    fn: Callable[..., Any],
    session_id: str,
    chars: str,
    *,
    yield_time_ms: int | float | None = None,
    allow_extended_empty_poll: bool = False,
    max_output_chars: int | None = None,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: Any = None,
) -> Any:
    try:
        kwargs: dict[str, Any] = {
            "yield_time_ms": yield_time_ms,
            "allow_extended_empty_poll": allow_extended_empty_poll,
            "on_activity": on_activity,
            "cancel_event": cancel_event,
        }
        if max_output_chars is not None:
            kwargs["max_output_chars"] = max_output_chars
        return fn(session_id, chars, **kwargs)
    except TypeError:
        try:
            kwargs = {
                "yield_time_ms": yield_time_ms,
                "allow_extended_empty_poll": allow_extended_empty_poll,
                "on_activity": on_activity,
            }
            if max_output_chars is not None:
                kwargs["max_output_chars"] = max_output_chars
            return fn(session_id, chars, **kwargs)
        except TypeError:
            return fn(session_id, chars)


def invoke_session_control_callable(
    fn: Callable[..., Any],
    session_id: str,
    *,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
) -> Any:
    try:
        return fn(session_id, on_activity=on_activity)
    except TypeError:
        return fn(session_id)


def write_trace_payload(
    *,
    event: ToolEvent | None = None,
    result: CommandExecutionResult | None = None,
    preview_text: Callable[[Any], str],
) -> dict[str, Any]:
    selected_event = event
    if selected_event is None and isinstance(result, CommandExecutionResult) and result.tool_events:
        last_event = result.tool_events[-1]
        if isinstance(last_event, ToolEvent):
            selected_event = last_event
    payload = dict((selected_event.payload if isinstance(selected_event, ToolEvent) else {}) or {})
    return {
        "ok": bool(selected_event.ok) if isinstance(selected_event, ToolEvent) else None,
        "summary": (
            str(selected_event.summary or "") if isinstance(selected_event, ToolEvent) else None
        ),
        "status": payload.get("status"),
        "exit_code": payload.get("exit_code", payload.get("returncode")),
        "error": str(payload.get("error") or "").strip() or None,
        "output_preview": preview_text(
            payload.get("aggregated_output") or payload.get("stdout") or payload.get("stderr") or ""
        )
        or None,
    }

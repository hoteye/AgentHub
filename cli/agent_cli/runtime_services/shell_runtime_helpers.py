from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.runtime_services import shell_runtime_invocation


def unsupported_interactive_shell_event(action: str, session_id: str) -> ToolEvent:
    normalized_session_id = str(session_id or "").strip()
    return ToolEvent(
        name="shell",
        ok=False,
        summary=f"shell {action} unsupported",
        payload={
            "session_id": normalized_session_id,
            "error": "interactive shell unsupported",
            "status": "unsupported",
        },
    )


def write_stdin_result(
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
    write_shell_stdin_fn: Callable[..., ToolEvent],
    shell_result_from_event_fn: Callable[[str, ToolEvent], CommandExecutionResult],
) -> CommandExecutionResult:
    write_result_fn = getattr(runtime.tools, "shell_write_stdin_result", None)
    normalized_session_id = str(session_id or "").strip()
    trace(
        "tool.runtime.write_stdin.begin",
        session_id=normalized_session_id,
        chars_preview=preview_text(chars),
        yield_time_ms=yield_time_ms,
    )
    if callable(write_result_fn):
        try:
            result = shell_runtime_invocation.invoke_shell_session_callable(
                write_result_fn,
                normalized_session_id,
                chars,
                yield_time_ms=yield_time_ms,
                allow_extended_empty_poll=allow_extended_empty_poll,
                max_output_chars=max_output_chars,
                on_activity=on_activity,
                cancel_event=cancel_event,
            )
        except Exception as exc:
            trace(
                "tool.runtime.write_stdin.failed",
                session_id=normalized_session_id,
                chars_preview=preview_text(chars),
                error=str(exc),
            )
            raise
        if isinstance(result, CommandExecutionResult):
            trace_payload = shell_runtime_invocation.write_trace_payload(
                result=result,
                preview_text=preview_text,
            )
            trace(
                "tool.runtime.write_stdin.completed",
                session_id=normalized_session_id,
                chars_preview=preview_text(chars),
                **trace_payload,
            )
            return result
    event = write_shell_stdin_fn(
        runtime,
        normalized_session_id,
        chars,
        yield_time_ms=yield_time_ms,
        allow_extended_empty_poll=allow_extended_empty_poll,
        max_output_chars=max_output_chars,
        on_activity=on_activity,
        cancel_event=cancel_event,
    )
    trace_payload = shell_runtime_invocation.write_trace_payload(
        event=event,
        preview_text=preview_text,
    )
    trace(
        "tool.runtime.write_stdin.completed",
        session_id=normalized_session_id,
        chars_preview=preview_text(chars),
        **trace_payload,
    )
    return shell_result_from_event_fn("Write shell stdin.", event)


def session_control_result(
    runtime: Any,
    session_id: str,
    *,
    result_attr: str,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
    fallback_event_fn: Callable[..., ToolEvent],
    shell_result_from_event_fn: Callable[[str, ToolEvent], CommandExecutionResult],
    assistant_text: str,
) -> CommandExecutionResult:
    result_fn = getattr(runtime.tools, result_attr, None)
    normalized_session_id = str(session_id or "").strip()
    if callable(result_fn):
        result = shell_runtime_invocation.invoke_session_control_callable(
            result_fn,
            normalized_session_id,
            on_activity=on_activity,
        )
        if isinstance(result, CommandExecutionResult):
            return result
    event = fallback_event_fn(
        runtime,
        normalized_session_id,
        on_activity=on_activity,
    )
    return shell_result_from_event_fn(assistant_text, event)

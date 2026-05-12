from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.tools_core import shell_event_payloads, shell_session_runtime_helpers
from cli.agent_cli.tools_core.shell_session_state import _ShellSession


def completed_replay_event(completed_payload: dict[str, Any]) -> ToolEvent:
    return shell_event_payloads.completed_replay_event(completed_payload)


def subscribe_payload_from_completed_payload(completed_payload: dict[str, Any]) -> dict[str, Any]:
    return shell_event_payloads.subscribe_payload_from_completed_payload(completed_payload)


def replayable_event_history(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return shell_session_runtime_helpers.replayable_event_history(payloads)


def completed_event_history(completed_payload: dict[str, Any]) -> list[dict[str, Any]]:
    return shell_session_runtime_helpers.completed_event_history(
        completed_payload,
        completed_replay_event_fn=completed_replay_event,
    )


def completed_readonly_write_payload(
    completed_payload: dict[str, Any],
    *,
    input_chars: str,
) -> dict[str, Any]:
    return shell_event_payloads.completed_readonly_write_payload(
        completed_payload,
        input_chars=input_chars,
    )


def missing_session_payload(
    session_id: str,
    *,
    call_id: str | None = None,
    process_id: str | None = None,
) -> dict[str, Any]:
    payload = shell_session_runtime_helpers.missing_session_payload(
        session_id,
        call_id=call_id,
        process_id=process_id,
    )
    return payload


def wait_for_completion(
    *,
    session_id: str,
    timeout_sec: int | float | None,
    cancel_event: threading.Event | None,
    on_activity: Callable[[dict[str, Any]], None] | None,
    get_session: Callable[[str], _ShellSession | None],
    get_completed_payload: Callable[[str], dict[str, Any] | None],
    interrupt_session: Callable[[_ShellSession, str], None],
    terminate_process: Callable[[_ShellSession], None],
    build_fallback_payload: Callable[[_ShellSession], dict[str, Any]],
) -> dict[str, Any]:
    session = get_session(session_id)
    if session is None:
        completed_payload = get_completed_payload(session_id)
        if completed_payload is not None:
            return completed_payload
        return shell_session_runtime_helpers.missing_wait_payload(session_id)
    session.add_callback(on_activity)
    deadline = None if timeout_sec is None else time.monotonic() + max(0.0, float(timeout_sec))
    while not session._completed.wait(timeout=0.05):
        if cancel_event is not None and cancel_event.is_set():
            interrupt_session(session, "user_interrupt")
            break
        if deadline is not None and time.monotonic() >= deadline:
            session._timed_out = True
            terminate_process(session)
            break
    session._completed.wait(timeout=1)
    payload = session.final_payload() or build_fallback_payload(session)
    payload.setdefault("exit_code", payload.get("returncode"))
    payload.setdefault("session_id", session.session_id)
    payload.setdefault("call_id", session.call_id)
    payload.setdefault("process_id", session.process_id)
    payload.setdefault("cwd", session.cwd)
    payload.setdefault("login", session.login)
    payload.setdefault("tty", session.tty)
    payload.setdefault("shell", session.shell)
    payload.setdefault("started_at_ms", session.started_at_ms)
    payload.setdefault("ok", False)
    return payload


def write_stdin(
    *,
    session_id: str,
    chars: str,
    yield_time_ms: int | float | None,
    allow_extended_empty_poll: bool = False,
    max_output_chars: int | None = None,
    on_activity: Callable[[dict[str, Any]], None] | None,
    cancel_event: threading.Event | None,
    get_session: Callable[[str], _ShellSession | None],
    get_completed_payload: Callable[[str], dict[str, Any] | None],
    normalize_write_yield_time_ms: Callable[[int | float | None, bool, bool], int],
    drain_incremental_output: Callable[
        [_ShellSession, int, threading.Event | None, int | None], dict[str, Any]
    ],
    interrupt_session: Callable[[_ShellSession, str], None],
    build_fallback_payload: Callable[[_ShellSession], dict[str, Any]],
) -> ToolEvent:
    input_chars = str(chars or "")
    session = get_session(session_id)
    if session is None:
        completed_payload = get_completed_payload(session_id)
        return shell_session_runtime_helpers.missing_or_completed_write_event(
            session_id=session_id,
            input_chars=input_chars,
            on_activity=on_activity,
            completed_payload=completed_payload,
            completed_replay_event_fn=completed_replay_event,
            completed_readonly_write_payload_fn=lambda payload, chars: completed_readonly_write_payload(
                payload,
                input_chars=chars,
            ),
        )

    session.add_callback(on_activity)
    completed_payload = session.final_payload()
    if completed_payload is not None:
        return shell_session_runtime_helpers.completed_live_write_event(
            completed_payload=completed_payload,
            input_chars=input_chars,
            on_activity=on_activity,
            completed_replay_event_fn=completed_replay_event,
            completed_readonly_write_payload_fn=lambda payload, chars: completed_readonly_write_payload(
                payload,
                input_chars=chars,
            ),
        )

    if session.pty_master_fd is None and session.process.stdin is None:
        return shell_session_runtime_helpers.stdin_unavailable_event(session)

    normalized_yield_ms = normalize_write_yield_time_ms(
        yield_time_ms,
        not bool(input_chars),
        allow_extended_empty_poll,
    )
    if not input_chars:
        return shell_session_runtime_helpers.poll_write_event(
            session=session,
            normalized_yield_ms=normalized_yield_ms,
            max_output_chars=max_output_chars,
            cancel_event=cancel_event,
            drain_incremental_output=drain_incremental_output,
        )

    if cancel_event is not None and cancel_event.is_set():
        return shell_session_runtime_helpers.cancelled_write_event(
            session=session,
            input_chars=input_chars,
            normalized_yield_ms=normalized_yield_ms,
            max_output_chars=max_output_chars,
            interrupt_session=interrupt_session,
            drain_incremental_output=drain_incremental_output,
        )

    try:
        if session.pty_master_fd is not None:
            session.write_pty_input(input_chars)
        else:
            session.process.stdin.write(input_chars)
            session.process.stdin.flush()
    except Exception as exc:
        return shell_session_runtime_helpers.write_failed_event(
            session=session,
            input_chars=input_chars,
            exc=exc,
            on_activity=on_activity,
            build_fallback_payload=build_fallback_payload,
            completed_readonly_write_payload_fn=lambda payload, chars: completed_readonly_write_payload(
                payload,
                input_chars=chars,
            ),
        )

    return shell_session_runtime_helpers.successful_write_event(
        session=session,
        input_chars=input_chars,
        normalized_yield_ms=normalized_yield_ms,
        max_output_chars=max_output_chars,
        cancel_event=cancel_event,
        drain_incremental_output=drain_incremental_output,
    )


def subscribe(
    *,
    session_id: str,
    on_activity: Callable[[dict[str, Any]], None] | None,
    get_session: Callable[[str], _ShellSession | None],
    get_completed_payload: Callable[[str], dict[str, Any] | None],
) -> ToolEvent:
    session = get_session(session_id)
    if session is None:
        completed_payload = get_completed_payload(session_id)
        return shell_session_runtime_helpers.subscribe_completed_or_missing(
            session_id=session_id,
            on_activity=on_activity,
            completed_payload=completed_payload,
            subscribe_payload_from_completed_payload_fn=subscribe_payload_from_completed_payload,
            completed_event_history_fn=completed_event_history,
        )
    return shell_session_runtime_helpers.subscribe_live_session(session, on_activity=on_activity)


def terminate(
    *,
    session_id: str,
    on_activity: Callable[[dict[str, Any]], None] | None,
    get_session: Callable[[str], _ShellSession | None],
    get_completed_payload: Callable[[str], dict[str, Any] | None],
    interrupt_session: Callable[[_ShellSession, str], None],
    build_fallback_payload: Callable[[_ShellSession], dict[str, Any]],
) -> ToolEvent:
    session = get_session(session_id)
    if session is None:
        completed_payload = get_completed_payload(session_id)
        return shell_session_runtime_helpers.terminate_missing_or_completed(
            session_id=session_id,
            on_activity=on_activity,
            completed_payload=completed_payload,
            completed_replay_event_fn=completed_replay_event,
        )
    return shell_session_runtime_helpers.terminate_live_session(
        session=session,
        on_activity=on_activity,
        interrupt_session=interrupt_session,
        build_fallback_payload=build_fallback_payload,
        completed_replay_event_fn=completed_replay_event,
    )

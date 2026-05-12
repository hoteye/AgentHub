from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.tools_core import shell_event_payloads
from cli.agent_cli.tools_core.shell_session_state import _ShellSession


def missing_or_completed_write_event(
    *,
    session_id: str,
    input_chars: str,
    on_activity: Callable[[dict[str, Any]], None] | None,
    completed_payload: dict[str, Any] | None,
    completed_replay_event_fn: Callable[[dict[str, Any]], ToolEvent],
    completed_readonly_write_payload_fn: Callable[[dict[str, Any], str], dict[str, Any]],
    missing_session_payload_fn: Callable[[str], dict[str, Any]],
) -> ToolEvent:
    if completed_payload is not None and not input_chars:
        event = completed_replay_event_fn(completed_payload)
        if on_activity is not None:
            on_activity(dict(event.payload))
        return event
    if completed_payload is not None:
        payload = completed_readonly_write_payload_fn(completed_payload, input_chars)
        if on_activity is not None:
            on_activity(dict(payload))
        return ToolEvent(
            name="shell",
            ok=False,
            summary="shell session completed",
            payload=payload,
        )
    return ToolEvent(
        name="shell",
        ok=False,
        summary="shell session missing",
        payload=missing_session_payload_fn(session_id),
    )


def completed_live_write_event(
    *,
    completed_payload: dict[str, Any],
    input_chars: str,
    on_activity: Callable[[dict[str, Any]], None] | None,
    completed_replay_event_fn: Callable[[dict[str, Any]], ToolEvent],
    completed_readonly_write_payload_fn: Callable[[dict[str, Any], str], dict[str, Any]],
) -> ToolEvent:
    if not input_chars:
        event = completed_replay_event_fn(completed_payload)
        if on_activity is not None:
            on_activity(dict(event.payload))
        return event
    payload = completed_readonly_write_payload_fn(completed_payload, input_chars)
    if on_activity is not None:
        on_activity(dict(payload))
    return ToolEvent(
        name="shell",
        ok=False,
        summary="shell session completed",
        payload=payload,
    )


def stdin_unavailable_event(session: _ShellSession) -> ToolEvent:
    return ToolEvent(
        name="shell",
        ok=False,
        summary="shell stdin unavailable",
        payload={
            "session_id": session.session_id,
            "call_id": session.call_id,
            "process_id": session.process_id,
            "status": "stdin_unavailable",
        },
    )


def input_event_payload(session: _ShellSession, *, status: str, input_chars: str) -> dict[str, Any]:
    return shell_event_payloads.event_payload(
        session,
        phase="input",
        kind="input",
        status=status,
        extra={
            "stdin": input_chars,
            "chars": input_chars,
            "interaction_input": input_chars,
        },
    )


def poll_write_event(
    *,
    session: _ShellSession,
    normalized_yield_ms: int,
    max_output_chars: int | None,
    cancel_event: threading.Event | None,
    drain_incremental_output: Callable[
        [_ShellSession, int, threading.Event | None, int | None], dict[str, Any]
    ],
) -> ToolEvent:
    payload = input_event_payload(session, status="noop", input_chars="")
    payload.update(
        drain_incremental_output(session, normalized_yield_ms, cancel_event, max_output_chars)
    )
    return ToolEvent(
        name="shell",
        ok=not bool(payload.get("interrupted") or payload.get("timed_out")),
        summary="shell interrupted" if payload.get("interrupted") else "shell stdin noop",
        payload=payload,
    )


def cancelled_write_event(
    *,
    session: _ShellSession,
    input_chars: str,
    normalized_yield_ms: int,
    max_output_chars: int | None,
    interrupt_session: Callable[[_ShellSession, str], None],
    drain_incremental_output: Callable[
        [_ShellSession, int, threading.Event | None, int | None], dict[str, Any]
    ],
) -> ToolEvent:
    interrupt_session(session, "user_interrupt")
    session._completed.wait(timeout=1)
    payload = input_event_payload(session, status="interrupted", input_chars=input_chars)
    payload.update(drain_incremental_output(session, normalized_yield_ms, None, max_output_chars))
    return ToolEvent(
        name="shell",
        ok=False,
        summary="shell interrupted",
        payload=payload,
    )


def write_failed_event(
    *,
    session: _ShellSession,
    input_chars: str,
    exc: Exception,
    on_activity: Callable[[dict[str, Any]], None] | None,
    build_fallback_payload: Callable[[_ShellSession], dict[str, Any]],
    completed_readonly_write_payload_fn: Callable[[dict[str, Any], str], dict[str, Any]],
) -> ToolEvent:
    session._completed.wait(timeout=0.25)
    completed_payload = session.final_payload()
    if completed_payload is None and session.process.poll() is not None:
        completed_payload = build_fallback_payload(session)
    if completed_payload is not None:
        payload = completed_readonly_write_payload_fn(completed_payload, input_chars)
        if on_activity is not None:
            on_activity(dict(payload))
        return ToolEvent(
            name="shell",
            ok=False,
            summary="shell session completed",
            payload=payload,
        )
    return ToolEvent(
        name="shell",
        ok=False,
        summary="shell stdin write failed",
        payload={
            "session_id": session.session_id,
            "call_id": session.call_id,
            "process_id": session.process_id,
            "error": str(exc),
            "status": "write_failed",
        },
    )


def successful_write_event(
    *,
    session: _ShellSession,
    input_chars: str,
    normalized_yield_ms: int,
    max_output_chars: int | None,
    cancel_event: threading.Event | None,
    drain_incremental_output: Callable[
        [_ShellSession, int, threading.Event | None, int | None], dict[str, Any]
    ],
) -> ToolEvent:
    emitted = input_event_payload(session, status="written", input_chars=input_chars)
    session.emit(emitted)
    payload = input_event_payload(session, status="written", input_chars=input_chars)
    payload.update(
        drain_incremental_output(session, normalized_yield_ms, cancel_event, max_output_chars)
    )
    return ToolEvent(
        name="shell",
        ok=not bool(payload.get("interrupted") or payload.get("timed_out")),
        summary="shell interrupted" if payload.get("interrupted") else "shell stdin written",
        payload=payload,
    )


def subscribe_completed_or_missing(
    *,
    session_id: str,
    on_activity: Callable[[dict[str, Any]], None] | None,
    completed_payload: dict[str, Any] | None,
    subscribe_payload_from_completed_payload_fn: Callable[[dict[str, Any]], dict[str, Any]],
    completed_event_history_fn: Callable[[dict[str, Any]], list[dict[str, Any]]],
    missing_session_payload_fn: Callable[[str], dict[str, Any]],
) -> ToolEvent:
    if completed_payload is not None:
        subscribe_payload = subscribe_payload_from_completed_payload_fn(completed_payload)
        if on_activity is not None:
            on_activity(dict(subscribe_payload))
            for payload in completed_event_history_fn(completed_payload):
                on_activity(dict(payload))
        return ToolEvent(
            name="shell",
            ok=True,
            summary="shell session subscribed",
            payload=subscribe_payload,
        )
    return ToolEvent(
        name="shell",
        ok=False,
        summary="shell session missing",
        payload=missing_session_payload_fn(session_id),
    )


def subscribe_live_session(
    session: _ShellSession,
    *,
    on_activity: Callable[[dict[str, Any]], None] | None,
    replayable_event_history_fn: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
) -> ToolEvent:
    subscribe_payload = shell_event_payloads.event_payload(
        session,
        phase="subscribe",
        kind="subscribe",
        status="subscribed",
    )
    completed_payload = session.final_payload()
    if completed_payload is not None:
        if on_activity is not None:
            on_activity(dict(subscribe_payload))
            _, history = session.snapshot_event_history()
            history = replayable_event_history_fn(history)
            for payload in history:
                on_activity(dict(payload))
        return ToolEvent(
            name="shell",
            ok=True,
            summary="shell session subscribed",
            payload=subscribe_payload,
        )

    if on_activity is None:
        session.emit(subscribe_payload)
        return ToolEvent(
            name="shell",
            ok=True,
            summary="shell session subscribed",
            payload=subscribe_payload,
        )

    replay_buffer: list[dict[str, Any]] = []
    replay_lock = threading.Lock()
    replay_state = {"active": True}

    def _buffering_callback(payload: dict[str, Any]) -> None:
        with replay_lock:
            if replay_state["active"]:
                replay_buffer.append(dict(payload))
                return
        on_activity(dict(payload))

    _, history = session.add_callback_with_history(_buffering_callback)
    history = replayable_event_history_fn(history)
    session.emit(subscribe_payload)
    on_activity(dict(subscribe_payload))
    for payload in history:
        on_activity(dict(payload))

    with replay_lock:
        replay_state["active"] = False
        buffered_payloads = list(replay_buffer)
        replay_buffer.clear()
    for payload in buffered_payloads:
        if (
            str(payload.get("phase") or "") == "subscribe"
            and str(payload.get("status") or "") == "subscribed"
            and str(payload.get("session_id") or "").strip() == str(session.session_id).strip()
        ):
            continue
        on_activity(dict(payload))

    return ToolEvent(
        name="shell",
        ok=True,
        summary="shell session subscribed",
        payload=subscribe_payload,
    )


def terminate_missing_or_completed(
    *,
    session_id: str,
    on_activity: Callable[[dict[str, Any]], None] | None,
    completed_payload: dict[str, Any] | None,
    completed_replay_event_fn: Callable[[dict[str, Any]], ToolEvent],
    missing_session_payload_fn: Callable[[str], dict[str, Any]],
) -> ToolEvent:
    if completed_payload is not None:
        event = completed_replay_event_fn(completed_payload)
        if on_activity is not None:
            on_activity(dict(event.payload))
        return event
    return ToolEvent(
        name="shell",
        ok=False,
        summary="shell session missing",
        payload=missing_session_payload_fn(session_id),
    )


def terminate_live_session(
    *,
    session: _ShellSession,
    on_activity: Callable[[dict[str, Any]], None] | None,
    interrupt_session: Callable[[_ShellSession, str], None],
    build_fallback_payload: Callable[[_ShellSession], dict[str, Any]],
    completed_replay_event_fn: Callable[[dict[str, Any]], ToolEvent],
) -> ToolEvent:
    session.add_callback(on_activity)
    completed_payload = session.final_payload()
    if completed_payload is not None:
        event = completed_replay_event_fn(completed_payload)
        if on_activity is not None:
            on_activity(dict(event.payload))
        return event

    if session.process.poll() is not None:
        session._completed.wait(timeout=1)
        payload = session.final_payload() or build_fallback_payload(session)
        if on_activity is not None:
            on_activity(dict(payload))
        return ToolEvent(
            name="shell",
            ok=bool(payload.get("ok")),
            summary=f"shell rc={payload.get('returncode')}",
            payload=payload,
        )

    interrupt_session(session, "terminate")
    session._completed.wait(timeout=1)
    payload = session.final_payload() or build_fallback_payload(session)
    return ToolEvent(
        name="shell",
        ok=False,
        summary="shell interrupted",
        payload=payload,
    )

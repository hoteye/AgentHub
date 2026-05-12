from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.tools_core import shell_session_runtime_interaction_helpers
from cli.agent_cli.tools_core.shell_session_state import _ShellSession


def replayable_event_history(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    replay: list[dict[str, Any]] = []
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        if str(payload.get("phase") or "") == "subscribe":
            continue
        replay.append(dict(payload))
    return replay


def missing_session_payload(
    session_id: str,
    *,
    call_id: str | None = None,
    process_id: str | None = None,
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "call_id": call_id,
        "process_id": process_id,
        "status": "missing",
    }


def missing_wait_payload(session_id: str) -> dict[str, Any]:
    now_ms = int(time.time() * 1000)
    return {
        "command": "",
        "session_id": str(session_id or "").strip() or None,
        "process_id": None,
        "returncode": None,
        "exit_code": None,
        "stdout": "",
        "stderr": "",
        "stdout_truncated": False,
        "stderr_truncated": False,
        "stdout_total_chars": 0,
        "stderr_total_chars": 0,
        "timed_out": False,
        "interrupted": False,
        "duration_ms": 0,
        "status": "missing",
        "login": True,
        "tty": False,
        "shell": None,
        "cwd": None,
        "started_at_ms": now_ms,
        "finished_at_ms": now_ms,
        "ok": False,
    }


def completed_event_history(
    completed_payload: dict[str, Any],
    *,
    completed_replay_event_fn: Callable[[dict[str, Any]], ToolEvent],
) -> list[dict[str, Any]]:
    raw_history = completed_payload.get("_event_history")
    if isinstance(raw_history, list):
        replay = replayable_event_history(
            [dict(item) for item in raw_history if isinstance(item, dict)]
        )
        if replay:
            return replay
    return [completed_replay_event_fn(completed_payload).payload]


def missing_or_completed_write_event(
    *,
    session_id: str,
    input_chars: str,
    on_activity: Callable[[dict[str, Any]], None] | None,
    completed_payload: dict[str, Any] | None,
    completed_replay_event_fn: Callable[[dict[str, Any]], ToolEvent],
    completed_readonly_write_payload_fn: Callable[[dict[str, Any], str], dict[str, Any]],
) -> ToolEvent:
    return shell_session_runtime_interaction_helpers.missing_or_completed_write_event(
        session_id=session_id,
        input_chars=input_chars,
        on_activity=on_activity,
        completed_payload=completed_payload,
        completed_replay_event_fn=completed_replay_event_fn,
        completed_readonly_write_payload_fn=completed_readonly_write_payload_fn,
        missing_session_payload_fn=missing_session_payload,
    )


def completed_live_write_event(
    *,
    completed_payload: dict[str, Any],
    input_chars: str,
    on_activity: Callable[[dict[str, Any]], None] | None,
    completed_replay_event_fn: Callable[[dict[str, Any]], ToolEvent],
    completed_readonly_write_payload_fn: Callable[[dict[str, Any], str], dict[str, Any]],
) -> ToolEvent:
    return shell_session_runtime_interaction_helpers.completed_live_write_event(
        completed_payload=completed_payload,
        input_chars=input_chars,
        on_activity=on_activity,
        completed_replay_event_fn=completed_replay_event_fn,
        completed_readonly_write_payload_fn=completed_readonly_write_payload_fn,
    )


def stdin_unavailable_event(session: _ShellSession) -> ToolEvent:
    return shell_session_runtime_interaction_helpers.stdin_unavailable_event(session)


def input_event_payload(session: _ShellSession, *, status: str, input_chars: str) -> dict[str, Any]:
    return shell_session_runtime_interaction_helpers.input_event_payload(
        session, status=status, input_chars=input_chars
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
    return shell_session_runtime_interaction_helpers.poll_write_event(
        session=session,
        normalized_yield_ms=normalized_yield_ms,
        max_output_chars=max_output_chars,
        cancel_event=cancel_event,
        drain_incremental_output=drain_incremental_output,
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
    return shell_session_runtime_interaction_helpers.cancelled_write_event(
        session=session,
        input_chars=input_chars,
        normalized_yield_ms=normalized_yield_ms,
        max_output_chars=max_output_chars,
        interrupt_session=interrupt_session,
        drain_incremental_output=drain_incremental_output,
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
    return shell_session_runtime_interaction_helpers.write_failed_event(
        session=session,
        input_chars=input_chars,
        exc=exc,
        on_activity=on_activity,
        build_fallback_payload=build_fallback_payload,
        completed_readonly_write_payload_fn=completed_readonly_write_payload_fn,
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
    return shell_session_runtime_interaction_helpers.successful_write_event(
        session=session,
        input_chars=input_chars,
        normalized_yield_ms=normalized_yield_ms,
        max_output_chars=max_output_chars,
        cancel_event=cancel_event,
        drain_incremental_output=drain_incremental_output,
    )


def subscribe_completed_or_missing(
    *,
    session_id: str,
    on_activity: Callable[[dict[str, Any]], None] | None,
    completed_payload: dict[str, Any] | None,
    subscribe_payload_from_completed_payload_fn: Callable[[dict[str, Any]], dict[str, Any]],
    completed_event_history_fn: Callable[[dict[str, Any]], list[dict[str, Any]]],
) -> ToolEvent:
    return shell_session_runtime_interaction_helpers.subscribe_completed_or_missing(
        session_id=session_id,
        on_activity=on_activity,
        completed_payload=completed_payload,
        subscribe_payload_from_completed_payload_fn=subscribe_payload_from_completed_payload_fn,
        completed_event_history_fn=completed_event_history_fn,
        missing_session_payload_fn=missing_session_payload,
    )


def subscribe_live_session(
    session: _ShellSession, *, on_activity: Callable[[dict[str, Any]], None] | None
) -> ToolEvent:
    return shell_session_runtime_interaction_helpers.subscribe_live_session(
        session,
        on_activity=on_activity,
        replayable_event_history_fn=replayable_event_history,
    )


def terminate_missing_or_completed(
    *,
    session_id: str,
    on_activity: Callable[[dict[str, Any]], None] | None,
    completed_payload: dict[str, Any] | None,
    completed_replay_event_fn: Callable[[dict[str, Any]], ToolEvent],
) -> ToolEvent:
    return shell_session_runtime_interaction_helpers.terminate_missing_or_completed(
        session_id=session_id,
        on_activity=on_activity,
        completed_payload=completed_payload,
        completed_replay_event_fn=completed_replay_event_fn,
        missing_session_payload_fn=missing_session_payload,
    )


def terminate_live_session(
    *,
    session: _ShellSession,
    on_activity: Callable[[dict[str, Any]], None] | None,
    interrupt_session: Callable[[_ShellSession, str], None],
    build_fallback_payload: Callable[[_ShellSession], dict[str, Any]],
    completed_replay_event_fn: Callable[[dict[str, Any]], ToolEvent],
) -> ToolEvent:
    return shell_session_runtime_interaction_helpers.terminate_live_session(
        session=session,
        on_activity=on_activity,
        interrupt_session=interrupt_session,
        build_fallback_payload=build_fallback_payload,
        completed_replay_event_fn=completed_replay_event_fn,
    )

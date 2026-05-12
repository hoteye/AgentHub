from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.models import ToolEvent
from cli.agent_cli.tools_core import shell_session_runtime
from cli.agent_cli.tools_core.shell_completed_runtime import ShellCompletedSessionCache
from cli.agent_cli.tools_core.shell_session_state import _ShellSession


def init_manager(
    manager: Any,
    *,
    host_platform: HostPlatform,
    max_live_sessions: int = 32,
    completed_cache_limit: int = 128,
    workspace_root_getter: Callable[[], str | None] | None = None,
) -> None:
    manager._host_platform = host_platform
    manager._max_live_sessions = max(1, int(max_live_sessions))
    manager._completed_cache_limit = max(1, int(completed_cache_limit))
    manager._workspace_root_getter = workspace_root_getter
    manager._lock = threading.Lock()
    manager._sessions = {}
    manager._completed_sessions = {}
    manager._completed_session_order = []
    manager._completed_cache = ShellCompletedSessionCache(
        lock=manager._lock,
        completed_sessions=manager._completed_sessions,
        completed_session_order=manager._completed_session_order,
        completed_cache_limit=manager._completed_cache_limit,
    )


def get_session(manager: Any, session_id: str) -> _ShellSession | None:
    with manager._lock:
        return manager._sessions.get(str(session_id or "").strip())


def get_completed_payload(manager: Any, session_id: str) -> dict[str, Any] | None:
    return manager._completed_cache.get_completed_payload(session_id)


def record_completed_payload(
    manager: Any,
    session_id: str,
    payload: dict[str, Any],
    *,
    event_history: list[dict[str, Any]] | None = None,
) -> None:
    manager._completed_cache.record_completed_payload(
        session_id,
        payload,
        event_history=event_history,
    )


def sessions_to_prune_after_start(manager: Any, *, keep_session_id: str) -> list[_ShellSession]:
    with manager._lock:
        if len(manager._sessions) <= manager._max_live_sessions:
            return []
        candidates = [
            session
            for session_id, session in manager._sessions.items()
            if session_id != keep_session_id and not session._completed.is_set()
        ]
    if not candidates:
        return []
    prune_count = max(0, len(candidates) - (manager._max_live_sessions - 1))
    if prune_count <= 0:
        return []
    candidates.sort(key=lambda item: item.started_at)
    return candidates[:prune_count]


def prune_session(manager: Any, session: _ShellSession) -> None:
    if session._completed.is_set():
        return
    session._pruned = True
    session._interrupted = True
    manager._terminate_process(session)
    session._completed.wait(timeout=1)


def workspace_root(manager: Any) -> str | None:
    getter = manager._workspace_root_getter
    if not callable(getter):
        return None
    try:
        value = getter()
    except Exception:
        return None
    text = str(value or "").strip()
    return text or None


def interrupt_sessions_for_cancel_event(
    manager: Any,
    cancel_event: threading.Event | None,
    *,
    reason: str = "user_interrupt",
) -> dict[str, Any]:
    if cancel_event is None:
        return {
            "ok": True,
            "session_ids": [],
            "count": 0,
        }
    with manager._lock:
        sessions = [
            session
            for session in manager._sessions.values()
            if session.cancel_event is cancel_event and not session._completed.is_set()
        ]
    interrupted_session_ids: list[str] = []
    for session in sessions:
        manager._interrupt_session(session, reason=reason)
        interrupted_session_ids.append(session.session_id)
    return {
        "ok": True,
        "session_ids": interrupted_session_ids,
        "count": len(interrupted_session_ids),
    }


def wait_for_completion(
    manager: Any,
    session_id: str,
    *,
    timeout_sec: int | float | None = None,
    cancel_event: threading.Event | None = None,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    return shell_session_runtime.wait_for_completion(
        session_id=session_id,
        timeout_sec=timeout_sec,
        cancel_event=cancel_event,
        on_activity=on_activity,
        get_session=manager._get_session,
        get_completed_payload=manager._get_completed_payload,
        interrupt_session=lambda session, reason: manager._interrupt_session(
            session, reason=reason
        ),
        terminate_process=manager._terminate_process,
        build_fallback_payload=manager._build_fallback_payload,
    )


def write_stdin(
    manager: Any,
    session_id: str,
    chars: str,
    *,
    yield_time_ms: int | float | None = None,
    allow_extended_empty_poll: bool = False,
    max_output_chars: int | None = None,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> ToolEvent:
    return shell_session_runtime.write_stdin(
        session_id=session_id,
        chars=chars,
        yield_time_ms=yield_time_ms,
        allow_extended_empty_poll=allow_extended_empty_poll,
        max_output_chars=max_output_chars,
        on_activity=on_activity,
        cancel_event=cancel_event,
        get_session=manager._get_session,
        get_completed_payload=manager._get_completed_payload,
        normalize_write_yield_time_ms=lambda value, empty_input, allow_extended: manager._normalize_write_yield_time_ms(
            value,
            empty_input=empty_input,
            allow_extended_empty_poll=allow_extended,
        ),
        drain_incremental_output=lambda session, wait_ms, event, output_limit=None: manager._drain_incremental_output(
            session,
            yield_time_ms=wait_ms,
            max_output_chars=output_limit,
            cancel_event=event,
        ),
        interrupt_session=lambda session, reason: manager._interrupt_session(
            session, reason=reason
        ),
        build_fallback_payload=manager._build_fallback_payload,
    )


def subscribe(
    manager: Any,
    session_id: str,
    *,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
) -> ToolEvent:
    return shell_session_runtime.subscribe(
        session_id=session_id,
        on_activity=on_activity,
        get_session=manager._get_session,
        get_completed_payload=manager._get_completed_payload,
    )


def terminate(
    manager: Any,
    session_id: str,
    *,
    on_activity: Callable[[dict[str, Any]], None] | None = None,
) -> ToolEvent:
    return shell_session_runtime.terminate(
        session_id=session_id,
        on_activity=on_activity,
        get_session=manager._get_session,
        get_completed_payload=manager._get_completed_payload,
        interrupt_session=lambda session, reason: manager._interrupt_session(
            session, reason=reason
        ),
        build_fallback_payload=manager._build_fallback_payload,
    )


def remove_live_session(manager: Any, session_id: str) -> None:
    with manager._lock:
        manager._sessions.pop(str(session_id or "").strip(), None)

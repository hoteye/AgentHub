from __future__ import annotations

import threading
import uuid
from typing import Any, Dict, List, Optional, Tuple

from cli.agent_cli.debug_timeline import log_timeline, timeline_debug_enabled
from cli.agent_cli.models import (
    ActivityEvent,
    ToolEvent,
    REFERENCE_CONVERSATION_INTERRUPTED_TEXT,
)


def _interrupt_trace(stage: str, **payload: Any) -> None:
    if not timeline_debug_enabled():
        return
    log_timeline(stage, **payload)


def has_active_run(runtime: Any) -> bool:
    with runtime._run_state_lock:
        return runtime._active_run_token is not None


def active_run_token(runtime: Any) -> Optional[str]:
    with runtime._run_state_lock:
        return runtime._active_run_token


def interrupt_active_run(runtime: Any) -> Dict[str, Any]:
    with runtime._run_state_lock:
        token = runtime._active_run_token
        label = runtime._active_run_label
        cancel_event = runtime._cancel_event
        already_requested = bool(cancel_event is not None and cancel_event.is_set())
        _interrupt_trace(
            "runtime.interrupt.requested",
            thread_id=str(getattr(runtime, "thread_id", "") or "").strip() or None,
            run_token=token,
            run_label=label,
            cancel_event_present=cancel_event is not None,
            already_requested=already_requested,
        )
        if token is None or cancel_event is None:
            _interrupt_trace(
                "runtime.interrupt.no_active_run",
                thread_id=str(getattr(runtime, "thread_id", "") or "").strip() or None,
                run_token=token,
                run_label=label,
            )
            return {
                "ok": False,
                "interrupted": False,
                "reason": "no_active_run",
            }
        cancel_event.set()
    interrupted_shell_sessions: list[str] = []
    provider_stream_interrupted = False
    interrupt_shell_sessions = getattr(getattr(runtime, "tools", None), "interrupt_shell_sessions", None)
    if callable(interrupt_shell_sessions):
        try:
            shell_interrupt_result = interrupt_shell_sessions(
                cancel_event=cancel_event,
                reason="user_interrupt",
            )
        except Exception as exc:
            _interrupt_trace(
                "runtime.interrupt.shell_sessions_failed",
                thread_id=str(getattr(runtime, "thread_id", "") or "").strip() or None,
                run_token=token,
                run_label=label,
                error=str(exc),
            )
        else:
            interrupted_shell_sessions = [
                str(item).strip()
                for item in list((shell_interrupt_result or {}).get("session_ids") or [])
                if str(item).strip()
            ]
            _interrupt_trace(
                "runtime.interrupt.shell_sessions_interrupted",
                thread_id=str(getattr(runtime, "thread_id", "") or "").strip() or None,
                run_token=token,
                run_label=label,
                shell_session_ids=interrupted_shell_sessions,
                shell_session_count=len(interrupted_shell_sessions),
            )
    interrupt_provider_stream = getattr(getattr(runtime, "agent", None), "interrupt_active_provider_stream", None)
    if callable(interrupt_provider_stream):
        try:
            provider_stream_interrupted = bool(interrupt_provider_stream())
        except Exception as exc:
            _interrupt_trace(
                "runtime.interrupt.provider_stream_failed",
                thread_id=str(getattr(runtime, "thread_id", "") or "").strip() or None,
                run_token=token,
                run_label=label,
                error=str(exc),
            )
        else:
            _interrupt_trace(
                "runtime.interrupt.provider_stream_interrupted",
                thread_id=str(getattr(runtime, "thread_id", "") or "").strip() or None,
                run_token=token,
                run_label=label,
                provider_stream_interrupted=provider_stream_interrupted,
            )
    _interrupt_trace(
        "runtime.interrupt.cancel_event_set",
        thread_id=str(getattr(runtime, "thread_id", "") or "").strip() or None,
        run_token=token,
        run_label=label,
        already_requested=already_requested,
        shell_session_count=len(interrupted_shell_sessions),
        provider_stream_interrupted=provider_stream_interrupted,
    )
    runtime._emit_activity(
        ActivityEvent(
            title=f"Interrupt requested for {label or token}",
            status="info",
            kind="interrupt",
            code="interrupt.requested",
            params={"run_label": label or "", "run_token": token or ""},
        )
    )
    _interrupt_trace(
        "runtime.interrupt.activity_emitted",
        thread_id=str(getattr(runtime, "thread_id", "") or "").strip() or None,
        run_token=token,
        run_label=label,
    )
    return {
        "ok": True,
        "interrupted": True,
        "run_token": token,
        "run_label": label,
        "already_requested": already_requested,
        "shell_session_ids": interrupted_shell_sessions,
        "shell_session_count": len(interrupted_shell_sessions),
        "provider_stream_interrupted": provider_stream_interrupted,
    }


def begin_run(runtime: Any, text: str) -> str:
    with runtime._run_state_lock:
        if runtime._active_run_token is not None:
            raise RuntimeError("runtime is busy")
        token = uuid.uuid4().hex[:12]
        normalized_text = str(text or "").strip()
        runtime._active_run_token = token
        runtime._active_run_label = normalized_text[:120]
        runtime._active_run_text = normalized_text
        runtime._cancel_event = threading.Event()
    _interrupt_trace(
        "runtime.run.begin",
        thread_id=str(getattr(runtime, "thread_id", "") or "").strip() or None,
        run_token=token,
        run_label=normalized_text[:120],
    )
    return token


def finish_run(runtime: Any, token: str) -> None:
    with runtime._run_state_lock:
        if runtime._active_run_token != token:
            _interrupt_trace(
                "runtime.run.finish.skipped",
                thread_id=str(getattr(runtime, "thread_id", "") or "").strip() or None,
                requested_token=token,
                active_run_token=runtime._active_run_token,
            )
            return
        cancel_requested = bool(runtime._cancel_event is not None and runtime._cancel_event.is_set())
        run_label = runtime._active_run_label
        runtime._active_run_token = None
        runtime._active_run_label = ""
        runtime._active_run_text = ""
        runtime._cancel_event = None
    _interrupt_trace(
        "runtime.run.finish",
        thread_id=str(getattr(runtime, "thread_id", "") or "").strip() or None,
        run_token=token,
        run_label=run_label,
        cancel_requested=cancel_requested,
    )


def is_interrupt_requested(runtime: Any) -> bool:
    cancel_getter = getattr(runtime, "_active_cancel_event", None)
    if callable(cancel_getter):
        try:
            cancel_event = cancel_getter()
        except Exception:
            cancel_event = runtime._cancel_event
    else:
        cancel_event = runtime._cancel_event
    requested = bool(cancel_event is not None and cancel_event.is_set())
    if requested:
        _interrupt_trace(
            "runtime.interrupt.poll.hit",
            thread_id=str(getattr(runtime, "thread_id", "") or "").strip() or None,
            run_token=getattr(runtime, "_active_run_token", None),
            run_label=getattr(runtime, "_active_run_label", ""),
        )
    return requested


def interrupt_event() -> ToolEvent:
    return ToolEvent(
        name="interrupted",
        ok=False,
        summary="execution interrupted",
        payload={
            "ok": False,
            "interrupted": True,
            "reason": "user_interrupt",
        },
    )


def interrupt_tuple(runtime: Any) -> Tuple[str, List[ToolEvent]]:
    event = interrupt_event()
    _interrupt_trace(
        "runtime.interrupt.observed",
        thread_id=str(getattr(runtime, "thread_id", "") or "").strip() or None,
        run_token=getattr(runtime, "_active_run_token", None),
        run_label=getattr(runtime, "_active_run_label", ""),
    )
    runtime._emit_activity(
        ActivityEvent(
            title="Execution interrupted",
            status="info",
            kind="interrupt",
            code="interrupt.completed",
            params={"reason": "user_interrupt"},
        )
    )
    return (REFERENCE_CONVERSATION_INTERRUPTED_TEXT, [event])

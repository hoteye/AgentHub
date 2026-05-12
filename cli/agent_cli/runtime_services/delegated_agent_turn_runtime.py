from __future__ import annotations

import threading
from typing import Any, Dict

from cli.agent_cli.models import (
    CommandExecutionResult,
    replay_input_items_from_turn_events,
    tool_events_include_interrupt,
)
from cli.agent_cli.runtime_services import delegated_agent_turn_helpers_runtime as delegated_agent_turn_helpers_runtime_service
from cli.agent_cli.runtime_services import delegated_agent_turn_runtime_helpers as turn_runtime_helpers


def _preview_text(value: Any, *, max_chars: int = 240) -> str:
    return delegated_agent_turn_helpers_runtime_service.preview_text(value, max_chars=max_chars)


def _runtime_now_iso() -> str:
    return delegated_agent_turn_helpers_runtime_service.runtime_now_iso()


def _sync_delegated_run_record(
    runtime: Any,
    session: Any,
    *,
    forced_status: str | None = None,
    forced_summary: str | None = None,
) -> None:
    delegated_agent_turn_helpers_runtime_service.sync_delegated_run_record(
        runtime,
        session,
        forced_status=forced_status,
        forced_summary=forced_summary,
    )


def _preserve_terminal_reason(session: Any, fallback: str) -> str:
    return delegated_agent_turn_helpers_runtime_service.preserve_terminal_reason(session, fallback)


def delegated_plan_kwargs(
    runtime: Any,
    planner: Any,
    *,
    session: Any,
) -> Dict[str, Any]:
    return turn_runtime_helpers.delegated_plan_kwargs_impl(runtime, planner, session=session)


def run_delegated_agent_turn(
    runtime: Any,
    session: Any,
    *,
    user_text: str,
) -> CommandExecutionResult:
    planner = runtime._delegated_planner(
        session.config,
        timeout=session.timeout,
    )
    intent = planner.plan(
        str(user_text or "").strip(),
        **delegated_plan_kwargs(runtime, planner, session=session),
    )
    return runtime._execute_agent_intent_result(intent)


def apply_delegated_turn_result(
    runtime: Any,
    session: Any,
    *,
    user_text: str,
    step_id: str = "",
    result: CommandExecutionResult,
) -> None:
    turn_runtime_helpers.apply_delegated_turn_result_impl(
        runtime,
        session,
        user_text=user_text,
        step_id=step_id,
        result=result,
        preview_text_fn=lambda value: _preview_text(value, max_chars=160),
    )


def apply_interrupted_delegated_turn_result(
    runtime: Any,
    session: Any,
    *,
    user_text: str,
    step_id: str = "",
    result: CommandExecutionResult,
) -> None:
    turn_runtime_helpers.apply_interrupted_delegated_turn_result_impl(
        runtime,
        session,
        user_text=user_text,
        step_id=step_id,
        result=result,
        preserve_terminal_reason_fn=_preserve_terminal_reason,
    )


def run_delegated_agent_worker(runtime: Any, agent_id: str) -> None:
    session = runtime._delegated_session(agent_id)
    current_worker = threading.current_thread()
    while True:
        should_return = False
        with session.condition:
            if session.closed:
                session.status = "closed"
                if not str(session.terminal_reason or "").strip():
                    session.terminal_reason = _preserve_terminal_reason(
                        session,
                        "close_requested" if session.close_requested else "closed",
                    )
                session.scheduler_reason = ""
                session.updated_at = _runtime_now_iso()
                session.condition.notify_all()
                should_return = True
            elif not session.queued_inputs:
                if session.close_requested:
                    session.closed = True
                    session.status = "closed"
                    session.terminal_reason = _preserve_terminal_reason(session, "close_requested")
                elif session.status not in {"failed", "completed"}:
                    session.status = "completed" if str(session.assistant_text or "").strip() else "idle"
                    session.terminal_reason = "completed" if session.status == "completed" else ""
                elif session.status == "completed" and not str(session.terminal_reason or "").strip():
                    session.terminal_reason = "completed"
                elif session.status == "failed" and not str(session.terminal_reason or "").strip():
                    session.terminal_reason = "failed"
                session.scheduler_reason = ""
                session.updated_at = _runtime_now_iso()
                session.condition.notify_all()
                should_return = True
            elif runtime._normalized_delegated_queue_item(session.queued_inputs[0]) is None:
                session.queued_inputs.pop(0)
                session.updated_at = _runtime_now_iso()
                session.condition.notify_all()
                continue
        if should_return:
            _sync_delegated_run_record(runtime, session, forced_summary="delegated worker finalized")
            runtime._sync_delegated_background_task(session)
            with session.condition:
                if not session.closed and session.active_input is None and session.queued_inputs:
                    session.condition.notify_all()
                    runtime._notify_delegated_scheduler()
                    continue
                if session.worker is current_worker:
                    session.worker = None
                session.condition.notify_all()
            runtime._notify_delegated_scheduler()
            return
        decision = runtime._wait_for_delegated_slot(session)
        if not bool(decision.get("allowed")):
            continue
        user_text = ""
        step_id = ""
        skip_turn = False
        with session.condition:
            if session.closed:
                session.scheduler_reason = ""
                session.updated_at = _runtime_now_iso()
                session.condition.notify_all()
                skip_turn = True
            elif not session.queued_inputs:
                session.scheduler_reason = ""
                session.updated_at = _runtime_now_iso()
                session.condition.notify_all()
                skip_turn = True
            else:
                item = runtime._normalized_delegated_queue_item(session.queued_inputs.pop(0))
                if item is None:
                    session.scheduler_reason = ""
                    session.updated_at = _runtime_now_iso()
                    session.condition.notify_all()
                    skip_turn = True
                else:
                    user_text = str(item.get("message") or "").strip()
                    step_id = str(item.get("step_id") or "").strip()
                    session.cancel_event.clear()
                    session.active_input = dict(item)
                    session.current_step_id = step_id
                    session.status = "running"
                    session.terminal_reason = ""
                    session.scheduler_reason = ""
                    session.updated_at = _runtime_now_iso()
                    if step_id:
                        runtime._update_delegated_step(
                            session,
                            step_id=step_id,
                            status="running",
                            summary="running",
                            started=True,
                        )
                        runtime._record_delegated_checkpoint(
                            session,
                            kind="step_started",
                            status="running",
                            summary=f"started {step_id}",
                            step_id=step_id,
                        )
                    session.condition.notify_all()
        runtime._sync_delegated_background_task(session)
        _sync_delegated_run_record(runtime, session, forced_status="running", forced_summary="delegated turn running")
        if skip_turn:
            runtime._notify_delegated_scheduler()
            continue
        suppress_direct_callbacks = str(session.delegation_mode or "").strip().lower() == "background"
        try:
            with runtime._bound_cancel_event(session.cancel_event):
                with runtime._bound_callback_suppression(
                    suppress_activity=suppress_direct_callbacks,
                    suppress_turn_events=suppress_direct_callbacks,
                ):
                    result = run_delegated_agent_turn(runtime, session, user_text=user_text)
        except Exception as exc:
            interrupted_result: CommandExecutionResult | None = None
            if session.cancel_event.is_set():
                interrupt_text, interrupt_events = runtime._interrupt_tuple()
                interrupted_result = CommandExecutionResult(
                    assistant_text=interrupt_text,
                    tool_events=interrupt_events,
                )
            with session.condition:
                if interrupted_result is not None:
                    apply_interrupted_delegated_turn_result(
                        runtime,
                        session,
                        user_text=user_text,
                        step_id=step_id,
                        result=interrupted_result,
                    )
                    session.cancel_event.clear()
                    if session.close_requested and not session.queued_inputs:
                        session.closed = True
                        session.status = "closed"
                        session.terminal_reason = _preserve_terminal_reason(session, "close_requested")
                    elif session.queued_inputs:
                        session.status = "queued"
                        session.terminal_reason = ""
                    else:
                        session.status = "completed" if str(session.assistant_text or "").strip() else "idle"
                        session.terminal_reason = "completed" if session.status == "completed" else ""
                    _sync_delegated_run_record(runtime, session, forced_summary="delegated turn interrupted")
                else:
                    session.active_input = None
                    session.scheduler_reason = ""
                    session.last_input_text = user_text
                    session.assistant_text = ""
                    session.error = str(exc)
                    session.last_tool_events = []
                    session.last_item_events = []
                    session.last_turn_events = []
                    session.adopted = False
                    session.adopted_at = ""
                    if session.close_requested and not session.queued_inputs:
                        session.closed = True
                        session.status = "closed"
                        session.terminal_reason = _preserve_terminal_reason(session, "close_requested")
                    elif session.queued_inputs:
                        session.status = "queued"
                        session.terminal_reason = ""
                    else:
                        session.status = "failed"
                        session.terminal_reason = "failed"
                    if step_id:
                        runtime._update_delegated_step(
                            session,
                            step_id=step_id,
                            status="failed",
                            summary=_preview_text(str(exc), max_chars=160) or "failed",
                            error=str(exc),
                            finished=True,
                        )
                        runtime._record_delegated_checkpoint(
                            session,
                            kind="step_failed",
                            status="failed",
                            summary=f"failed {step_id}",
                            step_id=step_id,
                        )
                    runtime._refresh_delegated_current_step_id(session)
                    session.updated_at = _runtime_now_iso()
                    _sync_delegated_run_record(
                        runtime,
                        session,
                        forced_status="failed",
                        forced_summary="delegated turn failed",
                    )
                session.condition.notify_all()
            runtime._sync_delegated_background_task(session)
            runtime._notify_delegated_scheduler()
            continue
        with session.condition:
            if tool_events_include_interrupt(list(result.tool_events or [])):
                apply_interrupted_delegated_turn_result(
                    runtime,
                    session,
                    user_text=user_text,
                    step_id=step_id,
                    result=result,
                )
                session.cancel_event.clear()
                if session.close_requested and not session.queued_inputs:
                    session.closed = True
                    session.status = "closed"
                    session.terminal_reason = _preserve_terminal_reason(session, "close_requested")
                elif session.queued_inputs:
                    session.status = "queued"
                    session.terminal_reason = ""
                else:
                    session.status = "completed" if str(session.assistant_text or "").strip() else "idle"
                    session.terminal_reason = "completed" if session.status == "completed" else ""
            else:
                apply_delegated_turn_result(
                    runtime,
                    session,
                    user_text=user_text,
                    step_id=step_id,
                    result=result,
                )
                if session.close_requested and not session.queued_inputs:
                    session.closed = True
                    session.status = "closed"
                    session.terminal_reason = _preserve_terminal_reason(session, "close_requested")
                elif session.queued_inputs:
                    session.status = "queued"
                    session.terminal_reason = ""
                else:
                    session.status = "completed"
                    session.terminal_reason = "completed"
            _sync_delegated_run_record(runtime, session, forced_summary="delegated turn completed")
            session.condition.notify_all()
        runtime._sync_delegated_background_task(session)
        runtime._notify_delegated_scheduler()

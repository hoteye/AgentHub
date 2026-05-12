from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any

from cli.agent_cli.models import ActivityEvent, PromptAttachment, ToolEvent
from cli.agent_cli.runtime_core import (
    active_run_token as core_active_run_token,
)
from cli.agent_cli.runtime_core import (
    begin_run as core_begin_run,
)
from cli.agent_cli.runtime_core import (
    finish_run as core_finish_run,
)
from cli.agent_cli.runtime_core import (
    has_active_run as core_has_active_run,
)
from cli.agent_cli.runtime_core import (
    interrupt_active_run as core_interrupt_active_run,
)
from cli.agent_cli.runtime_core import (
    interrupt_event as core_interrupt_event,
)
from cli.agent_cli.runtime_core import (
    interrupt_tuple as core_interrupt_tuple,
)
from cli.agent_cli.runtime_core import (
    is_interrupt_requested as core_is_interrupt_requested,
)
from cli.agent_cli.runtime_core import (
    list_threads as core_list_threads,
)
from cli.agent_cli.runtime_core import (
    restore_provider_state as core_restore_provider_state,
)
from cli.agent_cli.runtime_core import (
    resume_thread as core_resume_thread,
)
from cli.agent_cli.runtime_core import (
    start_thread as core_start_thread,
)
from cli.agent_cli.runtime_core import (
    state_value as core_state_value,
)
from cli.agent_cli.runtime_services import (
    run_thread_normalization_helpers_runtime,
    run_thread_projection_helpers_runtime,
    run_thread_pure_helpers_runtime,
)


def callback_suppression_state(runtime: Any) -> dict[str, bool]:
    raw_state = getattr(runtime._thread_local_state, "callback_suppression", None)
    if not isinstance(raw_state, dict):
        return {
            "activity": False,
            "turn_events": False,
        }
    return {
        "activity": bool(raw_state.get("activity")),
        "turn_events": bool(raw_state.get("turn_events")),
    }


def activity_callbacks_suppressed(runtime: Any) -> bool:
    return bool(callback_suppression_state(runtime).get("activity"))


def turn_event_callbacks_suppressed(runtime: Any) -> bool:
    return bool(callback_suppression_state(runtime).get("turn_events"))


@contextmanager
def bound_callback_suppression(
    runtime: Any,
    *,
    suppress_activity: bool = False,
    suppress_turn_events: bool = False,
):
    next_state = {
        "activity": activity_callbacks_suppressed(runtime) or bool(suppress_activity),
        "turn_events": turn_event_callbacks_suppressed(runtime) or bool(suppress_turn_events),
    }
    if not next_state["activity"] and not next_state["turn_events"]:
        yield
        return
    had_previous = hasattr(runtime._thread_local_state, "callback_suppression")
    previous = getattr(runtime._thread_local_state, "callback_suppression", None)
    runtime._thread_local_state.callback_suppression = next_state
    try:
        yield
    finally:
        if had_previous:
            runtime._thread_local_state.callback_suppression = previous
        else:
            try:
                delattr(runtime._thread_local_state, "callback_suppression")
            except AttributeError:
                pass


def emit_activity(runtime: Any, event: ActivityEvent) -> None:
    if activity_callbacks_suppressed(runtime):
        return
    callback = runtime.activity_callback
    if callback is not None:
        callback(event)


def emit_turn_event(runtime: Any, event: dict[str, Any]) -> None:
    if turn_event_callbacks_suppressed(runtime):
        return
    callback = runtime.turn_event_callback
    if callback is not None:
        callback(dict(event))


def normalized_turn_event_value(cls: Any, value: Any) -> Any:
    return run_thread_normalization_helpers_runtime.normalized_turn_event_value(
        value,
        normalize_nested_value_fn=cls._normalized_turn_event_value,
    )


def turn_event_replay_signature(cls: Any, event: dict[str, Any]) -> str:
    return run_thread_normalization_helpers_runtime.turn_event_replay_signature(
        event,
        normalized_turn_event_value_fn=cls._normalized_turn_event_value,
    )


def active_cancel_event(runtime: Any) -> threading.Event | None:
    delegated_cancel_event = getattr(runtime._thread_local_state, "cancel_event", None)
    if isinstance(delegated_cancel_event, threading.Event):
        return delegated_cancel_event
    return runtime._cancel_event


@contextmanager
def bound_cancel_event(runtime: Any, cancel_event: threading.Event | None):
    had_previous = hasattr(runtime._thread_local_state, "cancel_event")
    previous = getattr(runtime._thread_local_state, "cancel_event", None)
    runtime._thread_local_state.cancel_event = cancel_event
    try:
        yield
    finally:
        if had_previous:
            runtime._thread_local_state.cancel_event = previous
        else:
            try:
                delattr(runtime._thread_local_state, "cancel_event")
            except AttributeError:
                pass


def has_active_run(runtime: Any) -> bool:
    return core_has_active_run(runtime)


def _pending_steer_lock(runtime: Any):
    lock = getattr(runtime, "_pending_steer_lock", None)
    if lock is None:
        lock = getattr(runtime, "_run_state_lock", None)
    return lock


def _pending_steer_input_items(runtime: Any) -> list[dict[str, Any]]:
    raw = getattr(runtime, "_pending_steer_input_items", None)
    if not isinstance(raw, list):
        raw = []
        runtime._pending_steer_input_items = raw
    return raw


def _clear_pending_steer_input_items(runtime: Any) -> None:
    lock = _pending_steer_lock(runtime)
    if lock is None:
        runtime._pending_steer_input_items = []
        return
    with lock:
        _pending_steer_input_items(runtime).clear()


def pending_steer_supported(runtime: Any) -> bool:
    return bool(getattr(runtime, "_pending_steer_enabled", False))


def _steer_message_input_item(
    runtime: Any,
    *,
    text: str,
    attachments: list[PromptAttachment],
) -> dict[str, Any] | None:
    return run_thread_pure_helpers_runtime.build_steer_message_input_item(
        text=text,
        attachments=attachments,
        planner_message_input_item_builder=getattr(runtime, "_planner_message_input_item", None),
    )


def steer_active_run(
    runtime: Any,
    text: str,
    *,
    attachments: list[PromptAttachment] | None = None,
) -> dict[str, Any]:
    if not has_active_run(runtime):
        return {"accepted": False, "fallback_queue": True, "reason": "no_active_run"}
    if not pending_steer_supported(runtime):
        return {"accepted": False, "fallback_queue": True, "reason": "unsupported"}
    normalized_text = str(text or "").strip()
    if not normalized_text:
        return {"accepted": False, "fallback_queue": False, "reason": "empty_text"}
    item = _steer_message_input_item(
        runtime,
        text=normalized_text,
        attachments=list(attachments or []),
    )
    if not isinstance(item, dict):
        return {"accepted": False, "fallback_queue": False, "reason": "invalid_input_item"}
    lock = _pending_steer_lock(runtime)
    if lock is None:
        items = _pending_steer_input_items(runtime)
        items.append(dict(item))
        queued_count = len(items)
    else:
        with lock:
            items = _pending_steer_input_items(runtime)
            items.append(dict(item))
            queued_count = len(items)
    return {
        "accepted": True,
        "fallback_queue": False,
        "reason": "accepted",
        "queued_count": queued_count,
    }


def take_pending_steer_input_items(
    runtime: Any, *, limit: int | None = None
) -> list[dict[str, Any]]:
    take_limit = run_thread_normalization_helpers_runtime.normalized_pending_steer_limit(limit)
    lock = _pending_steer_lock(runtime)
    if lock is None:
        return run_thread_pure_helpers_runtime.take_pending_steer_items(
            _pending_steer_input_items(runtime),
            limit=take_limit,
        )
    with lock:
        return run_thread_pure_helpers_runtime.take_pending_steer_items(
            _pending_steer_input_items(runtime),
            limit=take_limit,
        )


def has_thread(runtime: Any) -> bool:
    return bool(runtime.thread_id)


def start_thread(
    runtime: Any,
    *,
    name: str | None = None,
    cwd: str | None = None,
) -> dict[str, Any]:
    return core_start_thread(runtime, name=name, cwd=cwd)


def list_threads(runtime: Any, *, limit: int = 50, cwd: str | None = None) -> list[dict[str, Any]]:
    return core_list_threads(runtime, limit=limit, cwd=cwd)


def resume_thread(
    runtime: Any,
    thread_id: str | None = None,
    *,
    path: str | None = None,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = core_resume_thread(runtime, thread_id, path=path, history=history)
    resumed_planner_state = run_thread_projection_helpers_runtime.resumed_planner_state(
        payload,
        normalized_history_item_fn=runtime._normalized_history_item,
        normalized_planner_input_item_fn=runtime._normalized_planner_input_item,
        planner_history_limit=runtime._PLANNER_HISTORY_LIMIT_MESSAGES,
    )
    planner_history = list(resumed_planner_state["planner_history"])
    if isinstance(payload, dict):
        runtime._planner_input_items = list(resumed_planner_state["planner_input_items"])
    if not runtime._planner_input_items:
        runtime._planner_input_items = runtime._planner_conversation_input_items()
    if not planner_history:
        planner_history = runtime._planner_history()
    runtime.history = planner_history[-runtime._PLANNER_HISTORY_LIMIT_MESSAGES :]
    if len(runtime.history_turns) > 100:
        runtime.history_turns = runtime.history_turns[-100:]
    if isinstance(payload, dict):
        state = payload.get("state")
        if isinstance(state, dict) and "delegated_agents" in state:
            with runtime._delegated_agents_lock:
                restored_agent_ids = set(runtime._delegated_agents)
            filtered_delegated_agents = (
                run_thread_projection_helpers_runtime.filtered_delegated_agents(
                    list(state.get("delegated_agents") or []),
                    restored_agent_ids=restored_agent_ids,
                )
            )
            payload["state"] = dict(state)
            if filtered_delegated_agents:
                payload["state"]["delegated_agents"] = filtered_delegated_agents
            else:
                payload["state"].pop("delegated_agents", None)
    return payload


def active_run_token(runtime: Any) -> str | None:
    return core_active_run_token(runtime)


def interrupt_active_run(runtime: Any) -> dict[str, Any]:
    return core_interrupt_active_run(runtime)


def begin_run(runtime: Any, text: str) -> str:
    token = core_begin_run(runtime, text)
    _clear_pending_steer_input_items(runtime)
    return token


def finish_run(runtime: Any, token: str) -> None:
    should_clear_pending = core_active_run_token(runtime) == token
    core_finish_run(runtime, token)
    if should_clear_pending:
        _clear_pending_steer_input_items(runtime)


def is_interrupt_requested(runtime: Any) -> bool:
    return core_is_interrupt_requested(runtime)


def interrupt_event() -> ToolEvent:
    return core_interrupt_event()


def interrupt_tuple(runtime: Any):
    return core_interrupt_tuple(runtime)


def runtime_state_value(state: dict[str, Any], key: str) -> str | None:
    return core_state_value(state, key)


def restore_provider_state(runtime: Any, state: dict[str, Any]) -> None:
    core_restore_provider_state(runtime, state)


def emit_shell_activity(runtime: Any, payload: dict[str, Any]) -> None:
    phase = run_thread_projection_helpers_runtime.shell_phase(payload)
    if phase == "started":
        runtime._emit_activity(
            run_thread_projection_helpers_runtime.shell_started_activity(payload)
        )
        return
    if phase == "output":
        activity = run_thread_projection_helpers_runtime.shell_output_activity(payload)
        if activity is None:
            return
        runtime._emit_activity(activity)
        return
    if phase == "completed":
        event = run_thread_projection_helpers_runtime.shell_completed_tool_event(payload)
        for activity in runtime._activity_events_for_tool_event(event):
            runtime._emit_activity(activity)


def running_activity_for_tool(tool_name: str) -> ActivityEvent:
    return run_thread_projection_helpers_runtime.running_activity_for_tool(tool_name)


def plan_activity_event(plan: dict[str, Any]) -> ActivityEvent | None:
    return run_thread_projection_helpers_runtime.plan_activity_event(plan)

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.models import ToolEvent


def _normalized_optional_bool(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        if value == 1:
            return True
        if value == 0:
            return False
        return None
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def snapshot_session_payload(
    runtime: Any,
    session: Any,
    *,
    payload: dict[str, Any],
    progress_payload: dict[str, Any],
) -> dict[str, Any]:
    snapshot = dict(payload)
    snapshot["live_snapshot_version"] = 1
    snapshot["base_url"] = str(getattr(session.config, "base_url", "") or "")
    snapshot["protocol_run_id"] = str(getattr(session, "protocol_run_id", "") or "")
    snapshot["protocol_parent_run_id"] = str(getattr(session, "protocol_parent_run_id", "") or "")
    snapshot["protocol_thread_id"] = str(getattr(session, "protocol_thread_id", "") or "")
    snapshot["resume_source"] = str(getattr(session, "resume_source", "") or "spawn_agent")
    if str(getattr(session, "subagent_type", "") or "").strip():
        snapshot["subagent_type"] = str(getattr(session, "subagent_type", "") or "").strip()
    snapshot["seed_input_items"] = [
        dict(item) for item in list(session.seed_input_items or []) if isinstance(item, dict)
    ]
    snapshot["seed_history"] = [
        dict(item) for item in list(session.seed_history or []) if isinstance(item, dict)
    ]
    snapshot["replay_input_items"] = [
        dict(item) for item in list(session.replay_input_items or []) if isinstance(item, dict)
    ]
    snapshot["replay_history"] = [
        dict(item) for item in list(session.replay_history or []) if isinstance(item, dict)
    ]
    snapshot["progress_steps"] = list(progress_payload.get("steps") or [])
    snapshot["progress_checkpoints"] = list(progress_payload.get("checkpoints") or [])
    if str(progress_payload.get("current_step_id") or "").strip():
        snapshot["current_step_id"] = str(progress_payload.get("current_step_id") or "").strip()
    snapshot["queued_inputs"] = [
        normalized
        for normalized in (
            runtime._normalized_delegated_queue_item(item)
            for item in list(session.queued_inputs or [])
        )
        if normalized is not None
    ]
    active_input = runtime._normalized_delegated_queue_item(session.active_input)
    if active_input is not None:
        snapshot["active_input"] = active_input
    snapshot["last_tool_events"] = [
        event.to_dict()
        for event in list(session.last_tool_events or [])
        if isinstance(event, ToolEvent)
    ]
    snapshot["last_item_events"] = [
        dict(item) for item in list(session.last_item_events or []) if isinstance(item, dict)
    ]
    snapshot["last_turn_events"] = [
        dict(item) for item in list(session.last_turn_events or []) if isinstance(item, dict)
    ]
    current_step_id = str(progress_payload.get("current_step_id") or "").strip()
    if current_step_id:
        snapshot["live_current_step_id"] = current_step_id
    snapshot["live_current_step_status"] = str(
        progress_payload.get("current_step_status") or ""
    ).strip()
    snapshot["live_current_step_title"] = str(
        progress_payload.get("current_step_title") or ""
    ).strip()
    latest_checkpoint = progress_payload.get("latest_checkpoint")
    if not isinstance(latest_checkpoint, dict):
        checkpoints = list(progress_payload.get("checkpoints") or [])
        if checkpoints and isinstance(checkpoints[-1], dict):
            latest_checkpoint = dict(checkpoints[-1])
    if isinstance(latest_checkpoint, dict):
        snapshot["live_last_checkpoint_kind"] = str(latest_checkpoint.get("kind") or "").strip()
        snapshot["live_last_checkpoint_at"] = str(
            latest_checkpoint.get("at")
            or latest_checkpoint.get("ts")
            or latest_checkpoint.get("timestamp")
            or ""
        ).strip()
    else:
        snapshot["live_last_checkpoint_kind"] = ""
        snapshot["live_last_checkpoint_at"] = ""
    snapshot["live_has_active_input"] = active_input is not None
    snapshot["live_queued_input_count"] = len(snapshot["queued_inputs"])
    snapshot["live_last_tool_event_count"] = len(snapshot["last_tool_events"])
    snapshot["live_last_item_event_count"] = len(snapshot["last_item_events"])
    snapshot["live_last_turn_event_count"] = len(snapshot["last_turn_events"])
    snapshot["live_snapshot_exported_at"] = str(
        payload.get("updated_at") or payload.get("created_at") or ""
    ).strip()
    return snapshot


def restore_resolution_context(runtime: Any, raw: dict[str, Any]) -> dict[str, Any]:
    raw_status = str(raw.get("status") or "").strip().lower()
    timeout = raw.get("timeout")
    if timeout not in (None, ""):
        try:
            timeout = int(timeout)
        except (TypeError, ValueError):
            timeout = None
    else:
        timeout = None
    queued_inputs = [
        normalized
        for normalized in (
            runtime._normalized_delegated_queue_item(item)
            for item in list(raw.get("queued_inputs") or [])
        )
        if normalized is not None
    ]
    active_input = runtime._normalized_delegated_queue_item(raw.get("active_input"))
    return {
        "raw_status": raw_status,
        "timeout": timeout,
        "resolution_kwargs": {
            "model": str(raw.get("model_key") or raw.get("model") or "").strip() or None,
            "provider": str(raw.get("provider_name") or "").strip() or None,
            "reasoning_effort": str(raw.get("reasoning_effort") or "").strip() or None,
            "timeout": timeout,
        },
        "queued_inputs": queued_inputs,
        "active_input": active_input,
    }


def restored_session_kwargs(
    runtime: Any,
    raw: dict[str, Any],
    *,
    agent_id: str,
    role: str,
    config: Any,
    resolution: Any,
    timeout: int | None,
    queued_inputs: list[dict[str, Any]],
    raw_status: str,
    active_input: dict[str, Any] | None,
    now_iso_fn: Callable[[], str],
) -> dict[str, Any]:
    normalized_close_requested = _normalized_optional_bool(raw.get("close_requested"))
    normalized_closed = _normalized_optional_bool(raw.get("closed"))
    close_requested = normalized_close_requested is True or raw_status == "closing"
    closed = normalized_closed is True or raw_status in {"closing", "closed"}
    delegation_mode = str(raw.get("delegation_mode") or "").strip()
    wait_required = None
    if "wait_required" in raw:
        wait_required = _normalized_optional_bool(raw.get("wait_required"))
    if (
        wait_required is None
        and delegation_mode.lower() == "background"
        and str(role or "").strip().lower() == "teammate"
    ):
        wait_required = False
    restored_queue = list(queued_inputs or [])
    if closed or close_requested:
        restored_queue = []
    elif active_input is not None:
        restored_queue.insert(0, active_input)
    assistant_text = str(raw.get("text") or "").strip()
    error = str(raw.get("error") or "").strip()
    last_wait_blocked_ms = None
    if raw.get("last_wait_blocked_ms") not in (None, ""):
        try:
            last_wait_blocked_ms = int(raw.get("last_wait_blocked_ms"))
        except (TypeError, ValueError):
            last_wait_blocked_ms = None
    return {
        "agent_id": agent_id,
        "role": role,
        "config": config,
        "timeout": timeout,
        "source": str(raw.get("source") or resolution.source or ""),
        "protocol_run_id": str(raw.get("protocol_run_id") or raw.get("run_id") or ""),
        "protocol_parent_run_id": str(
            raw.get("protocol_parent_run_id") or raw.get("parent_run_id") or ""
        ),
        "protocol_thread_id": str(raw.get("protocol_thread_id") or raw.get("thread_id") or ""),
        "resume_source": "thread_resume_restore",
        "delegation_reason": str(raw.get("delegation_reason") or ""),
        "delegation_mode": delegation_mode,
        "wait_required": wait_required,
        "task_shape": str(raw.get("task_shape") or ""),
        "subagent_type": str(raw.get("subagent_type") or ""),
        "background_priority": (
            str(raw.get("background_priority") or "").strip()
            or runtime._delegated_background_priority(
                role=role,
                delegation_mode=delegation_mode,
                wait_required=wait_required,
            )
        ),
        "parallel_group": (
            str(raw.get("parallel_group") or "").strip()
            or runtime._delegated_parallel_group(raw.get("task_shape"))
        ),
        "scheduler_reason": str(raw.get("scheduler_reason") or ""),
        "seed_input_items": [
            normalized
            for normalized in (
                runtime._normalized_planner_input_item(item)
                for item in list(raw.get("seed_input_items") or [])
            )
            if normalized is not None
        ],
        "seed_history": [
            normalized
            for normalized in (
                runtime._normalized_history_item(item)
                for item in list(raw.get("seed_history") or [])
            )
            if normalized is not None
        ],
        "replay_input_items": [
            normalized
            for normalized in (
                runtime._normalized_planner_input_item(item)
                for item in list(raw.get("replay_input_items") or [])
            )
            if normalized is not None
        ],
        "replay_history": [
            normalized
            for normalized in (
                runtime._normalized_history_item(item)
                for item in list(raw.get("replay_history") or [])
            )
            if normalized is not None
        ],
        "progress_steps": [
            dict(item) for item in list(raw.get("progress_steps") or []) if isinstance(item, dict)
        ],
        "progress_checkpoints": [
            dict(item)
            for item in list(raw.get("progress_checkpoints") or [])
            if isinstance(item, dict)
        ],
        "current_step_id": str(raw.get("current_step_id") or ""),
        "queued_inputs": restored_queue,
        "created_at": str(raw.get("created_at") or "") or now_iso_fn(),
        "updated_at": str(raw.get("updated_at") or "") or now_iso_fn(),
        "status": runtime._restored_delegated_status(
            status=raw.get("status"),
            queued_inputs=restored_queue,
            close_requested=close_requested,
            closed=closed,
            assistant_text=assistant_text,
            error=error,
        ),
        "last_input_text": str(raw.get("last_input_text") or ""),
        "assistant_text": assistant_text,
        "error": error,
        "last_tool_events": [
            ToolEvent.from_dict(item)
            for item in list(raw.get("last_tool_events") or [])
            if isinstance(item, dict)
        ],
        "last_item_events": [
            dict(item) for item in list(raw.get("last_item_events") or []) if isinstance(item, dict)
        ],
        "last_turn_events": [
            dict(item) for item in list(raw.get("last_turn_events") or []) if isinstance(item, dict)
        ],
        "turn_count": max(0, int(raw.get("turn_count") or 0)),
        "adopted": _normalized_optional_bool(raw.get("adopted")) is True,
        "adopted_at": str(raw.get("adopted_at") or ""),
        "last_wait_reason": str(raw.get("last_wait_reason") or ""),
        "last_wait_decision": str(raw.get("last_wait_decision") or ""),
        "last_wait_at": str(raw.get("last_wait_at") or ""),
        "last_wait_blocked_ms": last_wait_blocked_ms,
        "last_wait_timed_out": _normalized_optional_bool(raw.get("last_wait_timed_out")) is True,
        "terminal_reason": str(raw.get("terminal_reason") or ""),
        "close_requested": close_requested,
        "closed": closed,
    }

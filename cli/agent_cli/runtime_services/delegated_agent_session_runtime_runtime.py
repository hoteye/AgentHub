from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli import builtin_agent_profiles_runtime


def resolved_spawn_context(
    *,
    task: str,
    role: str,
    async_mode: bool | None,
    reason: str | None,
    mode: str | None,
    wait_required: Any,
    task_shape: str | None,
    subagent_type: str | None = None,
    codex_collab_payload: bool = False,
    infer_spawn_agent_metadata_fn: Callable[..., dict[str, Any]],
    resolve_spawn_agent_async_mode_fn: Callable[..., bool],
    resolved_delegation_metadata_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    task_text = str(task or "").strip()
    if not task_text:
        raise ValueError("spawn_agent requires a non-empty task")
    delegation_metadata = infer_spawn_agent_metadata_fn(
        {
            "task": task_text,
            "reason": reason,
            "mode": mode,
            "wait_required": wait_required,
            "task_shape": task_shape,
            "subagent_type": subagent_type,
            "codex_collab_payload": bool(codex_collab_payload),
        },
        async_mode=async_mode,
        role=role,
    )
    if async_mode is not None:
        effective_async_mode = bool(async_mode)
    elif str(mode or "").strip():
        effective_async_mode = resolve_spawn_agent_async_mode_fn(
            {
                "mode": mode,
                "codex_collab_payload": bool(codex_collab_payload),
            },
            async_mode=None,
            role=role,
        )
    else:
        effective_async_mode = resolve_spawn_agent_async_mode_fn(
            {
                "task": task_text,
                "role": role,
                "mode": delegation_metadata.get("delegation_mode"),
                "codex_collab_payload": bool(codex_collab_payload),
            },
            async_mode=None,
            role=role,
        )
    delegation_metadata = resolved_delegation_metadata_fn(
        delegation_metadata,
        role=role,
        effective_async_mode=effective_async_mode,
    )
    normalized_subagent_type = builtin_agent_profiles_runtime.normalize_subagent_type(
        subagent_type or delegation_metadata.get("subagent_type")
    )
    if normalized_subagent_type:
        delegation_metadata["subagent_type"] = normalized_subagent_type
    return {
        "task_text": task_text,
        "effective_async_mode": effective_async_mode,
        "delegation_metadata": delegation_metadata,
    }


def delegated_result(
    *,
    tool_name: str,
    target: str,
    payload: dict[str, Any],
    assistant_text: str,
    summary: str,
    tool_event_factory: Callable[..., Any],
    generic_tool_call_item_events_fn: Callable[..., list[dict[str, Any]]],
) -> Any:
    event = tool_event_factory(
        name=tool_name,
        ok=True,
        summary=summary,
        payload=payload,
    )
    return {
        "event": event,
        "assistant_text": assistant_text,
        "item_events": generic_tool_call_item_events_fn(
            tool_name=tool_name,
            arguments={"target": str(target or "").strip()},
            ok=True,
            summary=summary,
            structured_content=dict(event.payload or {}),
        ),
    }


def close_session(
    *,
    session: Any,
    now_iso_fn: Callable[[], str],
    refresh_current_step_id_fn: Callable[[Any], Any],
    record_checkpoint_fn: Callable[..., None],
    delegated_agent_payload_fn: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    worker_running = bool(session.worker is not None and session.worker.is_alive())
    session.close_requested = True
    session.terminal_reason = "close_requested"
    session.queued_inputs.clear()
    if not worker_running:
        session.closed = True
        session.status = "closed"
    else:
        if session.active_input is not None:
            session.cancel_event.set()
        session.status = "closing"
    session.scheduler_reason = ""
    refresh_current_step_id_fn(session)
    session.updated_at = now_iso_fn()
    record_checkpoint_fn(
        session,
        kind="session_close_requested",
        status="closing" if worker_running else "closed",
        summary=f"close requested for {session.agent_id}",
        step_id=str(session.current_step_id or "").strip(),
    )
    return {
        "payload": delegated_agent_payload_fn(session),
        "worker_running": worker_running,
    }


def resume_session(
    *,
    session: Any,
    now_iso_fn: Callable[[], str],
    refresh_current_step_id_fn: Callable[[Any], Any],
    record_checkpoint_fn: Callable[..., None],
    delegated_agent_payload_fn: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    should_start = False
    if session.closed or session.close_requested:
        session.closed = False
        session.close_requested = False
        session.cancel_event.clear()
        session.scheduler_reason = ""
        session.resume_source = "resume_agent"
        session.terminal_reason = ""
        if session.queued_inputs:
            session.status = "queued"
            should_start = True
        else:
            session.status = "completed" if str(session.assistant_text or "").strip() else "idle"
        refresh_current_step_id_fn(session)
        session.updated_at = now_iso_fn()
        record_checkpoint_fn(
            session,
            kind="session_resumed",
            status=str(session.status or "").strip() or "idle",
            summary=f"resumed {session.agent_id}",
            step_id=str(session.current_step_id or "").strip(),
        )
    return {
        "payload": delegated_agent_payload_fn(session),
        "should_start": should_start,
    }

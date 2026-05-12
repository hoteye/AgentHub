from __future__ import annotations

from typing import Any, Callable, Dict

from cli.agent_cli.runtime_services import (
    delegated_agent_background_state_runtime as background_state_runtime,
    delegated_agent_background_state_transition_runtime as background_state_transition_runtime,
)


def reset_delegated_agent_state_impl(runtime: Any) -> None:
    with runtime._delegated_agents_lock:
        sessions = list(runtime._delegated_agents.values())
        runtime._delegated_agents = {}
    for session in sessions:
        with session.condition:
            cleanup_candidate = background_state_transition_runtime.delegated_orphan_cleanup_candidate(
                status=session.status,
                queued_inputs=list(session.queued_inputs or []),
                active_input=session.active_input,
            )
        if cleanup_candidate:
            runtime._request_delegated_session_cleanup(
                session,
                reason="orphan_cleanup",
                summary=f"orphan cleanup for {session.agent_id}",
            )
            continue
        runtime._sync_delegated_background_task(session)
    runtime._notify_delegated_scheduler()


def restore_delegated_agent_state_impl(
    runtime: Any,
    state: Dict[str, Any],
    *,
    session_class: Any,
    now_iso_fn: Callable[[], str],
) -> None:
    raw_sessions = list(state.get("delegated_agents") or [])
    runtime._reset_delegated_agent_state()
    restored_sessions: Dict[str, Any] = {}
    for raw in raw_sessions:
        if not isinstance(raw, dict):
            continue
        agent_id = str(raw.get("agent_id") or "").strip()
        role = str(raw.get("role") or "").strip() or "subagent"
        if not agent_id:
            continue
        restore_context = background_state_runtime.restore_resolution_context(runtime, raw)
        raw_status = restore_context["raw_status"]
        timeout = restore_context["timeout"]
        resolution_kwargs = restore_context["resolution_kwargs"]
        queued_inputs = restore_context["queued_inputs"]
        active_input = restore_context["active_input"]
        try:
            resolution = runtime.agent.resolve_delegate_execution(role, **resolution_kwargs)
        except Exception as exc:
            if background_state_transition_runtime.delegated_orphan_cleanup_candidate(
                status=raw.get("status"),
                queued_inputs=queued_inputs,
                active_input=active_input,
            ):
                runtime._record_orphaned_delegated_background_task(
                    raw,
                    reason="restore_resolution_failed",
                    error=f"{type(exc).__name__}: {exc}",
                )
            continue
        config = getattr(resolution, "config", None)
        if config is None:
            if background_state_transition_runtime.delegated_orphan_cleanup_candidate(
                status=raw.get("status"),
                queued_inputs=queued_inputs,
                active_input=active_input,
            ):
                runtime._record_orphaned_delegated_background_task(
                    raw,
                    reason="restore_resolution_failed",
                    error="delegated agent unavailable during restore",
                )
            continue
        session = session_class(
            **background_state_runtime.restored_session_kwargs(
                runtime,
                raw,
                agent_id=agent_id,
                role=role,
                config=config,
                resolution=resolution,
                timeout=timeout,
                queued_inputs=queued_inputs,
                raw_status=raw_status,
                active_input=active_input,
                now_iso_fn=now_iso_fn,
            )
        )
        runtime._refresh_delegated_current_step_id(session)
        restored_sessions[agent_id] = session
    with runtime._delegated_agents_lock:
        runtime._delegated_agents = restored_sessions
    runtime._notify_delegated_scheduler()
    for session in restored_sessions.values():
        with session.condition:
            should_start = bool(session.queued_inputs) and not session.closed
        if should_start:
            runtime._start_delegated_agent_worker(session)

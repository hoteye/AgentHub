from __future__ import annotations

from typing import Any, Callable, Dict, List

from cli.agent_cli.runtime_services import (
    delegated_agent_background_payload_runtime as background_payload_runtime,
    delegated_agent_background_runtime_helpers_state_helpers as state_helpers,
    delegated_agent_background_state_runtime as background_state_runtime,
    delegated_agent_background_state_transition_runtime as background_state_transition_runtime,
)


def sync_delegated_run_record(
    runtime: Any,
    session: Any,
    *,
    forced_status: str | None = None,
    forced_summary: str | None = None,
) -> None:
    def read(name: str) -> Any:
        if isinstance(session, dict):
            return session.get(name)
        return getattr(session, name, None)

    manager = getattr(runtime, "run_manager", None)
    if manager is None:
        return
    agent_id = str(read("agent_id") or "").strip()
    protocol_run_id = str(read("protocol_run_id") or "").strip()
    run_id = protocol_run_id or f"delegated:{agent_id or 'unknown'}"
    if not run_id:
        return
    role = str(read("role") or "").strip().lower()
    delegation_mode = str(read("delegation_mode") or "").strip().lower()
    kind = "background" if role == "teammate" and delegation_mode == "background" else "task"
    parent_run_id = str(read("protocol_parent_run_id") or "").strip()
    thread_id = (
        str(read("protocol_thread_id") or "").strip()
        or str(getattr(runtime, "thread_id", "") or "").strip()
    )
    status = str(forced_status or "").strip().lower()
    if not status:
        session_status = str(read("status") or "").strip().lower()
        terminal_reason = str(read("terminal_reason") or "").strip().lower()
        if session_status in {"running", "starting"}:
            status = "running"
        elif session_status == "failed":
            status = "failed"
        elif session_status == "completed":
            status = "completed"
        elif session_status == "closed":
            if terminal_reason == "failed":
                status = "failed"
            elif terminal_reason == "completed":
                status = "completed"
            else:
                status = "cancelled"
        else:
            status = "created"
    summary = str(forced_summary or "").strip() or f"delegated session {status}"
    payload = {
        "agent_id": agent_id,
        "role": str(read("role") or "").strip(),
        "session_status": str(read("status") or "").strip(),
        "terminal_reason": str(read("terminal_reason") or "").strip(),
        "delegation_mode": str(read("delegation_mode") or "").strip(),
    }
    if manager.get(run_id) is None:
        try:
            manager.create(
                run_id=run_id,
                kind=kind,
                thread_id=thread_id,
                parent_run_id=parent_run_id,
                summary="delegated session created",
                payload=payload,
            )
        except Exception:
            return
    try:
        manager.update(run_id, status=status, summary=summary, payload=payload)
    except Exception:
        return


def sync_delegated_background_task(
    runtime: Any,
    session: Any,
    *,
    preview_text_fn: Callable[..., str],
) -> None:
    sync_delegated_run_record(runtime, session, forced_summary="delegated background sync")
    if str(session.role or "").strip().lower() != "teammate":
        return
    if str(session.delegation_mode or "").strip().lower() != "background":
        return
    adapter = runtime._background_task_adapter_if_enabled()
    if adapter is None:
        return

    from cli.agent_cli.background_tasks import BackgroundTaskStatus, TaskResult as BackgroundTaskResult

    payload = runtime._delegated_agent_payload(session)
    progress_payload = runtime._delegated_progress_summary(session, include_history=True)
    task_id = runtime._delegated_background_task_id(session)
    previous_result = None
    previous_artifact: Dict[str, Any] = {}
    try:
        previous_result = adapter.storage.get_result(task_id)
    except Exception:
        previous_result = None
    if previous_result is not None:
        previous_artifact = dict(getattr(previous_result, "artifact", {}) or {})
    text = str(payload.get("text") or "").strip()
    error = str(payload.get("error") or "").strip()
    terminal_reason = str(payload.get("terminal_reason") or "").strip()
    status_text = runtime._delegated_background_task_status(
        str(payload.get("status") or ""),
        has_text=bool(text),
        terminal_reason=terminal_reason,
    )
    candidate_notification_state = runtime._delegated_background_notification_state(
        status=str(payload.get("status") or ""),
        adopted=bool(payload.get("adopted")),
        terminal_reason=terminal_reason,
    )
    notification_state = background_payload_runtime.stabilized_notification_state(
        candidate_state=candidate_notification_state,
        checkpoint_count=progress_payload.get("checkpoint_count"),
        previous_artifact=previous_artifact,
    )
    if notification_state == "orphaned":
        status_text = "cancelled"
    result_contract = dict(payload.get("result_contract") or {})
    snapshot_payload = background_payload_runtime.sync_snapshot_payload(
        runtime,
        session,
        payload=payload,
        progress_payload=progress_payload,
        task_id=task_id,
        notification_state=notification_state,
    )
    snapshot_payload = background_payload_runtime.stabilize_orphan_snapshot_payload(
        snapshot_payload=snapshot_payload,
        payload=payload,
        previous_artifact=previous_artifact,
    )
    try:
        snapshot_path = adapter.storage.write_result_snapshot(task_id, snapshot_payload, suffix="delegated")
        finished_at = str(payload.get("updated_at") or "") if status_text in {"completed", "failed", "cancelled"} else ""
        if status_text == "cancelled" and not finished_at:
            finished_at = str(payload.get("updated_at") or "")
        artifact = background_payload_runtime.sync_result_artifact(
            session=session,
            payload=payload,
            progress_payload=progress_payload,
            snapshot_path=snapshot_path,
            notification_state=notification_state,
            text=text,
            error=error,
            preview_text_fn=preview_text_fn,
        )
        artifact = background_payload_runtime.stabilize_orphan_result_artifact(
            artifact=artifact,
            payload=payload,
            previous_artifact=previous_artifact,
        )
        summary_text = str(result_contract.get("summary") or runtime._delegated_agent_summary_text(session))
        if notification_state == "orphaned" and previous_result is not None and str(previous_result.summary or "").strip():
            summary_text = str(previous_result.summary or "")
        if notification_state == "orphaned" and not error and previous_result is not None and str(previous_result.error or "").strip():
            error = str(previous_result.error or "")
        adapter.storage.upsert_result(
            BackgroundTaskResult(
                task_id=task_id,
                status=BackgroundTaskStatus(status_text),
                started_at=str(payload.get("created_at") or ""),
                finished_at=finished_at,
                summary=summary_text,
                artifact=artifact,
                error=error,
            )
        )
    except Exception:
        return


def record_orphaned_delegated_background_task(
    runtime: Any,
    raw_session: Dict[str, Any],
    *,
    reason: str,
    error: str = "",
    preview_text_fn: Callable[..., str],
    now_iso_fn: Callable[[], str],
) -> None:
    role = str(raw_session.get("role") or "").strip().lower()
    delegation_mode = str(raw_session.get("delegation_mode") or "").strip().lower()
    agent_id = str(raw_session.get("agent_id") or "").strip()
    if role != "teammate" or delegation_mode != "background" or not agent_id:
        return
    adapter = runtime._background_task_adapter_if_enabled()
    if adapter is None:
        return

    from cli.agent_cli.background_tasks import BackgroundTaskStatus, TaskResult as BackgroundTaskResult

    task_id = f"bg_delegate_{agent_id}"
    summary = f"delegated session orphaned: {reason}"
    queued_inputs = list(raw_session.get("queued_inputs") or [])
    active_input = raw_session.get("active_input")
    goal = background_payload_runtime.orphan_goal(raw_session, queued_inputs, active_input)
    snapshot_payload = background_payload_runtime.orphan_snapshot_payload(
        raw_session=raw_session,
        task_id=task_id,
        goal=goal,
        agent_id=agent_id,
        role=role,
        reason=reason,
        summary=summary,
    )
    try:
        snapshot_path = adapter.storage.write_result_snapshot(task_id, snapshot_payload, suffix="delegated")
        artifact = background_payload_runtime.orphan_result_artifact(
            raw_session=raw_session,
            snapshot_path=snapshot_path,
            agent_id=agent_id,
            role=role,
            reason=reason,
            error=error,
            preview_text_fn=preview_text_fn,
        )
        adapter.storage.upsert_result(
            BackgroundTaskResult(
                task_id=task_id,
                status=BackgroundTaskStatus.CANCELLED,
                started_at=str(raw_session.get("created_at") or ""),
                finished_at=now_iso_fn(),
                summary=summary,
                artifact=artifact,
                error=str(error or ""),
            )
        )
        sync_delegated_run_record(
            runtime,
            raw_session,
            forced_status="cancelled",
            forced_summary=f"delegated session orphaned: {reason}",
        )
    except Exception:
        return


def cleanup_delegated_sessions_for_role(runtime: Any, role_name: str, *, reason: str) -> int:
    normalized_role = str(role_name or "").strip().lower()
    if not normalized_role:
        return 0
    with runtime._delegated_agents_lock:
        sessions = list(runtime._delegated_agents.values())
    cleaned = 0
    for session in sessions:
        with session.condition:
            matches_role = str(session.role or "").strip().lower() == normalized_role
            cleanup_candidate = background_state_transition_runtime.delegated_orphan_cleanup_candidate(
                status=session.status,
                queued_inputs=list(session.queued_inputs or []),
                active_input=session.active_input,
            )
        if not matches_role or not cleanup_candidate:
            continue
        if runtime._request_delegated_session_cleanup(
            session,
            reason=reason,
            summary=f"{reason} cleanup for {session.agent_id}",
        ):
            cleaned += 1
    return cleaned


def snapshot_delegated_agent_session(runtime: Any, session: Any) -> Dict[str, Any]:
    with session.condition:
        payload = runtime._delegated_agent_payload(session)
        progress_payload = runtime._delegated_progress_summary(session, include_history=True)
        return background_state_runtime.snapshot_session_payload(
            runtime,
            session,
            payload=payload,
            progress_payload=progress_payload,
        )


def delegated_agent_state_snapshot(runtime: Any) -> List[Dict[str, Any]]:
    with runtime._delegated_agents_lock:
        sessions = list(runtime._delegated_agents.values())
    return [runtime._snapshot_delegated_agent_session(session) for session in sessions]


def reset_delegated_agent_state(runtime: Any) -> None:
    state_helpers.reset_delegated_agent_state_impl(runtime)


def restore_delegated_agent_state(
    runtime: Any,
    state: Dict[str, Any],
    *,
    session_class: Any,
    now_iso_fn: Callable[[], str],
) -> None:
    state_helpers.restore_delegated_agent_state_impl(
        runtime,
        state,
        session_class=session_class,
        now_iso_fn=now_iso_fn,
    )

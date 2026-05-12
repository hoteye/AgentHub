from __future__ import annotations

import time
from typing import Any, Callable


def sync_delegated_run_record(
    runtime: Any,
    session: Any,
    *,
    forced_status: str | None = None,
    forced_summary: str | None = None,
) -> None:
    manager = getattr(runtime, "run_manager", None)
    if manager is None:
        return
    agent_id = str(getattr(session, "agent_id", "") or "").strip()
    protocol_run_id = str(getattr(session, "protocol_run_id", "") or "").strip()
    run_id = protocol_run_id or f"delegated:{agent_id or 'unknown'}"
    if not run_id:
        return
    role = str(getattr(session, "role", "") or "").strip().lower()
    delegation_mode = str(getattr(session, "delegation_mode", "") or "").strip().lower()
    kind = "background" if role == "teammate" and delegation_mode == "background" else "task"
    parent_run_id = str(getattr(session, "protocol_parent_run_id", "") or "").strip()
    thread_id = (
        str(getattr(session, "protocol_thread_id", "") or "").strip()
        or str(getattr(runtime, "thread_id", "") or "").strip()
    )
    status = str(forced_status or "").strip().lower()
    if not status:
        session_status = str(getattr(session, "status", "") or "").strip().lower()
        terminal_reason = str(getattr(session, "terminal_reason", "") or "").strip().lower()
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
        "role": str(getattr(session, "role", "") or "").strip(),
        "session_status": str(getattr(session, "status", "") or "").strip(),
        "terminal_reason": str(getattr(session, "terminal_reason", "") or "").strip(),
        "delegation_mode": str(getattr(session, "delegation_mode", "") or "").strip(),
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


def mark_delegated_result_adopted_impl(
    runtime: Any,
    session: Any,
    *,
    now_iso_fn: Callable[[], str],
    sync_delegated_run_record_fn: Callable[..., None],
) -> bool:
    if bool(getattr(session, "adopted", False)):
        return False
    session.adopted = True
    session.adopted_at = now_iso_fn()
    session.updated_at = session.adopted_at
    runtime._record_delegated_checkpoint(
        session,
        kind="result_adopted",
        status="completed",
        summary="delegated result adopted by main thread",
        step_id=str(session.current_step_id or "").strip(),
    )
    sync_delegated_run_record_fn(
        runtime,
        session,
        forced_status="completed",
        forced_summary="delegated session adopted",
    )
    return True


def wait_agent_result_impl(
    runtime: Any,
    agent_id: str,
    *,
    timeout_ms: Any,
    reason: str | None,
    wait_required: Any,
    normalize_wait_agent_metadata_fn: Callable[[dict[str, Any]], dict[str, Any]],
    wait_timeout_seconds_fn: Callable[[Any], float | None],
    promote_terminal_wait_status_fn: Callable[[Any], bool],
    runtime_now_iso_fn: Callable[[], str],
    sync_delegated_run_record_fn: Callable[..., None],
    tool_event_factory: Callable[..., Any],
    command_result_factory: Callable[..., Any],
    generic_tool_call_item_events_fn: Callable[..., Any],
    active_wait_statuses: set[str],
) -> Any:
    session = runtime._delegated_session(agent_id)
    wait_metadata = normalize_wait_agent_metadata_fn(
        {
            "reason": reason,
            "wait_required": wait_required,
        }
    )
    blocking_wait = bool(wait_metadata.get("wait_required", True))
    timeout_seconds = wait_timeout_seconds_fn(timeout_ms)
    wait_started_at = time.monotonic()
    wait_timed_out = False
    wait_decision = "blocking_join" if blocking_wait else "status_snapshot"
    with session.condition:
        if blocking_wait:
            deadline = None if timeout_seconds is None else time.monotonic() + timeout_seconds
            while True:
                terminal_ready = promote_terminal_wait_status_fn(session)
                if terminal_ready:
                    break
                normalized_status = str(getattr(session, "status", "") or "").strip().lower() or "queued"
                if normalized_status not in active_wait_statuses and not bool(getattr(session, "queued_inputs", None)):
                    break
                remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
                if remaining is not None and remaining <= 0:
                    wait_timed_out = True
                    break
                session.condition.wait(timeout=remaining)
        terminal_ready = promote_terminal_wait_status_fn(session)
        if (
            blocking_wait
            and not wait_timed_out
            and terminal_ready
            and runtime._delegated_result_adoptable(session)
            and not bool(getattr(session, "adopted", False))
        ):
            runtime._mark_delegated_result_adopted(session)
        session.last_wait_reason = str(wait_metadata.get("wait_reason") or wait_metadata.get("reason") or "").strip()
        session.last_wait_decision = wait_decision
        session.last_wait_at = runtime_now_iso_fn()
        session.last_wait_blocked_ms = int((time.monotonic() - wait_started_at) * 1000)
        session.last_wait_timed_out = bool(wait_timed_out)
        payload = runtime._delegated_agent_payload(session)
    payload.update(wait_metadata)
    payload["wait_decision"] = wait_decision
    payload["wait_blocked_ms"] = int(session.last_wait_blocked_ms or 0)
    payload["wait_timed_out"] = bool(wait_timed_out)
    sync_delegated_run_record_fn(runtime, session, forced_summary="delegated wait status synced")
    runtime._sync_delegated_background_task(session)
    status = str(payload.get("status") or "").strip() or "queued"
    event_ok = status in {"completed", "closed"} or (not blocking_wait and status != "failed")
    if status in {"completed", "closed"}:
        summary = "wait_agent completed"
    elif status == "failed":
        summary = "wait_agent failed"
    elif blocking_wait:
        summary = "wait_agent timed out" if wait_timed_out else "wait_agent pending"
    else:
        summary = "wait_agent status snapshot"
    event = tool_event_factory(
        name="wait_agent",
        ok=event_ok,
        summary=summary,
        payload=payload,
    )
    return command_result_factory(
        assistant_text=runtime._delegated_agent_summary_text(session),
        tool_events=[event],
        item_events=generic_tool_call_item_events_fn(
            tool_name="wait_agent",
            arguments={
                "target": str(agent_id or "").strip(),
                **({"timeout_ms": int(timeout_ms)} if timeout_ms not in (None, "") else {}),
                **({"reason": str(reason).strip()} if str(reason or "").strip() else {}),
                **(
                    {"wait_required": wait_metadata["wait_required"]}
                    if "wait_required" in wait_metadata
                    else {}
                ),
            },
            ok=bool(event.ok),
            summary=str(event.summary or ""),
            structured_content=dict(event.payload or {}),
        ),
    )


def _selected_wait_result(result: Any, *, ids: list[str], selected_id: str) -> Any:
    if result.tool_events:
        payload = dict(result.tool_events[0].payload or {})
        payload["ids"] = list(ids)
        payload["selected_id"] = selected_id
        result.tool_events[0].payload = payload
    return result


def wait_agents_result_impl(
    runtime: Any,
    agent_ids: list[str],
    *,
    timeout_ms: Any,
    reason: str | None,
    wait_required: Any,
    codex_style: bool,
    wait_agent_result_fn: Callable[..., Any],
    normalized_wait_agent_ids_fn: Callable[[list[str]], list[str]],
    normalize_wait_agent_metadata_fn: Callable[[dict[str, Any]], dict[str, Any]],
    normalized_wait_timeout_ms_fn: Callable[[Any], int],
    wait_timeout_seconds_fn: Callable[[Any], float | None],
    codex_wait_status_snapshot_fn: Callable[[Any, list[str]], tuple[dict[str, Any], list[tuple[str, Any]]]],
    codex_wait_status_wire_fn: Callable[[Any], Any | None],
    codex_wait_result_fn: Callable[..., Any],
    promote_terminal_wait_status_fn: Callable[[Any], bool],
    active_wait_statuses: set[str],
) -> Any:
    normalized_ids = normalized_wait_agent_ids_fn(agent_ids)
    if codex_style:
        normalized_timeout_ms = normalized_wait_timeout_ms_fn(timeout_ms)
        statuses, pending = codex_wait_status_snapshot_fn(runtime, normalized_ids)
        if statuses:
            return codex_wait_result_fn(
                agent_ids=normalized_ids,
                statuses=statuses,
                timed_out=False,
                timeout_ms=normalized_timeout_ms,
            )
        deadline = time.monotonic() + (normalized_timeout_ms / 1000.0)
        while True:
            for agent_id, session in pending:
                with session.condition:
                    promote_terminal_wait_status_fn(session)
                    wire_status = codex_wait_status_wire_fn(session)
                if wire_status is None:
                    continue
                statuses = {agent_id: wire_status}
                for other_id, other_session in pending:
                    if other_id == agent_id:
                        continue
                    with other_session.condition:
                        promote_terminal_wait_status_fn(other_session)
                        other_wire = codex_wait_status_wire_fn(other_session)
                    if other_wire is not None:
                        statuses[other_id] = other_wire
                return codex_wait_result_fn(
                    agent_ids=normalized_ids,
                    statuses=statuses,
                    timed_out=False,
                    timeout_ms=normalized_timeout_ms,
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return codex_wait_result_fn(
                    agent_ids=normalized_ids,
                    statuses={},
                    timed_out=True,
                    timeout_ms=normalized_timeout_ms,
                )
            time.sleep(min(0.05, remaining))
    if len(normalized_ids) == 1:
        return _selected_wait_result(
            wait_agent_result_fn(
                runtime,
                normalized_ids[0],
                timeout_ms=timeout_ms,
                reason=reason,
                wait_required=wait_required,
            ),
            ids=normalized_ids,
            selected_id=normalized_ids[0],
        )

    wait_metadata = normalize_wait_agent_metadata_fn(
        {
            "reason": reason,
            "wait_required": wait_required,
        }
    )
    blocking_wait = bool(wait_metadata.get("wait_required", True))
    timeout_seconds = wait_timeout_seconds_fn(timeout_ms)
    deadline = None if timeout_seconds is None else time.monotonic() + timeout_seconds
    selected_id = normalized_ids[0]
    while True:
        for current_agent_id in normalized_ids:
            session = runtime._delegated_session(current_agent_id)
            with session.condition:
                terminal_ready = promote_terminal_wait_status_fn(session)
                normalized_status = str(getattr(session, "status", "") or "").strip().lower() or "queued"
                has_queued_inputs = bool(getattr(session, "queued_inputs", None))
            if terminal_ready or (not blocking_wait and (normalized_status not in active_wait_statuses or not has_queued_inputs)):
                selected_id = current_agent_id
                break
        else:
            if not blocking_wait:
                break
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            if remaining is not None and remaining <= 0:
                break
            time.sleep(min(0.05, remaining) if remaining is not None else 0.05)
            continue
        break

    effective_timeout_ms = 0 if len(normalized_ids) > 1 else timeout_ms
    return _selected_wait_result(
        wait_agent_result_fn(
            runtime,
            selected_id,
            timeout_ms=effective_timeout_ms,
            reason=reason,
            wait_required=wait_required,
        ),
        ids=normalized_ids,
        selected_id=selected_id,
    )

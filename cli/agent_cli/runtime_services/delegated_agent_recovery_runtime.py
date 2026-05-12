from __future__ import annotations

from typing import Any

from cli.agent_cli.models import CommandExecutionResult, ToolEvent, generic_tool_call_item_events


def normalized_recover_action(action: str | None) -> str:
    normalized = str(action or "").strip().lower().replace("-", "_")
    if normalized in {"", "retry", "retry_failed_step"}:
        return "retry_step"
    if normalized in {"resume", "resume_agent"}:
        return "resume_session"
    if normalized in {"close", "close_agent", "abort", "abort_session"}:
        return "close_session"
    return normalized


def recover_agent_result(
    runtime: Any,
    agent_id: str,
    *,
    action: str | None = None,
    step_id: str | None = None,
    now_iso_fn: Any,
    normalized_recover_action_fn: Any = normalized_recover_action,
    resume_agent_result_fn: Any,
    close_agent_result_fn: Any,
) -> CommandExecutionResult:
    normalized_action = normalized_recover_action_fn(action)
    if normalized_action == "resume_session":
        return resume_agent_result_fn(runtime, agent_id)
    if normalized_action == "close_session":
        return close_agent_result_fn(runtime, agent_id)
    if normalized_action != "retry_step":
        raise ValueError(f"unsupported recovery action: {action}")
    session = runtime._delegated_session(agent_id)
    with session.condition:
        if session.active_input is not None:
            raise RuntimeError(f"delegated agent is still running: {session.agent_id}")
        if session.queued_inputs:
            raise RuntimeError(f"delegated agent already has pending work: {session.agent_id}")
        target_step = runtime._delegated_latest_recoverable_step(
            session,
            step_id=str(step_id or "").strip(),
        )
        if target_step is None:
            raise RuntimeError(f"delegated agent has no recoverable step: {session.agent_id}")
        target_step_id = str(target_step.get("step_id") or "").strip()
        retry_message = str(target_step.get("user_text") or "").strip()
        if not retry_message:
            raise RuntimeError(f"delegated step is not retryable: {target_step_id or session.agent_id}")
        session.closed = False
        session.close_requested = False
        session.cancel_event.clear()
        session.scheduler_reason = ""
        session.resume_source = "recover_agent"
        session.error = ""
        session.adopted = False
        session.adopted_at = ""
        session.terminal_reason = ""
        retry_root_step_id = runtime._delegated_step_retry_root_id(target_step)
        retry_attempt = runtime._next_delegated_retry_attempt(
            session,
            retry_root_step_id=retry_root_step_id,
        )
        retry_step_id = runtime._queue_delegated_step(
            session,
            user_text=retry_message,
            source="retry_step",
            retry_of_step_id=target_step_id,
            retry_root_step_id=retry_root_step_id,
            retry_attempt=retry_attempt,
        )
        session.queued_inputs.append(
            runtime._delegated_queue_item(retry_message, step_id=retry_step_id)
        )
        session.status = "queued"
        runtime._record_delegated_checkpoint(
            session,
            kind="recovery_retry_requested",
            status="queued",
            summary=f"retry requested for {target_step_id} -> {retry_step_id}",
            step_id=retry_step_id,
        )
        runtime._refresh_delegated_current_step_id(session)
        session.updated_at = now_iso_fn()
        session.condition.notify_all()
        payload = runtime._delegated_workflow_payload(session)
    runtime._start_delegated_agent_worker(session)
    runtime._notify_delegated_scheduler()
    runtime._sync_delegated_background_task(session)
    payload["recovery_action"] = "retry_step"
    payload["recovered_step_id"] = str(target_step_id or "")
    payload["retry_step_id"] = str(retry_step_id or "")
    event = ToolEvent(
        name="recover_agent",
        ok=True,
        summary="recover_agent accepted",
        payload=payload,
    )
    return CommandExecutionResult(
        assistant_text=f"queued recovery retry for delegated agent {session.agent_id}",
        tool_events=[event],
        item_events=generic_tool_call_item_events(
            tool_name="recover_agent",
            arguments={
                "target": str(agent_id or "").strip(),
                "action": "retry_step",
                **({"step_id": str(step_id).strip()} if str(step_id or "").strip() else {}),
            },
            ok=True,
            summary=str(event.summary or ""),
            structured_content=dict(event.payload or {}),
        ),
    )

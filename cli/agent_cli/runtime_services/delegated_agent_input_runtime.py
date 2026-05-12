from __future__ import annotations

from typing import Any, Dict

from cli.agent_cli.models import CommandExecutionResult, ToolEvent, generic_tool_call_item_events
from cli.agent_cli.runtime_services import delegated_agent_session_payload_runtime


def enqueue_delegated_input(
    runtime: Any,
    session: Any,
    *,
    message_text: str,
    interrupt: bool,
    input_items: list[dict[str, Any]] | None,
    now_iso_fn: Any,
) -> Dict[str, Any]:
    step_id = runtime._queue_delegated_step(
        session,
        user_text=message_text,
        source="interrupt_input" if interrupt else "followup_input",
    )
    queue_item = runtime._delegated_queue_item(
        message_text,
        interrupt=interrupt,
        step_id=step_id,
        input_items=input_items,
    )
    if interrupt:
        session.queued_inputs.insert(0, queue_item)
        if session.status == "running" and session.active_input is not None:
            session.cancel_event.set()
    else:
        session.queued_inputs.append(queue_item)
    if session.status not in {"running", "starting"}:
        session.status = "queued"
    session.scheduler_reason = ""
    session.resume_source = "send_input"
    session.adopted = False
    session.adopted_at = ""
    session.terminal_reason = ""
    runtime._refresh_delegated_current_step_id(session)
    session.updated_at = now_iso_fn()
    pending_count = len(list(session.queued_inputs or [])) + (1 if session.active_input else 0)
    return {
        "step_id": step_id,
        "pending_count": pending_count,
    }


def send_input_result(
    runtime: Any,
    agent_id: str,
    *,
    message: str,
    interrupt: bool = False,
    input_items: list[dict[str, Any]] | None = None,
    codex_style: bool = False,
    now_iso_fn: Any,
) -> CommandExecutionResult:
    session = runtime._delegated_session(agent_id)
    message_text = str(message or "").strip()
    if not message_text:
        raise ValueError("send_input requires a non-empty message")
    with session.condition:
        if session.closed:
            raise RuntimeError(f"delegated agent is closed: {session.agent_id}")
        if session.close_requested:
            raise RuntimeError(f"delegated agent is closing: {session.agent_id}")
        queued = enqueue_delegated_input(
            runtime,
            session,
            message_text=message_text,
            interrupt=bool(interrupt),
            input_items=input_items,
            now_iso_fn=now_iso_fn,
        )
        pending_count = int(queued.get("pending_count") or 0)
        session.condition.notify_all()
    runtime._start_delegated_agent_worker(session)
    runtime._notify_delegated_scheduler()
    runtime._sync_delegated_background_task(session)
    payload = runtime._delegated_agent_payload(session)
    payload["accepted_message"] = message_text
    payload["interrupt_requested"] = bool(interrupt)
    payload["pending_input_count"] = pending_count
    if input_items is not None:
        payload["accepted_items"] = [dict(item) for item in list(input_items or []) if isinstance(item, dict)]
    if codex_style:
        return delegated_agent_session_payload_runtime.codex_collab_tool_result(
            tool_name="send_input",
            payload=payload,
            function_output={"submission_id": str(queued.get("step_id") or "").strip()},
            assistant_text=f"queued input for delegated agent {session.agent_id}",
            summary="send_input accepted",
            tool_event_factory=ToolEvent,
            command_result_factory=CommandExecutionResult,
        )
    event = ToolEvent(
        name="send_input",
        ok=True,
        summary="send_input accepted",
        payload=payload,
    )
    return CommandExecutionResult(
        assistant_text=f"queued input for delegated agent {session.agent_id}",
        tool_events=[event],
        item_events=generic_tool_call_item_events(
            tool_name="send_input",
            arguments={
                **({"id": str(agent_id or "").strip()} if input_items is not None else {"target": str(agent_id or "").strip()}),
                **({"message": message_text} if input_items is None else {}),
                **(
                    {"items": [dict(item) for item in list(input_items or []) if isinstance(item, dict)]}
                    if input_items is not None
                    else {}
                ),
                **({"interrupt": True} if interrupt else {}),
            },
            ok=True,
            summary="send_input accepted",
            structured_content=dict(event.payload or {}),
        ),
    )

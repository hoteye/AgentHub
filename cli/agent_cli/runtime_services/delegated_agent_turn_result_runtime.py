from __future__ import annotations

from typing import Any

from cli.agent_cli.models import CommandExecutionResult, replay_input_items_from_turn_events
from cli.agent_cli.runtime_services import delegated_agent_turn_helpers_runtime as delegated_agent_turn_helpers_runtime_service


def populate_session_from_result(
    runtime: Any,
    session: Any,
    result: CommandExecutionResult,
    user_text: str,
    *,
    include_assistant_history: bool = True,
    include_turn_history: bool = True,
) -> str:
    assistant_text = str(result.assistant_text or "").strip()
    if not assistant_text and result.turn_events:
        assistant_text = runtime._assistant_text_from_turn_events(result.turn_events)
    session.active_input = None
    session.scheduler_reason = ""
    session.last_input_text = str(user_text or "").strip()
    session.assistant_text = assistant_text
    session.error = ""
    session.last_tool_events = list(result.tool_events or [])
    session.last_item_events = [
        dict(item) for item in list(result.item_events or []) if isinstance(item, dict)
    ]
    session.last_turn_events = [
        dict(item) for item in list(result.turn_events or []) if isinstance(item, dict)
    ]
    replay_items = replay_input_items_from_turn_events(session.last_turn_events)
    if replay_items:
        session.replay_input_items.extend(
            dict(item) for item in replay_items if isinstance(item, dict)
        )
    if include_turn_history:
        session.replay_history.append({"role": "user", "content": str(user_text or "").strip()})
        if include_assistant_history and assistant_text:
            session.replay_history.append({"role": "assistant", "content": assistant_text})
        session.turn_count += 1
    session.adopted = False
    session.adopted_at = ""
    session.terminal_reason = ""
    session.updated_at = delegated_agent_turn_helpers_runtime_service.runtime_now_iso()
    return assistant_text


def record_delegated_step(
    runtime: Any,
    session: Any,
    *,
    step_id: str,
    status: str,
    summary: str,
    assistant_text: str | None = None,
    finished: bool = False,
    error: str | None = None,
) -> None:
    if not step_id:
        return
    runtime._update_delegated_step(
        session,
        step_id=step_id,
        status=status,
        summary=summary,
        assistant_text=assistant_text or "",
        error=error,
        finished=finished,
    )
    runtime._record_delegated_checkpoint(
        session,
        kind=f"step_{status}",
        status=status,
        summary=f"{status} {step_id}",
        step_id=step_id,
    )

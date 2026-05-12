from __future__ import annotations

from typing import Any, Callable, Dict, List, Tuple

from cli.agent_cli.debug_timeline import log_timeline, timeline_debug_enabled
from cli.agent_cli.models import AgentIntent, REFERENCE_CONVERSATION_INTERRUPTED_TEXT, CommandExecutionResult, ToolEvent


def interrupt_tuple(tool_executor: Any) -> Tuple[str, List[ToolEvent]]:
    builder = getattr(tool_executor, "interrupt_result", None)
    if callable(builder):
        try:
            result = builder()
        except Exception:
            result = None
        if isinstance(result, CommandExecutionResult):
            return (
                str(result.assistant_text or "").strip() or REFERENCE_CONVERSATION_INTERRUPTED_TEXT,
                list(result.tool_events or []),
            )
        if isinstance(result, tuple) and len(result) == 2:
            assistant_text, events = result
            return (
                str(assistant_text or "").strip() or REFERENCE_CONVERSATION_INTERRUPTED_TEXT,
                list(events or []),
            )
    return (
        REFERENCE_CONVERSATION_INTERRUPTED_TEXT,
        [
            ToolEvent(
                name="interrupted",
                ok=False,
                summary="execution interrupted",
                payload={
                    "ok": False,
                    "interrupted": True,
                    "reason": "user_interrupt",
                },
            )
        ],
    )


def interrupted_intent(
    *,
    tool_executor: Any,
    executed_events: List[ToolEvent],
    executed_item_events: List[Dict[str, Any]],
    model_ms: int,
    tool_execution_ms: int,
    planning_rounds: int,
    planning_trace: List[Dict[str, Any]],
    total_ms: int,
    final_intent_builder: Callable[..., AgentIntent],
    tool_event_is_interrupt_fn: Callable[[ToolEvent], bool],
) -> AgentIntent:
    interrupt_text, interrupt_events = interrupt_tuple(tool_executor)
    combined_events = list(executed_events or [])
    if interrupt_events:
        should_append_interrupt = True
        if combined_events and all(tool_event_is_interrupt_fn(event) for event in interrupt_events):
            last_event = combined_events[-1]
            if tool_event_is_interrupt_fn(last_event) and str(last_event.name or "").strip() == "interrupted":
                should_append_interrupt = False
        if should_append_interrupt:
            combined_events.extend(list(interrupt_events or []))
    return final_intent_builder(
        assistant_text=interrupt_text or REFERENCE_CONVERSATION_INTERRUPTED_TEXT,
        response_items=None,
        executed_events=combined_events,
        executed_item_events=executed_item_events,
        model_ms=model_ms,
        tool_execution_ms=tool_execution_ms,
        planning_rounds=planning_rounds,
        planning_trace=planning_trace,
        synthesis_model_ms=0,
        synthesis_rounds=0,
        total_ms=total_ms,
    )


def emit_turn_event(
    event: Dict[str, Any],
    *,
    callback: Callable[[Dict[str, Any]], None] | None,
) -> None:
    item = event.get("item")
    if timeline_debug_enabled() and isinstance(item, dict):
        item_type = str(item.get("type") or "").strip()
        item_id = str(item.get("id") or "").strip()
        event_type = str(event.get("type") or "").strip()
        log_timeline(
            "turn_engine.turn_event.emit",
            event_type=event_type,
            item_type=item_type,
            item_id=item_id or None,
        )
    if callback is not None:
        callback(dict(event))


def emit_turn_events(
    events: List[Dict[str, Any]],
    *,
    emit_turn_event_fn: Callable[[Dict[str, Any]], None],
) -> None:
    for event in list(events or []):
        if isinstance(event, dict):
            emit_turn_event_fn(event)

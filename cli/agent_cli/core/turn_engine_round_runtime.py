from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from cli.agent_cli.models import AgentIntent, ToolEvent, response_items_to_text
from cli.agent_cli.core.turn_engine_item_events import _next_item_index, _response_item_events


TraceSummaryBuilder = Callable[[List[Any]], Dict[str, Any]]
EventEmitter = Callable[[Dict[str, Any]], None]
PreambleTextBuilder = Callable[[str, Dict[str, Any]], str]
SyntheticEventBuilder = Callable[..., Dict[str, Any]]
FallbackTextBuilder = Callable[[List[ToolEvent]], str]
InterruptIntentBuilder = Callable[[], AgentIntent]
FinalIntentBuilder = Callable[..., AgentIntent]
FallbackIntentBuilder = Callable[[AgentIntent], AgentIntent]
HandlerInvoker = Callable[..., AgentIntent]
TotalMsBuilder = Callable[[], int]


@dataclass
class TerminalRoundResolution:
    intent: AgentIntent


def build_trace_entry(
    *,
    planning_round: int,
    request_elapsed_ms: int,
    step: Any,
    summary_builder: TraceSummaryBuilder,
) -> Dict[str, Any]:
    trace_entry = {
        "round": planning_round,
        "model_ms": request_elapsed_ms,
        "tool_calls": list(step.trace.get("tool_calls") or [call.name for call in step.tool_calls]),
        "tool_call_count": int(step.trace.get("tool_call_count") or len(step.tool_calls)),
        "answered": bool(
            step.trace.get("answered")
            or (not step.tool_calls and bool(step.output_text or step.response_items))
        ),
        "answer_preview": str(
            step.trace.get("answer_preview") or (step.output_text[:120] if not step.tool_calls else "")
        ),
    }
    usage = step.trace.get("usage")
    if isinstance(usage, dict):
        trace_entry["usage"] = dict(usage)
    trace_entry.update(summary_builder(step.tool_calls))
    return trace_entry


def record_tool_call_round_items(
    *,
    step: Any,
    executed_item_events: List[Dict[str, Any]],
    emit_turn_event: EventEmitter,
    preamble_text_builder: PreambleTextBuilder,
    synthetic_event_builder: SyntheticEventBuilder,
) -> None:
    if not step.tool_calls:
        return
    if step.response_items:
        executed_item_events.extend(_response_item_events(list(step.response_items or [])))
    streamed_message_count = int(step.trace.get("streamed_message_count") or 0)
    if streamed_message_count > 0:
        return
    preamble_text = preamble_text_builder(step.tool_calls[0].name, step.tool_calls[0].arguments)
    if _latest_completed_agent_message_text(executed_item_events) == preamble_text:
        return
    synthetic_item_id = f"item_{_next_item_index(executed_item_events)}"
    synthetic_event = synthetic_event_builder(
        item_id=synthetic_item_id,
        text=preamble_text,
    )
    executed_item_events.append(dict(synthetic_event))
    emit_turn_event(synthetic_event)


def _latest_completed_agent_message_text(executed_item_events: List[Dict[str, Any]]) -> str:
    for event in reversed(executed_item_events):
        if not isinstance(event, dict):
            continue
        if str(event.get("type") or "").strip() != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() != "agent_message":
            continue
        return str(item.get("text") or "")
    return ""


def resolve_terminal_round(
    *,
    step: Any,
    interrupt_requested: bool,
    fallback_on_empty_output: bool,
    executed_events: List[ToolEvent],
    executed_item_events: List[Dict[str, Any]],
    terminal_handler: Optional[Callable[..., AgentIntent]],
    user_text: str,
    previous_response_id: Optional[str],
    continuation_input_items: List[Dict[str, Any]],
    model_ms: int,
    tool_execution_ms: int,
    planning_rounds: int,
    planning_trace: List[Dict[str, Any]],
    total_ms_builder: TotalMsBuilder,
    interrupted_intent_builder: InterruptIntentBuilder,
    final_intent_builder: FinalIntentBuilder,
    handler_invoker: HandlerInvoker,
    fallback_intent_builder: FallbackIntentBuilder,
    fallback_text_builder: FallbackTextBuilder,
) -> Optional[TerminalRoundResolution]:
    if step.tool_calls:
        return None
    if bool(step.trace.get("provider_native_continuation_pending")):
        return None
    if interrupt_requested:
        return TerminalRoundResolution(intent=interrupted_intent_builder())

    has_displayable_output = bool(str(step.output_text or "").strip())
    if not has_displayable_output and step.response_items:
        has_displayable_output = bool(response_items_to_text(list(step.response_items or [])).strip())
    if has_displayable_output or not fallback_on_empty_output:
        return TerminalRoundResolution(
            intent=final_intent_builder(
                assistant_text=step.output_text,
                response_items=step.response_items,
                executed_events=executed_events,
                executed_item_events=executed_item_events,
                model_ms=model_ms,
                tool_execution_ms=tool_execution_ms,
                planning_rounds=planning_rounds,
                planning_trace=planning_trace,
                synthesis_model_ms=0,
                synthesis_rounds=0,
                total_ms=total_ms_builder(),
            )
        )

    if executed_events and terminal_handler is not None:
        fallback = handler_invoker(
            terminal_handler,
            user_text=user_text,
            executed_events=executed_events,
            executed_item_events=executed_item_events,
            previous_response_id=previous_response_id,
            continuation_input_items=continuation_input_items,
        )
        return TerminalRoundResolution(
            intent=fallback_intent_builder(
                fallback,
                executed_events=executed_events,
                executed_item_events=executed_item_events,
                model_ms=model_ms,
                tool_execution_ms=tool_execution_ms,
                planning_rounds=planning_rounds,
                total_ms=total_ms_builder(),
            )
        )

    return TerminalRoundResolution(
        intent=final_intent_builder(
            assistant_text=fallback_text_builder(executed_events),
            response_items=None,
            executed_events=executed_events,
            executed_item_events=executed_item_events,
            model_ms=model_ms,
            tool_execution_ms=tool_execution_ms,
            planning_rounds=planning_rounds,
            planning_trace=planning_trace,
            synthesis_model_ms=0,
            synthesis_rounds=0,
            total_ms=total_ms_builder(),
        )
    )


def next_round_input_items(
    *,
    continuation_input_items: List[Dict[str, Any]],
    tool_outputs: List[Dict[str, Any]],
    pending_input_items: Optional[List[Dict[str, Any]]] = None,
    incremental_continuation: bool = False,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    if continuation_input_items and not incremental_continuation:
        items.extend(list(continuation_input_items))
    items.extend(list(tool_outputs))
    if pending_input_items:
        items.extend(
            dict(item)
            for item in list(pending_input_items)
            if isinstance(item, dict)
        )
    return items

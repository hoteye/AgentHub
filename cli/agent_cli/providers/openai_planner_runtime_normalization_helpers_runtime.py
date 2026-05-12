from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from cli.agent_cli.models import AgentIntent, response_items_to_text
from cli.agent_cli.providers.planner_postprocessing import sanitize_final_answer_text


@dataclass
class NormalizedAssistantPayload:
    assistant_text: str
    response_items: List[Any]
    response_items_text: str


@dataclass
class NormalizedNativeToolLoopIntent:
    assistant_text: str
    response_items: List[Any]
    response_items_text: str
    raw_timings: Dict[str, Any]
    turn_events: List[Dict[str, Any]]
    tool_item_events: List[Dict[str, Any]]
    response_has_text: bool


def normalized_turn_event_dicts(events: List[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
    return [dict(item) for item in list(events or []) if isinstance(item, dict)]


def normalized_response_payload(
    *,
    assistant_text: Any,
    response_items: List[Any] | None,
) -> NormalizedAssistantPayload:
    normalized_response_items = list(response_items or [])
    response_items_text = response_items_to_text(normalized_response_items)
    normalized_assistant_text = sanitize_final_answer_text(str(assistant_text or "").strip())
    if not normalized_assistant_text and normalized_response_items:
        normalized_assistant_text = sanitize_final_answer_text(response_items_text)
    return NormalizedAssistantPayload(
        assistant_text=normalized_assistant_text,
        response_items=normalized_response_items,
        response_items_text=response_items_text,
    )


def normalized_native_tool_loop_intent(
    raw_intent: AgentIntent,
    *,
    tool_item_events_from_turn_events_fn: Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]],
) -> NormalizedNativeToolLoopIntent:
    normalized_response = normalized_response_payload(
        assistant_text=raw_intent.assistant_text,
        response_items=list(raw_intent.response_items or []),
    )
    turn_events = normalized_turn_event_dicts(list(raw_intent.turn_events or []))
    tool_item_events = tool_item_events_from_turn_events_fn(turn_events)
    return NormalizedNativeToolLoopIntent(
        assistant_text=normalized_response.assistant_text,
        response_items=normalized_response.response_items,
        response_items_text=normalized_response.response_items_text,
        raw_timings=dict(raw_intent.timings or {}),
        turn_events=turn_events,
        tool_item_events=tool_item_events,
        response_has_text=bool(normalized_response.response_items_text.strip()),
    )


__all__ = [
    "NormalizedAssistantPayload",
    "NormalizedNativeToolLoopIntent",
    "normalized_native_tool_loop_intent",
    "normalized_response_payload",
    "normalized_turn_event_dicts",
]

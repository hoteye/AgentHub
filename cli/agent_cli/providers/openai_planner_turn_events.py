from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from cli.agent_cli.models import ToolEvent, compose_turn_events_from_response_items
from cli.agent_cli.providers import openai_planner_turn_events_runtime as turn_events_runtime
from cli.agent_cli.providers.tool_calls import tool_result_payload as _tool_result_payload_impl


def _tool_output_item(call_id: str, command_text: Optional[str], assistant_text: str, events: List[ToolEvent]) -> Dict[str, Any]:
    return {
        "type": "function_call_output",
        "call_id": call_id,
        "output": json.dumps(
            _tool_result_payload_impl(command_text, assistant_text, events),
            ensure_ascii=False,
        ),
    }


def _next_item_index(events: List[Dict[str, Any]]) -> int:
    return turn_events_runtime.next_item_index(events)


def _rebase_item_events(events: List[Dict[str, Any]], *, start_index: int) -> List[Dict[str, Any]]:
    return turn_events_runtime.rebase_item_events(events, start_index=start_index)


def _compose_turn_events(
    *,
    assistant_text: str,
    response_items: List[Any],
    executed_item_events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    return compose_turn_events_from_response_items(
        assistant_text=assistant_text,
        response_items=list(response_items or []),
        executed_item_events=[
            dict(item)
            for item in list(executed_item_events or [])
            if isinstance(item, dict)
        ],
    )


def _rewrite_existing_turn_events(
    existing_turn_events: List[Dict[str, Any]],
    *,
    final_text: str,
) -> List[Dict[str, Any]]:
    return turn_events_runtime.rewrite_existing_turn_events(existing_turn_events, final_text=final_text)


def _canonical_turn_events(
    *,
    assistant_text: str,
    response_items: List[Any],
    executed_item_events: List[Dict[str, Any]],
    existing_turn_events: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    normalized_existing = turn_events_runtime.normalized_turn_event_dicts(existing_turn_events)
    if normalized_existing:
        final_text = turn_events_runtime.final_text_for_turn_events(
            assistant_text=assistant_text,
            response_items=response_items,
        )
        return _rewrite_existing_turn_events(normalized_existing, final_text=final_text)
    return _compose_turn_events(
        assistant_text=assistant_text,
        response_items=response_items,
        executed_item_events=list(executed_item_events or []),
    )


def _tool_item_events_from_turn_events(turn_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return turn_events_runtime.tool_item_events_from_turn_events(turn_events)

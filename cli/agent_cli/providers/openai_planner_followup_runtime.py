from __future__ import annotations

import json
import time
from typing import Any, Callable, Dict, List, Optional

from cli.agent_cli.models import (
    AgentIntent,
    ToolEvent,
    default_response_items,
)


def normalized_item_event_dicts(events: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    return [dict(item) for item in list(events or []) if isinstance(item, dict)]


def function_output_item_event_dicts(events: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for raw_event in normalized_item_event_dicts(events):
        item = raw_event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() not in {"function_call_output", "custom_tool_call_output"}:
            continue
        results.append(dict(raw_event))
    return results


def build_tool_followup_messages(
    *,
    user_text: str,
    executed_events: List[ToolEvent],
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    attachment_payloads: Optional[List[Dict[str, Any]]] = None,
    generic_tool_event_summary_lines_fn: Callable[[List[ToolEvent]], List[str]],
    generic_tool_event_context_blocks_fn: Callable[[List[ToolEvent]], List[Dict[str, Any]]],
    executed_item_event_context_blocks_fn: Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    parts = [
        "ORIGINAL_USER_REQUEST:",
        user_text,
        "",
        "VERIFIED_TOOL_RESULT_SUMMARY:",
        "\n".join(generic_tool_event_summary_lines_fn(executed_events)) or "- no tool events",
        "",
        "VERIFIED_TOOL_RESULT_CONTEXT_JSON:",
        json.dumps(generic_tool_event_context_blocks_fn(executed_events), ensure_ascii=False, indent=2),
    ]
    item_blocks = executed_item_event_context_blocks_fn(executed_item_events or [])
    if item_blocks:
        parts.extend(
            [
                "",
                "EXECUTED_ITEM_EVENTS_JSON:",
                json.dumps(item_blocks, ensure_ascii=False, indent=2),
            ]
        )
    parts.extend(
        [
            "",
            "Continue solving the original request from these verified tool results and executed item events.",
            "If the current evidence is insufficient, call more tools. If it is sufficient, answer directly.",
        ]
    )
    if attachment_payloads:
        parts.extend(
            [
                "",
                "ATTACHMENTS_JSON:",
                json.dumps(list(attachment_payloads), ensure_ascii=False, indent=2),
            ]
        )
    return [{"role": "user", "content": "\n".join(parts)}]


def build_followup_direct_answer_intent(
    *,
    assistant_text: str,
    response_items: Optional[List[Any]],
    executed_events: List[ToolEvent],
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    compose_turn_events_fn: Callable[..., List[Dict[str, Any]]],
    started_at: float,
    model_ms: int,
    tool_execution_ms: int,
    rounds: int,
) -> AgentIntent:
    final_response_items = list(response_items or default_response_items(assistant_text=assistant_text))
    normalized_item_events = normalized_item_event_dicts(executed_item_events)
    return AgentIntent(
        assistant_text=assistant_text,
        response_items=final_response_items,
        command_text=None,
        status_hint="tool",
        tool_events=executed_events,
        turn_events=compose_turn_events_fn(
            assistant_text=assistant_text,
            response_items=final_response_items,
            executed_item_events=normalized_item_events,
        ),
        timings={
            "synthesis_model_ms": model_ms,
            "synthesis_rounds": rounds,
            "tool_execution_ms": tool_execution_ms,
            "total_ms": int((time.perf_counter() - started_at) * 1000),
        },
    )


def merge_followup_synthesis_intent(
    *,
    synthesized: AgentIntent,
    executed_events: List[ToolEvent],
    started_at: float,
    model_ms: int,
    tool_execution_ms: int,
    rounds: int,
    executed_item_events: Optional[List[Dict[str, Any]]] = None,
    canonical_turn_events_fn: Callable[..., List[Dict[str, Any]]],
) -> AgentIntent:
    synthesized_timings = dict(synthesized.timings or {})
    response_items = list(
        synthesized.response_items
        or default_response_items(assistant_text=synthesized.assistant_text)
    )
    normalized_item_events = normalized_item_event_dicts(executed_item_events)
    return AgentIntent(
        assistant_text=synthesized.assistant_text,
        response_items=response_items,
        command_text=None,
        status_hint="tool",
        tool_events=list(executed_events),
        turn_events=canonical_turn_events_fn(
            assistant_text=synthesized.assistant_text,
            response_items=response_items,
            executed_item_events=normalized_item_events,
            existing_turn_events=list(synthesized.turn_events or []),
        ),
        timings={
            "synthesis_model_ms": model_ms + int(synthesized_timings.get("synthesis_model_ms") or 0),
            "synthesis_rounds": rounds + int(synthesized_timings.get("synthesis_rounds") or 0),
            "tool_execution_ms": tool_execution_ms + int(synthesized_timings.get("tool_execution_ms") or 0),
            "total_ms": int((time.perf_counter() - started_at) * 1000),
        },
    )


def rebase_followup_result_item_events(
    *,
    call: Dict[str, Any],
    result: Any,
    aggregated_item_events: List[Dict[str, Any]],
    next_item_index: int,
    latest_open_todo_list_item_fn: Callable[[List[Dict[str, Any]]], Any],
    todo_list_turn_event_from_plan_payload_fn: Callable[..., Dict[str, Any]],
    rebase_item_events_fn: Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    if str(call.get("name") or "").strip() == "update_plan":
        active_todo_list = latest_open_todo_list_item_fn(aggregated_item_events)
        active_todo_list_id = (
            str(active_todo_list.get("id") or "").strip()
            if isinstance(active_todo_list, dict)
            else ""
        )
        todo_payload = dict(call.get("arguments") or {})
        last_tool_event = result.tool_events[-1] if result.tool_events else None
        if isinstance(last_tool_event, ToolEvent) and isinstance((last_tool_event.payload or {}).get("plan"), list):
            todo_payload = dict(last_tool_event.payload or {})
        todo_event = todo_list_turn_event_from_plan_payload_fn(
            todo_payload,
            item_id=active_todo_list_id or f"item_{next_item_index}",
            event_type="item.updated" if active_todo_list_id else "item.started",
        )
        explicit_output_events = function_output_item_event_dicts(getattr(result, "item_events", None))
        if not explicit_output_events:
            return [todo_event]
        output_start_index = int(next_item_index) if active_todo_list_id else int(next_item_index) + 1
        return [
            todo_event,
            *rebase_item_events_fn(explicit_output_events, start_index=output_start_index),
        ]
    return rebase_item_events_fn(normalized_item_event_dicts(result.item_events), start_index=next_item_index)

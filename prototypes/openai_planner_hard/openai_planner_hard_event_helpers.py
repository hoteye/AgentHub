from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.models import (
    CommandExecutionResult,
    ToolEvent,
    compose_turn_events_from_response_items,
    response_items_to_text,
    tool_events_to_turn_events,
)

PlannerToolExecutor = Callable[[str], tuple[str, list[ToolEvent]]]


def next_item_index(events: list[dict[str, Any]]) -> int:
    highest = -1
    for event in list(events or []):
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "").strip()
        if not item_id.startswith("item_"):
            continue
        try:
            highest = max(highest, int(item_id.split("_", 1)[1]))
        except (TypeError, ValueError):
            continue
    return highest + 1


def rebase_item_events(events: list[dict[str, Any]], *, start_index: int) -> list[dict[str, Any]]:
    mapping: dict[str, str] = {}
    next_index = int(start_index)
    rebased: list[dict[str, Any]] = []
    for event in list(events or []):
        if not isinstance(event, dict):
            continue
        copied = dict(event)
        item = copied.get("item")
        if not isinstance(item, dict):
            rebased.append(copied)
            continue
        item_copy = dict(item)
        original_id = str(item_copy.get("id") or "").strip()
        if original_id:
            replacement = mapping.get(original_id)
            if replacement is None:
                replacement = f"item_{next_index}"
                mapping[original_id] = replacement
                next_index += 1
            item_copy["id"] = replacement
        copied["item"] = item_copy
        rebased.append(copied)
    return rebased


def compose_turn_events(
    *,
    assistant_text: str,
    response_items: list[Any],
    executed_item_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return compose_turn_events_from_response_items(
        assistant_text=assistant_text,
        response_items=list(response_items or []),
        executed_item_events=[
            dict(item) for item in list(executed_item_events or []) if isinstance(item, dict)
        ],
    )


def rewrite_existing_turn_events(
    existing_turn_events: list[dict[str, Any]],
    *,
    final_text: str,
) -> list[dict[str, Any]]:
    normalized = [dict(item) for item in list(existing_turn_events or []) if isinstance(item, dict)]
    if not normalized:
        return []
    final_text = str(final_text or "").strip()
    if not final_text:
        return normalized
    updated = [dict(item) for item in normalized]
    replaced = False
    for idx in range(len(updated) - 1, -1, -1):
        event = dict(updated[idx])
        if str(event.get("type") or "").strip() != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() != "agent_message":
            continue
        item_copy = dict(item)
        item_copy["text"] = final_text
        event["item"] = item_copy
        updated[idx] = event
        replaced = True
        break
    if replaced:
        return updated
    inserted = {
        "type": "item.completed",
        "item": {
            "id": "item_0",
            "type": "agent_message",
            "text": final_text,
        },
    }
    turn_completed_idx = None
    for idx, event in enumerate(updated):
        if str((event or {}).get("type") or "").strip() == "turn.completed":
            turn_completed_idx = idx
            break
    if turn_completed_idx is None:
        if not updated or str(updated[0].get("type") or "").strip() != "turn.started":
            updated.insert(0, {"type": "turn.started"})
        updated.append(inserted)
        updated.append(
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0},
            }
        )
        return updated
    updated.insert(turn_completed_idx, inserted)
    return updated


def canonical_turn_events(
    *,
    assistant_text: str,
    response_items: list[Any],
    executed_item_events: list[dict[str, Any]],
    existing_turn_events: list[dict[str, Any]] | None = None,
    rewrite_existing_turn_events_fn: Callable[..., list[dict[str, Any]]],
    compose_turn_events_fn: Callable[..., list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    normalized_existing = [
        dict(item) for item in list(existing_turn_events or []) if isinstance(item, dict)
    ]
    if normalized_existing:
        final_text = (
            response_items_to_text(list(response_items or [])).strip()
            or str(assistant_text or "").strip()
        )
        return rewrite_existing_turn_events_fn(normalized_existing, final_text=final_text)
    return compose_turn_events_fn(
        assistant_text=assistant_text,
        response_items=response_items,
        executed_item_events=list(executed_item_events or []),
    )


def tool_item_events_from_turn_events(turn_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tool_item_types = {"command_execution", "mcp_tool_call", "function_call_output"}
    item_events: list[dict[str, Any]] = []
    for raw_event in list(turn_events or []):
        if not isinstance(raw_event, dict):
            continue
        item = raw_event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() not in tool_item_types:
            continue
        item_events.append(dict(raw_event))
    return item_events


def execute_tool_result(
    tool_executor: PlannerToolExecutor, command_text: str
) -> CommandExecutionResult:
    structured_runner = getattr(tool_executor, "run_structured", None)
    if callable(structured_runner):
        structured_result = structured_runner(command_text)
    else:
        structured_result = tool_executor(command_text)

    if isinstance(structured_result, CommandExecutionResult):
        return CommandExecutionResult(
            assistant_text=str(structured_result.assistant_text or ""),
            tool_events=list(structured_result.tool_events or []),
            item_events=[
                dict(item)
                for item in list(structured_result.item_events or [])
                if isinstance(item, dict)
            ],
            turn_events=[
                dict(item)
                for item in list(structured_result.turn_events or [])
                if isinstance(item, dict)
            ],
        )

    assistant_text, events = structured_result
    item_events, _ = tool_events_to_turn_events(list(events or []), start_index=0)
    return CommandExecutionResult(
        assistant_text=str(assistant_text or ""),
        tool_events=list(events or []),
        item_events=item_events,
    )


def history_for_conversation(
    history: list[dict[str, str]],
    *,
    input_items: list[dict[str, Any]] | None = None,
    input_items_have_assistant_turn_fn: Callable[[list[dict[str, Any]] | None], bool],
) -> list[dict[str, str]]:
    # Structured turn-item path should be the canonical conversation carrier.
    # If input_items already include assistant turns, avoid re-appending legacy history.
    if input_items_have_assistant_turn_fn(input_items):
        return []
    return list(history or [])

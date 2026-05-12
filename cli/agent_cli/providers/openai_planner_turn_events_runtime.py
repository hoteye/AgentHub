from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli.models import response_items_phase_text, response_items_to_text

_TOOL_ITEM_TYPES = {
    "command_execution",
    "mcp_tool_call",
    "todo_list",
    "function_call_output",
    "custom_tool_call_output",
}


def normalized_turn_event_dicts(events: List[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
    return [dict(item) for item in list(events or []) if isinstance(item, dict)]


def final_text_for_turn_events(*, assistant_text: str, response_items: List[Any]) -> str:
    final_phase_text = response_items_phase_text(list(response_items or []), phase="final_answer").strip()
    if final_phase_text:
        return final_phase_text
    return response_items_to_text(list(response_items or [])).strip() or str(assistant_text or "").strip()


def next_item_index(events: List[Dict[str, Any]]) -> int:
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


def rebase_item_events(events: List[Dict[str, Any]], *, start_index: int) -> List[Dict[str, Any]]:
    mapping: Dict[str, str] = {}
    next_index = int(start_index)
    rebased: List[Dict[str, Any]] = []
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


def rewrite_existing_turn_events(
    existing_turn_events: List[Dict[str, Any]],
    *,
    final_text: str,
) -> List[Dict[str, Any]]:
    normalized = normalized_turn_event_dicts(existing_turn_events)
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


def tool_item_events_from_turn_events(turn_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    item_events: List[Dict[str, Any]] = []
    for raw_event in list(turn_events or []):
        if not isinstance(raw_event, dict):
            continue
        item = raw_event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() not in _TOOL_ITEM_TYPES:
            continue
        item_events.append(dict(raw_event))
    return item_events

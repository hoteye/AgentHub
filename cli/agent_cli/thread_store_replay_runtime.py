from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli.models import ResponseInputItem, ThreadHistoryTurn


def tool_item_events_from_turn_events(turn_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tool_item_types = {
        "command_execution",
        "mcp_tool_call",
        "function_call",
        "function_call_output",
        "custom_tool_call",
        "custom_tool_call_output",
        "shell_call",
        "shell_call_output",
        "local_shell_call",
        "local_shell_call_output",
    }
    events: List[Dict[str, Any]] = []
    for raw_event in list(turn_events or []):
        if not isinstance(raw_event, dict):
            continue
        item = raw_event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() not in tool_item_types:
            continue
        events.append(dict(raw_event))
    return events


def turn_has_structured_tool_items(turn: ThreadHistoryTurn) -> bool:
    return bool(
        tool_item_events_from_turn_events(
            [dict(item) for item in list(turn.turn_events or []) if isinstance(item, dict)]
        )
    )


def turn_has_tool_history(turn: ThreadHistoryTurn) -> bool:
    return bool(list(turn.tool_events or [])) or turn_has_structured_tool_items(turn)


def assistant_text_from_turn_events(turn_events: List[Dict[str, Any]]) -> str:
    for raw_event in reversed(list(turn_events or [])):
        if not isinstance(raw_event, dict):
            continue
        if str(raw_event.get("type") or "").strip() != "item.completed":
            continue
        item = raw_event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() != "agent_message":
            continue
        text = str(item.get("text") or "").strip()
        if text:
            return text
    return ""


def response_items_with_canonical_final_message(
    response_items: List[Dict[str, Any]],
    turn_events: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    canonical_text = assistant_text_from_turn_events(turn_events)
    updated = [dict(item) for item in list(response_items or []) if isinstance(item, dict)]
    if not canonical_text:
        return updated
    for idx in range(len(updated) - 1, -1, -1):
        raw_item = ResponseInputItem.from_dict(updated[idx]).to_dict()
        if str(raw_item.get("type") or "").strip() != "message":
            continue
        if str(raw_item.get("role") or "").strip() != "assistant":
            continue
        content = [dict(block) for block in list(raw_item.get("content") or []) if isinstance(block, dict)]
        replaced = False
        for block_idx in range(len(content) - 1, -1, -1):
            block = dict(content[block_idx])
            block_type = str(block.get("type") or "").strip()
            if block_type in {"output_text", "input_text", "text"}:
                block["text"] = canonical_text
                content[block_idx] = block
                replaced = True
                break
        if not replaced:
            content.append({"type": "output_text", "text": canonical_text})
        raw_item["content"] = content
        updated[idx] = raw_item
        return updated
    updated.append(
        ResponseInputItem(
            item_type="message",
            role="assistant",
            content=[{"type": "output_text", "text": canonical_text}],
            extra={"phase": "final_answer"},
        ).to_dict()
    )
    return updated


def history_replay_response_items(turn: ThreadHistoryTurn) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for raw_item in list(turn.response_items or []):
        normalized = ResponseInputItem.from_dict(
            raw_item.to_dict() if hasattr(raw_item, "to_dict") else dict(raw_item or {})
        ).to_dict()
        item_type = str(normalized.get("type") or "").strip().lower()
        role = str(normalized.get("role") or "").strip().lower()
        phase = str(normalized.get("phase") or "").strip().lower()
        if item_type == "message" and role == "assistant" and phase == "commentary":
            continue
        items.append(normalized)
    return items


def preferred_assistant_turn_text(
    turn: ThreadHistoryTurn,
    *,
    response_items_to_text_fn,
    include_response_items: bool = True,
) -> str:
    response_item_text = (
        response_items_to_text_fn(list(turn.response_items or [])).strip()
        if include_response_items
        else ""
    )
    assistant_history_text = str(turn.assistant_history_text or "").strip()
    assistant_fallback_text = str(turn.assistant_text or "").strip()
    canonical_turn_text = assistant_text_from_turn_events(
        [dict(item) for item in list(turn.turn_events or []) if isinstance(item, dict)]
    )
    if turn_has_structured_tool_items(turn) and canonical_turn_text:
        if assistant_history_text and canonical_turn_text in assistant_history_text:
            if assistant_history_text.startswith(canonical_turn_text):
                return canonical_turn_text
            return assistant_history_text
        if response_item_text and "\n\n" in response_item_text:
            return assistant_history_text or response_item_text
        return canonical_turn_text
    return assistant_history_text or response_item_text or assistant_fallback_text


def planner_turn_response_replay_items(
    turn: ThreadHistoryTurn,
    *,
    replay_input_items_from_turn_events_fn,
    response_items_with_tool_outputs_fn,
    response_items_to_text_fn,
) -> List[Dict[str, Any]]:
    turn_events = [dict(item) for item in list(turn.turn_events or []) if isinstance(item, dict)]
    tool_events = [item.to_dict() for item in list(turn.tool_events or [])]
    has_tool_history = turn_has_tool_history(turn)
    if turn.response_items:
        response_items = history_replay_response_items(turn)
        if has_tool_history:
            if assistant_text_from_turn_events(turn_events):
                response_items = response_items_with_canonical_final_message(
                    response_items,
                    turn_events,
                )
            return response_items_with_tool_outputs_fn(response_items, turn_events, tool_events)
        return response_items
    if turn_events:
        replay_items = replay_input_items_from_turn_events_fn(turn_events)
        if replay_items:
            return replay_items
    if has_tool_history:
        return response_items_with_tool_outputs_fn([], turn_events, tool_events)
    assistant_text = preferred_assistant_turn_text(
        turn,
        response_items_to_text_fn=response_items_to_text_fn,
        include_response_items=False,
    )
    if not assistant_text:
        return []
    return [
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": assistant_text}],
        }
    ]

from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli.models import ResponseInputItem


def shared_replay_reasoning_retention_diagnostics(
    turn: Dict[str, Any],
    *,
    reasoning_retention_diagnostic_key_fn: Any,
    shared_replay_reasoning_projection_fn: Any,
    turn_event_tool_history_available_fn: Any,
    reasoning_replay_projection_from_turn_event_item_fn: Any,
) -> List[Dict[str, Any]]:
    if not isinstance(turn, dict):
        return []
    diagnostics: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def _record(diagnostic: Dict[str, Any] | None) -> None:
        if not isinstance(diagnostic, dict) or not diagnostic:
            return
        diagnostic_key = reasoning_retention_diagnostic_key_fn(diagnostic)
        if diagnostic_key in seen:
            return
        seen.add(diagnostic_key)
        diagnostics.append(dict(diagnostic))

    response_items = [
        dict(item)
        for item in list(turn.get("response_items") or [])
        if isinstance(item, dict)
    ]
    turn_events = [dict(item) for item in list(turn.get("turn_events") or []) if isinstance(item, dict)]
    tool_events = [dict(item) for item in list(turn.get("tool_events") or []) if isinstance(item, dict)]
    has_tool_history = bool(tool_events or turn_event_tool_history_available_fn(turn_events))
    if response_items and has_tool_history:
        for item in response_items:
            projection = shared_replay_reasoning_projection_fn(item, source="tool_history_projection")
            _record(projection.get("diagnostic"))
        return diagnostics
    for raw_event in turn_events:
        if str(raw_event.get("type") or "").strip() != "item.completed":
            continue
        item = raw_event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip().lower() != "reasoning":
            continue
        projection = reasoning_replay_projection_from_turn_event_item_fn(item)
        _record(projection.get("diagnostic"))
    return diagnostics


def replay_input_items_from_turn_events(
    turn_events: List[Dict[str, Any]],
    *,
    reasoning_turn_event_key_fn: Any,
    reasoning_replay_projection_from_turn_event_item_fn: Any,
    response_input_item_from_web_search_turn_item_fn: Any,
    sanitize_tool_input_item_fn: Any,
    function_call_input_items_from_turn_events_fn: Any,
    tool_output_input_items_from_turn_events_fn: Any,
    provider_tool_call_input_items_from_turn_events_fn: Any,
    projected_structured_call_items_from_turn_events_fn: Any,
    response_input_call_id_overrides_fn: Any,
    apply_call_id_overrides_fn: Any,
    dedupe_tool_projection_items_fn: Any,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    emitted_reasoning: set[tuple[str, str, str]] = set()
    emitted_messages: set[tuple[str, str]] = set()
    emitted_calls: set[str] = set()
    emitted_outputs: set[str] = set()
    native_item_positions: dict[str, int] = {}
    for raw_event in list(turn_events or []):
        if not isinstance(raw_event, dict):
            continue
        event_type = str(raw_event.get("type") or "").strip()
        if event_type not in {"item.started", "item.completed"}:
            continue
        item = raw_event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip().lower()
        call_id = str(item.get("call_id") or item.get("tool_call_id") or item.get("id") or "").strip()
        if event_type == "item.completed" and item_type == "reasoning":
            projection = reasoning_replay_projection_from_turn_event_item_fn(item)
            reasoning_item = projection.get("input_item")
            if reasoning_item is not None:
                reasoning_key = reasoning_turn_event_key_fn(item)
                if reasoning_key not in emitted_reasoning:
                    emitted_reasoning.add(reasoning_key)
                    items.append(dict(reasoning_item))
            continue
        if event_type == "item.completed" and item_type == "agent_message":
            text = str(item.get("text") or "").strip()
            key = ("assistant", text)
            if text and key not in emitted_messages:
                emitted_messages.add(key)
                items.append(
                    ResponseInputItem(
                        item_type="message",
                        role="assistant",
                        content=[{"type": "output_text", "text": text}],
                    ).to_dict()
                )
            continue
        if event_type in {"item.started", "item.completed"} and item_type == "web_search_call":
            input_item = response_input_item_from_web_search_turn_item_fn(item)
            if input_item is None:
                continue
            input_item_id = str(input_item.get("id") or "").strip()
            if input_item_id:
                normalized_input_item = ResponseInputItem.from_dict(input_item).to_dict()
                existing_index = native_item_positions.get(input_item_id)
                if existing_index is None:
                    native_item_positions[input_item_id] = len(items)
                    items.append(normalized_input_item)
                else:
                    existing_status = str(items[existing_index].get("status") or "").strip().lower()
                    new_status = str(normalized_input_item.get("status") or "").strip().lower()
                    if existing_status not in {"completed", "failed"} or new_status in {"completed", "failed"}:
                        items[existing_index] = normalized_input_item
                continue
            items.append(ResponseInputItem.from_dict(input_item).to_dict())
            continue
        if event_type == "item.completed" and item_type in {"function_call", "custom_tool_call", "shell_call", "local_shell_call"}:
            if call_id and call_id not in emitted_calls:
                emitted_calls.add(call_id)
                items.append(sanitize_tool_input_item_fn(ResponseInputItem.from_dict(item).to_dict()))
            continue
        if event_type == "item.completed" and item_type in {
            "function_call_output",
            "custom_tool_call_output",
            "shell_call_output",
            "local_shell_call_output",
        }:
            if call_id and call_id in emitted_outputs:
                continue
            if call_id:
                emitted_outputs.add(call_id)
            items.append(ResponseInputItem.from_dict(item).to_dict())
            continue
        if item_type in {"command_execution", "mcp_tool_call", "todo_list"} and call_id and call_id not in emitted_calls:
            emitted_calls.add(call_id)
            items.extend(function_call_input_items_from_turn_events_fn([raw_event]))
        if event_type == "item.completed" and item_type in {"command_execution", "mcp_tool_call", "todo_list"}:
            if call_id and call_id in emitted_outputs:
                continue
            if call_id:
                emitted_outputs.add(call_id)
            items.extend(tool_output_input_items_from_turn_events_fn([raw_event]))
    provider_call_items = provider_tool_call_input_items_from_turn_events_fn(turn_events)
    projected_call_items = projected_structured_call_items_from_turn_events_fn(turn_events)
    projected_to_provider_overrides = response_input_call_id_overrides_fn(projected_call_items, provider_call_items)
    items = apply_call_id_overrides_fn(items, projected_to_provider_overrides)
    return dedupe_tool_projection_items_fn(items)


def reasoning_input_items_from_turn_events(
    turn_events: List[Dict[str, Any]],
    *,
    reasoning_input_item_from_turn_event_item_fn: Any,
    reasoning_turn_event_key_fn: Any,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen_reasoning: set[tuple[str, str, str]] = set()
    for raw_event in list(turn_events or []):
        if not isinstance(raw_event, dict):
            continue
        if str(raw_event.get("type") or "").strip() != "item.completed":
            continue
        item = raw_event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip().lower() != "reasoning":
            continue
        reasoning_item = reasoning_input_item_from_turn_event_item_fn(item)
        if reasoning_item is None:
            continue
        reasoning_key = reasoning_turn_event_key_fn(item)
        if reasoning_key in seen_reasoning:
            continue
        seen_reasoning.add(reasoning_key)
        items.append(reasoning_item)
    return items

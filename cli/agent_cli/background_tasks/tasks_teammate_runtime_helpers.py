from __future__ import annotations

import json
from typing import Any, Callable


def consume_headless_jsonl_line_impl(
    state: dict[str, Any],
    line: str,
    *,
    reasoning_text_fn: Callable[[dict[str, Any]], str],
    command_execution_payload_fn: Callable[[dict[str, Any]], dict[str, Any]],
    structured_payload_from_tool_item_fn: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    text = str(line or "").strip()
    if not text:
        return state
    try:
        event = json.loads(text)
    except json.JSONDecodeError:
        return state
    if not isinstance(event, dict):
        return state
    state["event_count"] = int(state.get("event_count") or 0) + 1
    event_type = str(event.get("type") or "").strip()
    if event_type == "thread.started":
        thread_id = str(event.get("thread_id") or "").strip()
        if thread_id:
            state["thread_id"] = thread_id
        return state
    if event_type not in {"turn.started", "turn.completed", "item.started", "item.updated", "item.completed"}:
        return state
    turn_events = list(state.get("turn_events") or [])
    turn_events.append(dict(event))
    state["turn_events"] = turn_events[-256:]
    item = event.get("item")
    if not isinstance(item, dict):
        return state
    item_type = str(item.get("type") or "").strip().lower()
    if item_type == "reasoning":
        reasoning_text = reasoning_text_fn(item)
        if reasoning_text:
            state["latest_reasoning_text"] = reasoning_text
        return state
    if item_type == "agent_message":
        message_text = str(item.get("text") or "").strip()
        if not message_text:
            return state
        phase = str(item.get("phase") or "").strip().lower()
        if phase == "commentary":
            state["commentary_text"] = message_text
        else:
            state["assistant_text"] = message_text
        return state
    if event_type != "item.completed":
        return state
    tool_events = list(state.get("tool_events") or [])
    if item_type == "command_execution":
        tool_events.append(
            {
                "name": "exec_command",
                "payload": command_execution_payload_fn(item),
            }
        )
    elif item_type == "mcp_tool_call":
        tool_name = str(item.get("tool") or "").strip()
        if tool_name:
            tool_events.append(
                {
                    "name": tool_name,
                    "payload": structured_payload_from_tool_item_fn(item),
                }
            )
    state["tool_events"] = tool_events[-128:]
    return state


def command_policy_projection_impl(response_payload: dict[str, Any]) -> list[dict[str, Any]]:
    projection: list[dict[str, Any]] = []
    for item in list(response_payload.get("tool_events") or []):
        if not isinstance(item, dict):
            continue
        payload = item.get("payload")
        if not isinstance(payload, dict):
            continue
        command = str(payload.get("command") or "").strip()
        effective_command = str(payload.get("effective_command") or "").strip()
        status = str(payload.get("status") or "").strip()
        command_policy = payload.get("command_policy")
        policy_mapping = dict(command_policy) if isinstance(command_policy, dict) else {}
        denied = status.lower() == "policy_denied" or policy_mapping.get("allowed") is False
        error_code = str(payload.get("error_code") or policy_mapping.get("error_code") or "").strip()
        if not (command or effective_command or denied or error_code):
            continue
        projection.append(
            {
                "command": command,
                "effective_command": effective_command,
                "status": status,
                "policy_denied": denied,
                "error_code": error_code,
                "command_policy": policy_mapping,
            }
        )
    return projection

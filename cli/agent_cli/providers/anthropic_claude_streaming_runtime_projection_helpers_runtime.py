from __future__ import annotations

import json
from typing import Any, Dict


def stream_agent_message_event(*, event_type: str, item_id: str, text: str) -> Dict[str, Any]:
    return {
        "type": event_type,
        "item": {
            "id": item_id,
            "type": "agent_message",
            "text": text,
        },
    }


def stream_reasoning_event(*, event_type: str, item_id: str, text: str) -> Dict[str, Any]:
    return {
        "type": event_type,
        "item": {
            "id": item_id,
            "type": "reasoning",
            "text": text,
        },
    }


def stream_function_call_started_event(*, call_id: str, name: str) -> Dict[str, Any]:
    return {
        "type": "item.started",
        "item": {
            "id": call_id or name or "anthropic_tool_call",
            "type": "function_call",
            "call_id": call_id or None,
            "name": name,
        },
    }


def stream_function_call_completed_event(
    *,
    call_id: str,
    name: str,
    arguments: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "type": "item.completed",
        "item": {
            "id": call_id or name or "anthropic_tool_call",
            "type": "function_call",
            "call_id": call_id or None,
            "name": name,
            "arguments": json.dumps(arguments, ensure_ascii=False),
        },
    }


__all__ = [
    "stream_agent_message_event",
    "stream_function_call_completed_event",
    "stream_function_call_started_event",
    "stream_reasoning_event",
]

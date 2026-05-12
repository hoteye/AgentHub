from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from cli.agent_cli.models import (
    PromptResponse,
    ResponseInputItem,
    default_response_items,
    response_items_to_text,
)
from cli.agent_cli.models_response_items import terminal_failure_message


def canonical_turn_events(
    response: PromptResponse,
    *,
    response_items: list[Any] | None = None,
    shell_turn_events_from_tool_events_fn: (
        Callable[[list[Any]], list[dict[str, Any]]] | None
    ) = None,
) -> list[dict[str, Any]]:
    explicit = [dict(item) for item in list(response.turn_events or []) if isinstance(item, dict)]
    if explicit:
        return explicit
    if callable(shell_turn_events_from_tool_events_fn):
        shell_events = shell_turn_events_from_tool_events_fn(list(response.tool_events or []))
        if shell_events:
            return shell_events
    items = list(
        response_items
        or response.response_items
        or default_response_items(
            commentary_text=str(response.commentary_text or ""),
            assistant_text=str(response.assistant_text or ""),
        )
    )
    normalized_items = [
        item if isinstance(item, ResponseInputItem) else ResponseInputItem.from_dict(dict(item))
        for item in items
        if isinstance(item, ResponseInputItem | dict)
    ]
    rendered_text = response_items_to_text(normalized_items).strip()
    events: list[dict[str, Any]] = [{"type": "turn.started"}]
    if rendered_text:
        events.append(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_0",
                    "type": "agent_message",
                    "text": rendered_text,
                },
            }
        )
    failure_message = terminal_failure_message(
        protocol_diagnostics=dict(getattr(response, "protocol_diagnostics", {}) or {}),
        status=dict(getattr(response, "status", {}) or {}),
    )
    if failure_message:
        events.append(
            {
                "type": "turn.failed",
                "error": {"message": failure_message},
            }
        )
    else:
        events.append(
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 0,
                    "cached_input_tokens": 0,
                    "output_tokens": 0,
                },
            }
        )
    return events


def normalized_turn_event_value(value: Any) -> Any:
    if isinstance(value, dict):
        if str(value.get("type") or "").strip() == "agent_message":
            normalized_agent_message: dict[str, Any] = {}
            for key, item in dict(value or {}).items():
                if str(key) == "id":
                    continue
                normalized_agent_message[str(key)] = normalized_turn_event_value(item)
            phase = str(normalized_agent_message.get("phase") or "").strip().lower()
            normalized_agent_message["phase"] = phase or "final_answer"
            return normalized_agent_message
        normalized: dict[str, Any] = {}
        for key, item in dict(value or {}).items():
            if str(key) == "id":
                continue
            normalized[str(key)] = normalized_turn_event_value(item)
        return normalized
    if isinstance(value, list):
        return [normalized_turn_event_value(item) for item in list(value or [])]
    return value


def turn_event_backfill_signature(
    event: dict[str, Any],
    *,
    normalized_turn_event_value_fn: Callable[[Any], Any] | None = None,
) -> str:
    normalized = (normalized_turn_event_value_fn or normalized_turn_event_value)(dict(event or {}))
    try:
        return json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return repr(normalized)

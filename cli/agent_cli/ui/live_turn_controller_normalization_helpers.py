from __future__ import annotations

import json
from typing import Callable


def turn_event_signature(
    event: dict[str, object],
    *,
    backfill_signature_fn: Callable[[dict[str, object]], str],
) -> str:
    item = event.get("item")
    if isinstance(item, dict) and str(item.get("type") or "").strip() == "reasoning":
        return backfill_signature_fn(event)
    try:
        return json.dumps(event, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return repr(event)


def normalized_turn_event_value(value: object) -> object:
    if isinstance(value, dict):
        item_type = str(value.get("type") or "").strip()
        if item_type == "agent_message":
            normalized_agent_message: dict[str, object] = {}
            for key, item in dict(value).items():
                if str(key) == "id":
                    continue
                normalized_agent_message[str(key)] = normalized_turn_event_value(item)
            phase = str(normalized_agent_message.get("phase") or "").strip().lower()
            normalized_agent_message["phase"] = phase or "final_answer"
            return normalized_agent_message
        if item_type == "reasoning":
            normalized_reasoning: dict[str, object] = {}
            for key, item in dict(value).items():
                if str(key) in {"id", "provider_item_id", "status", "summary", "encrypted_content"}:
                    continue
                normalized_reasoning[str(key)] = normalized_turn_event_value(item)
            return normalized_reasoning
        normalized: dict[str, object] = {}
        for key, item in dict(value).items():
            if str(key) == "id":
                continue
            normalized[str(key)] = normalized_turn_event_value(item)
        return normalized
    if isinstance(value, list):
        return [normalized_turn_event_value(item) for item in list(value)]
    return value


def turn_event_backfill_signature(event: dict[str, object]) -> str:
    normalized = normalized_turn_event_value(dict(event or {}))
    try:
        return json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return repr(normalized)

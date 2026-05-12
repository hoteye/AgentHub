from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any


def normalized_turn_event_value(
    value: Any,
    *,
    normalize_nested_value_fn: Callable[[Any], Any],
) -> Any:
    if isinstance(value, dict):
        if str(value.get("type") or "").strip() == "agent_message":
            normalized_agent_message: dict[str, Any] = {}
            for key, item in dict(value or {}).items():
                if str(key) == "id":
                    continue
                normalized_agent_message[str(key)] = normalize_nested_value_fn(item)
            phase = str(normalized_agent_message.get("phase") or "").strip().lower()
            normalized_agent_message["phase"] = phase or "final_answer"
            return normalized_agent_message
        normalized: dict[str, Any] = {}
        for key, item in dict(value or {}).items():
            if str(key) == "id":
                continue
            normalized[str(key)] = normalize_nested_value_fn(item)
        return normalized
    if isinstance(value, list):
        return [normalize_nested_value_fn(item) for item in list(value or [])]
    return value


def turn_event_replay_signature(
    event: Mapping[str, Any] | None,
    *,
    normalized_turn_event_value_fn: Callable[[Any], Any],
) -> str:
    normalized = normalized_turn_event_value_fn(dict(event or {}))
    try:
        return json.dumps(normalized, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return repr(normalized)


def normalized_pending_steer_limit(limit: Any) -> int | None:
    if limit is None:
        return None
    try:
        return max(0, int(limit))
    except (TypeError, ValueError):
        return None

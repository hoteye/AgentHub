from __future__ import annotations

import json
from typing import Any, Dict, Optional


class StreamFallback(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = str(reason or "").strip() or "stream_unavailable"


def stream_value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def stream_dict_payload(source: Any) -> Dict[str, Any]:
    if isinstance(source, dict):
        return dict(source)
    if source is None:
        return {}
    if hasattr(source, "__dict__"):
        return {
            str(key): value
            for key, value in vars(source).items()
            if not str(key).startswith("_")
        }
    return {}


def stream_string(value: Any) -> str:
    return str(value or "").strip()


def stream_event_type(event: Any) -> str:
    return stream_string(stream_value(event, "type"))


def stream_iterable(stream_handle: Any) -> Any:
    if hasattr(stream_handle, "__iter__"):
        return stream_handle
    events_fn = getattr(stream_handle, "events", None)
    if callable(events_fn):
        return events_fn()
    stream_attr = getattr(stream_handle, "stream", None)
    if hasattr(stream_attr, "__iter__"):
        return stream_attr
    raise StreamFallback("stream_api_invalid")


def stream_final_response(stream_handle: Any) -> Any:
    for method_name in ("get_final_message", "get_final_response"):
        method = getattr(stream_handle, method_name, None)
        if callable(method):
            try:
                response = method()
            except Exception:
                continue
            if response is not None:
                return response
    return None


def stream_content_block(event: Any) -> Dict[str, Any]:
    for key in ("content_block", "block", "item"):
        candidate = stream_value(event, key)
        if candidate is None:
            continue
        payload = stream_dict_payload(candidate)
        if payload:
            return payload
    return {}


def stream_delta_payload(event: Any) -> Dict[str, Any]:
    return stream_dict_payload(stream_value(event, "delta"))


def stream_int_value(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def stream_message_item_id(message_id: str, index: int) -> str:
    prefix = message_id or "anthropic_message"
    return f"{prefix}:{index}"


def stream_parse_tool_input(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    partial = str(state.get("input_buffer") or "").strip()
    if partial:
        try:
            parsed = json.loads(partial)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict):
            return None
        return dict(parsed)
    current_input = state.get("input")
    if isinstance(current_input, dict):
        return dict(current_input)
    return {}


__all__ = [
    "StreamFallback",
    "stream_content_block",
    "stream_delta_payload",
    "stream_dict_payload",
    "stream_event_type",
    "stream_final_response",
    "stream_int_value",
    "stream_iterable",
    "stream_message_item_id",
    "stream_parse_tool_input",
    "stream_string",
    "stream_value",
]

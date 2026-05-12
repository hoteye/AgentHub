from __future__ import annotations

from typing import Any


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    payload: dict[str, Any] = {}
    for key in (
        "input_tokens",
        "cached_input_tokens",
        "output_tokens",
        "reasoning_output_tokens",
        "total_tokens",
        "input_tokens_details",
        "output_tokens_details",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
    ):
        if hasattr(value, key):
            payload[key] = getattr(value, key)
    return payload


def _int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def usage_from_provider_response(response: Any) -> dict[str, int]:
    usage = _mapping(getattr(response, "usage", None))
    if not usage:
        return {}

    input_details = _mapping(usage.get("input_tokens_details"))
    output_details = _mapping(usage.get("output_tokens_details"))

    input_tokens = _int(usage.get("input_tokens"))
    output_tokens = _int(usage.get("output_tokens"))
    cached_input_tokens = _int(
        usage.get("cached_input_tokens")
        if usage.get("cached_input_tokens") is not None
        else usage.get("cache_read_input_tokens")
        if usage.get("cache_read_input_tokens") is not None
        else input_details.get("cached_tokens")
    )
    reasoning_output_tokens = _int(
        usage.get("reasoning_output_tokens")
        if usage.get("reasoning_output_tokens") is not None
        else output_details.get("reasoning_tokens")
    )
    total_tokens = _int(usage.get("total_tokens")) or input_tokens + output_tokens

    if not any((input_tokens, output_tokens, cached_input_tokens, reasoning_output_tokens, total_tokens)):
        return {}
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "reasoning_output_tokens": reasoning_output_tokens,
        "total_tokens": total_tokens,
    }

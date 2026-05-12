from __future__ import annotations

from typing import Any


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def configured_model_raw_context_window(raw_model: dict[str, Any] | None) -> int:
    data = dict(raw_model or {})
    configured = _int(
        data.get("model_context_window")
        or data.get("modelContextWindow")
        or data.get("context_window_tokens")
        or data.get("contextWindowTokens")
        or data.get("context_window")
        or data.get("contextWindow")
    )
    max_window = _int(data.get("max_context_window") or data.get("maxContextWindow"))
    if configured <= 0:
        configured = max_window
    elif max_window > 0:
        configured = min(configured, max_window)
    return max(0, configured)


def configured_model_context_window(raw_model: dict[str, Any] | None) -> int:
    data = dict(raw_model or {})
    configured = configured_model_raw_context_window(data)
    if configured <= 0:
        return 0

    effective_percent = _int(
        data.get("effective_context_window_percent")
        or data.get("effectiveContextWindowPercent")
        or 95
    )
    if effective_percent <= 0:
        effective_percent = 100
    return max(0, configured * min(effective_percent, 100) // 100)


def configured_model_auto_compact_token_limit(raw_model: dict[str, Any] | None) -> int:
    data = dict(raw_model or {})
    context_window = configured_model_raw_context_window(data)
    context_limit = context_window * 9 // 10 if context_window > 0 else 0
    configured_limit = _int(
        data.get("model_auto_compact_token_limit")
        or data.get("modelAutoCompactTokenLimit")
        or data.get("auto_compact_token_limit")
        or data.get("autoCompactTokenLimit")
    )
    if context_limit > 0:
        return min(configured_limit, context_limit) if configured_limit > 0 else context_limit
    return max(0, configured_limit)

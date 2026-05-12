from __future__ import annotations

from typing import Any

BASELINE_TOKENS = 12_000


def _int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _usage_from_mapping(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    input_tokens = _int(value.get("input_tokens"))
    cached_input_tokens = _int(value.get("cached_input_tokens"))
    output_tokens = _int(value.get("output_tokens"))
    reasoning_output_tokens = _int(value.get("reasoning_output_tokens"))
    total_tokens = _int(value.get("total_tokens")) or input_tokens + output_tokens
    if not any(
        (input_tokens, cached_input_tokens, output_tokens, reasoning_output_tokens, total_tokens)
    ):
        return {}
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "reasoning_output_tokens": reasoning_output_tokens,
        "total_tokens": total_tokens,
    }


def _usage_from_turn_events(turn_events: Any) -> dict[str, int]:
    for event in reversed([item for item in list(turn_events or []) if isinstance(item, dict)]):
        if str(event.get("type") or "").strip() != "turn.completed":
            continue
        usage = _usage_from_mapping(event.get("usage"))
        if usage:
            return usage
    return {}


def _usage_from_timings(timings: Any) -> dict[str, int]:
    if not isinstance(timings, dict):
        return {}
    for key in ("token_usage", "usage"):
        usage = _usage_from_mapping(timings.get(key))
        if usage:
            return usage
    planning_trace = timings.get("planning_trace")
    if isinstance(planning_trace, list):
        for entry in reversed(planning_trace):
            if not isinstance(entry, dict):
                continue
            usage = _usage_from_mapping(entry.get("usage"))
            if usage:
                return usage
    return {}


def context_remaining_percent(*, used_tokens: int, context_window: int) -> int | None:
    if context_window <= 0:
        return None
    if context_window <= BASELINE_TOKENS:
        return 0
    effective_window = context_window - BASELINE_TOKENS
    used = max(0, used_tokens - BASELINE_TOKENS)
    remaining = max(0, effective_window - used)
    return max(0, min(100, round((remaining / effective_window) * 100)))


def context_usage_status_from_response(
    response: Any, *, current_status: dict[str, Any]
) -> dict[str, str]:
    response_status = getattr(response, "status", None)
    status_usage = response_status.get("usage") if isinstance(response_status, dict) else None
    usage = (
        _usage_from_turn_events(getattr(response, "turn_events", None))
        or _usage_from_timings(getattr(response, "timings", None))
        or _usage_from_mapping(status_usage)
    )
    if not usage:
        return {}

    context_window = _int(
        current_status.get("model_context_window")
        or current_status.get("provider_model_context_window")
        or current_status.get("context_window_tokens")
        or current_status.get("context_window")
    )
    used_tokens = usage["total_tokens"]
    status = {
        "input_tokens": str(usage["input_tokens"]),
        "cached_input_tokens": str(usage["cached_input_tokens"]),
        "output_tokens": str(usage["output_tokens"]),
        "reasoning_output_tokens": str(usage["reasoning_output_tokens"]),
        "total_tokens": str(usage["total_tokens"]),
        "context_window_used_tokens": str(used_tokens),
    }
    if context_window > 0:
        status["context_window_tokens"] = str(context_window)
    percent = context_remaining_percent(
        used_tokens=used_tokens,
        context_window=context_window,
    )
    if percent is not None:
        status["context_window_remaining_percent"] = str(percent)
    return status


def format_tokens_compact(tokens: Any) -> str:
    value = _int(tokens)
    if value < 1_000:
        return str(value)
    if value >= 1_000_000_000_000:
        scaled, suffix = value / 1_000_000_000_000, "T"
    elif value >= 1_000_000_000:
        scaled, suffix = value / 1_000_000_000, "B"
    elif value >= 1_000_000:
        scaled, suffix = value / 1_000_000, "M"
    else:
        scaled, suffix = value / 1_000, "K"

    if scaled < 10:
        decimals = 2
    elif scaled < 100:
        decimals = 1
    else:
        decimals = 0
    formatted = f"{scaled:.{decimals}f}"
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return f"{formatted}{suffix}"


def format_tokens_footer_brief(tokens: Any) -> str:
    value = _int(tokens)
    if value < 1_000:
        return str(value)
    units = (
        (1_000_000_000_000, "t"),
        (1_000_000_000, "b"),
        (1_000_000, "m"),
        (1_000, "k"),
    )
    for scale, suffix in units:
        if value >= scale:
            return f"{max(1, int((value / scale) + 0.5))}{suffix}"
    return str(value)


def context_window_footer_text(
    *,
    status_data: dict[str, Any],
    translate_fn,
) -> str:
    used_tokens = _int(status_data.get("context_window_used_tokens"))
    context_window = _int(
        status_data.get("context_window_tokens")
        or status_data.get("model_context_window")
        or status_data.get("provider_model_context_window")
        or status_data.get("context_window")
    )
    percent = _int(status_data.get("context_window_remaining_percent"))
    if str(status_data.get("context_window_remaining_percent") or "").strip():
        if str(status_data.get("context_window_used_tokens") or "").strip() and context_window > 0:
            return translate_fn(
                "footer.context_left.detail",
                percent=max(0, min(100, percent)),
                used=format_tokens_footer_brief(used_tokens),
                window=format_tokens_footer_brief(context_window),
            )
        return translate_fn("footer.context_left.percent", percent=max(0, min(100, percent)))

    if str(status_data.get("context_window_used_tokens") or "").strip():
        computed_percent = context_remaining_percent(
            used_tokens=used_tokens,
            context_window=context_window,
        )
        if computed_percent is not None:
            return translate_fn(
                "footer.context_left.detail",
                percent=max(0, min(100, computed_percent)),
                used=format_tokens_footer_brief(used_tokens),
                window=format_tokens_footer_brief(context_window),
            )
        return translate_fn(
            "footer.context_used.tokens", tokens=format_tokens_footer_brief(used_tokens)
        )

    return ""

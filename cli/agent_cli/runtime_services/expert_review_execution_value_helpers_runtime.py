from __future__ import annotations

import time
from typing import Any, Callable


def normalized_text(value: Any) -> str:
    return str(value or "").strip()


def normalized_choice(
    value: Any,
    *,
    allowed: tuple[str, ...],
    default: str,
    normalized_text_fn: Callable[[Any], str],
) -> str:
    normalized = normalized_text_fn(value).lower()
    if normalized in allowed:
        return normalized
    return default


def sequence_items(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, (set, frozenset)):
        return sorted(list(value), key=lambda item: str(item))
    return [value]


def normalized_string_list(
    value: Any,
    *,
    allowed: tuple[str, ...] | None = None,
    sequence_items_fn: Callable[[Any], list[Any]],
    normalized_text_fn: Callable[[Any], str],
) -> list[str]:
    items: list[str] = []
    allowed_values = set(allowed or ())
    for raw_item in sequence_items_fn(value):
        normalized = normalized_text_fn(raw_item)
        if not normalized:
            continue
        normalized_lower = normalized.lower()
        if allowed_values and normalized_lower not in allowed_values:
            continue
        candidate = normalized_lower if allowed_values else normalized
        if candidate not in items:
            items.append(candidate)
    return items


def normalized_scope(
    value: Any,
    *,
    default: str,
    normalized_choice_fn: Callable[..., str],
) -> str:
    return normalized_choice_fn(
        value,
        allowed=("latest_turn", "current_task", "selected_artifacts"),
        default=default,
    )


def normalized_max_findings(value: Any, *, default: int) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(10, normalized))


def elapsed_ms(started_at: float) -> int:
    return max(0, int((time.monotonic() - started_at) * 1000))


__all__ = [
    "elapsed_ms",
    "normalized_choice",
    "normalized_max_findings",
    "normalized_scope",
    "normalized_string_list",
    "normalized_text",
    "sequence_items",
]

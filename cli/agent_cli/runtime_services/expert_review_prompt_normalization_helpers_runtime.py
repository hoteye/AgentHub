from __future__ import annotations

import math
import os
from collections.abc import Mapping, Sequence
from typing import Any


def mapping_dict(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): value[key] for key in value}


def normalize_policy(policy: Mapping[str, Any] | None) -> dict[str, Any]:
    root = mapping_dict(policy)
    nested: dict[str, Any] = {}
    for key in ("expert_review_prompt_policy", "expert_review_policy"):
        candidate = mapping_dict(root.get(key))
        if candidate:
            nested.update(candidate)
    merged = dict(nested)
    for key, value in root.items():
        if key in {"expert_review_prompt_policy", "expert_review_policy"}:
            continue
        merged[key] = value
    return merged


def normalized_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalized_text_list(value: Any, *, limit: int) -> list[str]:
    items: list[str] = []
    for item in _sequence_items(value):
        normalized = normalized_text(item)
        if not normalized or normalized in items:
            continue
        items.append(normalized)
        if len(items) >= limit:
            break
    return items


def normalized_string_list(
    value: Any,
    *,
    allowed: Sequence[str] | None = None,
    limit: int = 16,
) -> list[str]:
    normalized_items: list[str] = []
    allowed_values = set(allowed or ())
    for item in _sequence_items(value):
        normalized = normalized_text(item).lower()
        if not normalized:
            continue
        if allowed_values and normalized not in allowed_values:
            continue
        if normalized in normalized_items:
            continue
        normalized_items.append(normalized)
        if len(normalized_items) >= limit:
            break
    return normalized_items


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, os.PathLike):
        return os.fspath(value)
    if isinstance(value, Mapping):
        return {
            normalized_text(key): json_safe(value[key])
            for key in sorted(value.keys(), key=lambda item: str(item))
            if normalized_text(key)
        }
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [json_safe(item) for item in sorted(list(value), key=lambda item: str(item))]
    return str(value)


def normalized_scope(value: Any) -> str | None:
    normalized = normalized_text(value).lower()
    if normalized in {"latest_turn", "current_task", "selected_artifacts"}:
        return normalized
    return None


def normalized_choice(value: Any, *, allowed: Sequence[str]) -> str | None:
    normalized = normalized_text(value).lower()
    if normalized in set(allowed):
        return normalized
    return None


def normalized_max_findings(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return max(1, min(10, normalized))


def dedupe_strings(values: Sequence[Any], *, limit: int) -> list[str]:
    deduped: list[str] = []
    for value in values:
        text = normalized_text(value)
        if not text or text in deduped:
            continue
        deduped.append(text)
        if len(deduped) >= limit:
            break
    return deduped


def _sequence_items(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, (set, frozenset)):
        return sorted(list(value), key=lambda item: str(item))
    return [value]


__all__ = [
    "dedupe_strings",
    "json_safe",
    "mapping_dict",
    "normalize_policy",
    "normalized_choice",
    "normalized_max_findings",
    "normalized_scope",
    "normalized_string_list",
    "normalized_text",
    "normalized_text_list",
]

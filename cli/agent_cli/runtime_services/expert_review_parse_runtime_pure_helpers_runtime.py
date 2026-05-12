from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any


_DEFAULT_SCOPE = "current_task"
_DEFAULT_STRICTNESS = "medium"

_TEXT_KEYS = (
    "text",
    "content",
    "message",
    "assistant_text",
    "output_text",
    "response_text",
    "review_text",
)


def _coerce_mapping(value: Any) -> dict[str, Any] | None:
    if isinstance(value, Mapping):
        return dict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return dict(payload)
    return None


def _jsonish_mapping(text: str) -> dict[str, Any] | None:
    for candidate in (text.strip(), _strip_markdown_fence(text)):
        if not candidate or candidate[0] not in "{[":
            continue
        try:
            payload = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if isinstance(payload, Mapping):
            return dict(payload)
        if isinstance(payload, list) and len(payload) == 1 and isinstance(payload[0], Mapping):
            return dict(payload[0])
    return None


def _strip_markdown_fence(text: str) -> str:
    lines = text.strip().splitlines()
    if len(lines) >= 3 and lines[0].lstrip().startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text.strip()


def _text_from_value(value: Any) -> str:
    fragments = _text_fragments(value)
    deduped: list[str] = []
    for fragment in fragments:
        normalized = fragment.strip()
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return "\n".join(deduped).strip()


def _text_fragments(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, bytes):
        return [value.decode("utf-8", errors="replace")]
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        fragments: list[str] = []
        for key in _TEXT_KEYS:
            if key in value:
                fragments.extend(_text_fragments(value.get(key)))
        text_value = value.get("text")
        if value.get("type") in {"text", "output_text"} and text_value is not None:
            fragments.extend(_text_fragments(text_value))
        return fragments
    if isinstance(value, Sequence):
        fragments: list[str] = []
        for item in value:
            fragments.extend(_text_fragments(item))
        return fragments
    return []


def _split_text_list(value: Any) -> list[str]:
    raw_text = _text(value)
    if not raw_text:
        return []
    items: list[str] = []
    for chunk in re.split(r"[,\n;]+", raw_text):
        normalized = chunk.strip()
        if normalized and normalized not in items:
            items.append(normalized)
    return items


def _normalized_token(value: Any) -> str:
    return re.sub(r"[\s\-]+", "_", _normalized_text(value))


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalized_text(value: Any) -> str:
    return _text(value).lower()


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _first_present(*values: Any, default: Any = "") -> Any:
    for value in values:
        if not _is_present(value):
            continue
        return value
    return default


def _boolish(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = _normalized_text(value)
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


__all__ = [
    "_DEFAULT_SCOPE",
    "_DEFAULT_STRICTNESS",
    "_TEXT_KEYS",
    "_boolish",
    "_coerce_mapping",
    "_first_present",
    "_is_present",
    "_jsonish_mapping",
    "_normalized_text",
    "_normalized_token",
    "_split_text_list",
    "_strip_markdown_fence",
    "_text",
    "_text_from_value",
    "_text_fragments",
]

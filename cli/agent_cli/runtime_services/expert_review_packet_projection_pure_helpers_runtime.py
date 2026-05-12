from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


MAX_SCOPE_TURNS = 6
MAX_MESSAGE_ENTRIES = 12
MAX_TOOL_ACTIVITY_ITEMS = 10
MAX_ARTIFACT_PATHS = 16
MAX_CHANGED_FILES = 16
MAX_TEST_EVIDENCE = 8
MAX_MESSAGE_CHARS = 600
MAX_SUMMARY_CHARS = 320
MAX_ARGUMENT_CHARS = 240
MAX_TOOL_RESULT_CHARS = 600
MAX_DIFF_SUMMARY_CHARS = 1200
MAX_EVIDENCE_TEXT_CHARS = 400
MAX_CONSTRAINT_TEXT_CHARS = 240


def normalized_string_list(
    values: Sequence[Any] | None,
    *,
    lower: bool = False,
    limit: int = MAX_ARTIFACT_PATHS,
) -> list[str]:
    items: list[str] = []
    for raw_value in list(values or []):
        text = str(raw_value or "").strip()
        if not text:
            continue
        if lower:
            text = text.lower()
        if text not in items:
            items.append(text)
        if len(items) >= limit:
            break
    return items


def clip_text(value: Any, *, max_chars: int) -> tuple[str, bool]:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text, False
    clipped = text[: max(0, max_chars - 3)].rstrip()
    return f"{clipped}...", True


def _mapping_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for entry in value:
            entry_text = _mapping_text(entry)
            if entry_text:
                parts.append(entry_text)
        return "\n".join(parts).strip()
    if isinstance(value, Mapping):
        for key in ("text", "output_text", "stdout", "summary_text", "message", "error"):
            text = _mapping_text(value.get(key))
            if text:
                return text
    return ""


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, Mapping):
        return _mapping_text(content)
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for entry in content:
        if isinstance(entry, Mapping):
            text = _mapping_text(entry)
            if text:
                parts.append(text)
        elif str(entry or "").strip():
            parts.append(str(entry).strip())
    return "\n".join(parts).strip()


def _json_preview(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        return value.strip()
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value).strip()


def _dedupe_strings(values: Sequence[Any], *, limit: int) -> list[str]:
    deduped: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in deduped:
            continue
        deduped.append(text)
        if len(deduped) >= limit:
            break
    return deduped


__all__ = [
    "MAX_ARGUMENT_CHARS",
    "MAX_ARTIFACT_PATHS",
    "MAX_CHANGED_FILES",
    "MAX_CONSTRAINT_TEXT_CHARS",
    "MAX_DIFF_SUMMARY_CHARS",
    "MAX_EVIDENCE_TEXT_CHARS",
    "MAX_MESSAGE_CHARS",
    "MAX_MESSAGE_ENTRIES",
    "MAX_SCOPE_TURNS",
    "MAX_SUMMARY_CHARS",
    "MAX_TEST_EVIDENCE",
    "MAX_TOOL_ACTIVITY_ITEMS",
    "MAX_TOOL_RESULT_CHARS",
    "clip_text",
    "normalized_string_list",
    "_content_text",
    "_dedupe_strings",
    "_json_preview",
    "_mapping_text",
]

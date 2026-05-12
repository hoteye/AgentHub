from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Mapping


REQUEST_HEADER_KEYS = ("session_id", "x-reference-turn-state")
REQUEST_BODY_KEYS = (
    "model",
    "instructions",
    "input",
    "tools",
    "tool_choice",
    "parallel_tool_calls",
    "reasoning",
    "prompt_cache_key",
)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _normalize_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if item is not None
        }
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    return value


def build_request_signature(
    request: Mapping[str, Any] | None,
    *,
    headers: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    request_item = dict(request or {})
    headers_item = dict(headers or {})
    normalized_request = {
        key: _normalize_value(request_item[key])
        for key in REQUEST_BODY_KEYS
        if key in request_item
    }
    normalized_headers = {
        key: str(headers_item.get(key) or "").strip()
        for key in REQUEST_HEADER_KEYS
        if str(headers_item.get(key) or "").strip()
    }
    return {
        "request": normalized_request,
        "headers": normalized_headers,
    }


def request_fingerprint(
    request: Mapping[str, Any] | None,
    *,
    headers: Mapping[str, Any] | None = None,
) -> str:
    signature = build_request_signature(request, headers=headers)
    raw = json.dumps(signature, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()

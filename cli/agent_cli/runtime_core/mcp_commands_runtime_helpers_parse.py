from __future__ import annotations

import json
from typing import Any


def parse_headers_json(raw_value: str) -> tuple[dict[str, str], str]:
    text = str(raw_value or "").strip()
    if not text:
        return {}, ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return {}, f"invalid headers-json: {exc.msg}"
    if not isinstance(payload, dict):
        return {}, "invalid headers-json: expected object"
    return {str(key): str(value) for key, value in payload.items()}, ""


def parse_callback_json(raw_value: str) -> tuple[dict[str, Any], str]:
    text = str(raw_value or "").strip()
    if not text:
        return {}, ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        return {}, f"invalid callback-json: {exc.msg}"
    if not isinstance(payload, dict):
        return {}, "invalid callback-json: expected object"
    return dict(payload), ""


def parse_bool_flag(value: str) -> bool | None:
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return None


def normalize_payload_items(payload: Any, candidate_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in candidate_keys:
        items = payload.get(key)
        if isinstance(items, list):
            return [dict(item) for item in items if isinstance(item, dict)]
        if isinstance(items, dict):
            rows: list[dict[str, Any]] = []
            for row_key, row_value in items.items():
                row = dict(row_value) if isinstance(row_value, dict) else {"value": row_value}
                row.setdefault("id", str(row_key))
                rows.append(row)
            return rows
    return []

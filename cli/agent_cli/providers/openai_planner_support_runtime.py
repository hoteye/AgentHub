from __future__ import annotations

import json
import re
import shlex
from typing import Any, Callable, Dict, Optional


def log_responses_request(
    stage: str,
    kwargs: Dict[str, Any],
    *,
    timeline_debug_enabled_fn: Callable[[], bool],
    log_timeline_fn: Callable[..., None],
    json_ready_fn: Callable[[Any], Any],
) -> None:
    if not timeline_debug_enabled_fn():
        return
    payload = dict(kwargs or {})
    input_items = payload.get("input")
    log_timeline_fn(
        f"{stage}.request_raw",
        request=json_ready_fn(payload),
        input_count=len(list(input_items or [])) if isinstance(input_items, list) else None,
        tool_count=len(list(payload.get("tools") or [])) if isinstance(payload.get("tools"), list) else 0,
        stream=bool(payload.get("stream")),
        previous_response_id=payload.get("previous_response_id"),
    )


def log_responses_response(
    stage: str,
    response: Any,
    *,
    timeline_debug_enabled_fn: Callable[[], bool],
    log_timeline_fn: Callable[..., None],
    json_ready_fn: Callable[[Any], Any],
) -> None:
    if not timeline_debug_enabled_fn():
        return
    log_timeline_fn(
        f"{stage}.response_raw",
        response=json_ready_fn(response),
        response_id=str(getattr(response, "id", "") or "").strip() or None,
    )


def message_input_item(role: str, content: str) -> Dict[str, Any]:
    return {
        "role": str(role or "user").strip() or "user",
        "content": str(content or ""),
    }


def extract_json_payload(raw_text: str) -> Optional[Dict[str, Any]]:
    text = str(raw_text or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return payload if isinstance(payload, dict) else None


def quote_arg(value: Any) -> str:
    return shlex.quote(str(value))


def optional_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default

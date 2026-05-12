from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4


def runtime_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def delegated_agent_id() -> str:
    return f"agent_{uuid4().hex[:10]}"


def delegated_queue_item(
    message: str,
    *,
    interrupt: bool = False,
    step_id: str = "",
    input_items: list[dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    payload = {
        "message": str(message or "").strip(),
        "interrupt": bool(interrupt),
    }
    if str(step_id or "").strip():
        payload["step_id"] = str(step_id or "").strip()
    if input_items is not None:
        payload["input_items"] = [dict(item) for item in list(input_items or []) if isinstance(item, dict)]
    return payload


def normalized_delegated_queue_item(item: Any) -> Dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    message = str(item.get("message") or "").strip()
    if not message:
        return None
    payload = {
        "message": message,
        "interrupt": bool(item.get("interrupt")),
    }
    if str(item.get("step_id") or "").strip():
        payload["step_id"] = str(item.get("step_id") or "").strip()
    input_items = item.get("input_items")
    if isinstance(input_items, list):
        payload["input_items"] = [dict(entry) for entry in input_items if isinstance(entry, dict)]
    return payload

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def start_thread_payload_thread_id(payload: Any) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    thread = payload.get("thread")
    if not isinstance(thread, Mapping):
        return None
    thread_id = str(thread.get("thread_id") or "").strip()
    return thread_id or None


__all__ = ["start_thread_payload_thread_id"]

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def parse_runtime_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def elapsed_ms(started_at: Any, ended_at: Any = None) -> int | None:
    started = parse_runtime_iso(started_at)
    if started is None:
        return None
    ended = parse_runtime_iso(ended_at) if ended_at not in (None, "") else now_utc()
    if ended is None:
        ended = now_utc()
    return max(0, int((ended - started).total_seconds() * 1000))

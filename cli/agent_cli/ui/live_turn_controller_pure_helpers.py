from __future__ import annotations

from datetime import datetime
from typing import Callable


def entry_has_completion_time(
    content: str,
    *,
    completion_time_prefixes: tuple[str, ...],
    completion_elapsed_prefix: str,
    legacy_completion_time_prefix: str,
    is_hhmm_timestamp_fn: Callable[[str], bool],
) -> bool:
    for raw_line in reversed(str(content or "").splitlines()):
        line = str(raw_line or "").strip()
        if not line:
            continue
        for prefix in completion_time_prefixes:
            if not line.startswith(prefix):
                continue
            payload = line[len(prefix) :].strip()
            parts = payload.split()
            if len(parts) == 2:
                timestamp_text, elapsed_text = parts
            elif len(parts) == 3 and parts[1] in {completion_elapsed_prefix, "⌛️", "⏱", "⏱️"}:
                timestamp_text, elapsed_text = parts[0], parts[2]
            else:
                return False
            if not is_hhmm_timestamp_fn(timestamp_text):
                return False
            elapsed_unit = elapsed_text[-1:] if elapsed_text else ""
            elapsed_value = elapsed_text[:-1]
            return elapsed_unit in {"m", "s"} and elapsed_value.isdigit()
        if line.startswith("Done "):
            payload = line[len("Done ") :].strip()
            timestamp_text, separator, elapsed_payload = payload.partition(",")
            elapsed_text = elapsed_payload.strip()
            if not separator or not elapsed_text.startswith("took "):
                return False
            elapsed_value = elapsed_text[len("took ") :].strip()
            elapsed_unit = elapsed_value[-1:] if elapsed_value else ""
            return (
                is_hhmm_timestamp_fn(timestamp_text.strip())
                and elapsed_unit in {"m", "s"}
                and elapsed_value[:-1].isdigit()
            )
        if line.startswith("完成"):
            payload = line[len("完成") :].strip()
            timestamp_text, separator, elapsed_text = payload.partition("，用时")
            if separator:
                elapsed_unit = elapsed_text[-1:] if elapsed_text else ""
                return (
                    is_hhmm_timestamp_fn(timestamp_text.strip())
                    and elapsed_unit in {"m", "s"}
                    and elapsed_text[:-1].isdigit()
                )
        if not line.startswith(legacy_completion_time_prefix):
            return False
        timestamp_text = line[len(legacy_completion_time_prefix) :].strip()
        return is_hhmm_timestamp_fn(timestamp_text)
    return False


def is_hhmm_timestamp(timestamp_text: str) -> bool:
    if len(timestamp_text) != 5:
        return False
    hour_text, sep, minute_text = timestamp_text.partition(":")
    return bool(
        sep == ":"
        and hour_text.isdigit()
        and minute_text.isdigit()
        and 0 <= int(hour_text) <= 23
        and 0 <= int(minute_text) <= 59
    )


def completion_elapsed_seconds(started_at: float | None, *, now_monotonic: float) -> int:
    if started_at is None:
        return 0
    return int(max(0.0, now_monotonic - float(started_at)))


def completion_elapsed_text(elapsed_seconds: int) -> str:
    if elapsed_seconds < 60:
        return f"{elapsed_seconds}s"
    return f"{elapsed_seconds // 60}m"


def completion_time_text(now: datetime) -> str:
    return now.strftime("%H:%M")

from __future__ import annotations

import os

_DEFAULT_OPENAI_STREAM_MAX_RETRIES = 5


def openai_stream_max_retries() -> int:
    raw_value = str(os.getenv("AGENTHUB_OPENAI_STREAM_MAX_RETRIES", "") or "").strip()
    if not raw_value:
        return _DEFAULT_OPENAI_STREAM_MAX_RETRIES
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        return _DEFAULT_OPENAI_STREAM_MAX_RETRIES
    return min(max(parsed, 0), 8)

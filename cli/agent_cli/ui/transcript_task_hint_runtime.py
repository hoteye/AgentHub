from __future__ import annotations

import re

_DEFAULT_THREAD_NAME_RE = re.compile(r"^Thread \d{4}-\d{2}-\d{2}\b", re.IGNORECASE)


def resolve_transcript_task_hint(
    runtime_thread_name: str | None,
    top_title_text: str | None,
    base_title: str | None,
) -> str:
    normalized_base = str(base_title or "").strip()
    for candidate in (runtime_thread_name, top_title_text):
        normalized = str(candidate or "").strip()
        if not normalized:
            continue
        if normalized_base and normalized == normalized_base:
            continue
        if _DEFAULT_THREAD_NAME_RE.match(normalized):
            continue
        return normalized
    return normalized_base

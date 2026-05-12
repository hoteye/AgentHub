from __future__ import annotations

import re
from typing import Callable


_WHITESPACE_RE = re.compile(r"\s+")
_SENTENCE_SPLIT_RE = re.compile(r"[。！？!?;；]")
_LEADING_PREFIX_RE = re.compile(
    r"^(?:请帮我|请你|请问|请|帮我|麻烦你|麻烦|我想要|我想|我要|我希望|我需要|please|can you|help me)[\s,:，：]*",
    re.IGNORECASE,
)


def normalized_prompt_text(value: str) -> str:
    text = str(value or "").replace("\u3000", " ")
    return _WHITESPACE_RE.sub(" ", text).strip()


def is_slash_command_prompt(value: str) -> bool:
    return normalized_prompt_text(value).startswith("/")


def should_update_title_from_prompt(value: str) -> bool:
    normalized = normalized_prompt_text(value)
    if not normalized:
        return False
    return not is_slash_command_prompt(normalized)


def strip_leading_prompt_prefix(value: str) -> str:
    normalized = normalized_prompt_text(value)
    if not normalized:
        return ""
    return _LEADING_PREFIX_RE.sub("", normalized, count=1).strip()


def condensed_prompt_intent(value: str) -> str:
    stripped = strip_leading_prompt_prefix(value)
    if not stripped:
        return ""
    parts = _SENTENCE_SPLIT_RE.split(stripped, maxsplit=1)
    summary = str((parts[0] if parts else stripped) or stripped).strip()
    return summary


def top_title_text_for_prompt(
    prompt: str,
    *,
    base_title: str,
    width: int,
    crop_one_line_fn: Callable[[str, int], str],
) -> str:
    summary = condensed_prompt_intent(prompt)
    if not summary:
        return str(base_title or "")
    return crop_one_line_fn(summary, max(1, int(width)))


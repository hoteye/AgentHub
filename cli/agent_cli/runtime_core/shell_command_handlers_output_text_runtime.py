"""Output text processing helpers for shell command handlers.

Handles token budgeting, middle-truncation, chunk identification, and
formatted exec output construction.  Extracted from
``shell_command_handlers_runtime`` to keep the public handler module
focused on orchestration.
"""

from __future__ import annotations

import hashlib
from typing import Any

_DEFAULT_MAX_OUTPUT_TOKENS = 10000
_APPROX_BYTES_PER_TOKEN = 4


def approx_token_count(text: Any) -> int:
    length = len(str(text or "").encode("utf-8", errors="replace"))
    if length <= 0:
        return 0
    return (length + _APPROX_BYTES_PER_TOKEN - 1) // _APPROX_BYTES_PER_TOKEN


def approx_tokens_from_length(length: Any) -> int | None:
    normalized = _positive_int(length)
    if normalized is None:
        return None
    return (normalized + _APPROX_BYTES_PER_TOKEN - 1) // _APPROX_BYTES_PER_TOKEN


def max_output_chars_for_tokens(max_output_tokens: Any) -> int:
    tokens = _positive_int(max_output_tokens) or _DEFAULT_MAX_OUTPUT_TOKENS
    return tokens * _APPROX_BYTES_PER_TOKEN


def _positive_int(value: Any) -> int | None:
    try:
        normalized = int(float(value))
    except (TypeError, ValueError):
        return None
    return normalized if normalized > 0 else None


def exec_output_text(payload: dict[str, Any]) -> str:
    for key in ("aggregated_output", "stdout", "stderr"):
        value = payload.get(key)
        if value is not None:
            return str(value or "")
    return ""


def chunk_id(payload: dict[str, Any], output_text: str) -> str:
    chunk_id = str(payload.get("chunk_id") or "").strip()
    if chunk_id:
        return chunk_id
    call_id = str(payload.get("provider_call_id") or payload.get("call_id") or "").strip()
    if call_id:
        return hashlib.sha1(call_id.encode("utf-8", errors="replace")).hexdigest()[:6]
    seed = "\n".join(
        [
            str(payload.get("command") or ""),
            str(payload.get("process_id") or payload.get("session_id") or ""),
            str(payload.get("duration_ms") or ""),
            output_text[:4096],
        ]
    )
    return hashlib.sha1(seed.encode("utf-8", errors="replace")).hexdigest()[:6]


def truncate_middle_by_tokens(text: str, max_tokens: int) -> tuple[str, bool, int]:
    raw = str(text or "")
    original_tokens = approx_token_count(raw)
    if not raw:
        return "", False, original_tokens
    byte_budget = max(0, int(max_tokens)) * _APPROX_BYTES_PER_TOKEN
    raw_bytes = raw.encode("utf-8", errors="replace")
    if byte_budget > 0 and len(raw_bytes) <= byte_budget:
        return raw, False, original_tokens
    if byte_budget <= 0:
        omitted = original_tokens
        return f"…{omitted} tokens truncated…", True, original_tokens
    left_budget = byte_budget // 2
    right_budget = byte_budget - left_budget
    left = _prefix_for_byte_budget(raw, left_budget)
    right = _suffix_for_byte_budget(raw, right_budget)
    kept_tokens = approx_token_count(left) + approx_token_count(right)
    omitted_tokens = max(1, original_tokens - kept_tokens)
    return f"{left}…{omitted_tokens} tokens truncated…{right}", True, original_tokens


def _prefix_for_byte_budget(text: str, byte_budget: int) -> str:
    if byte_budget <= 0:
        return ""
    total = 0
    chars: list[str] = []
    for char in text:
        char_len = len(char.encode("utf-8", errors="replace"))
        if total + char_len > byte_budget:
            break
        chars.append(char)
        total += char_len
    return "".join(chars)


def _suffix_for_byte_budget(text: str, byte_budget: int) -> str:
    if byte_budget <= 0:
        return ""
    total = 0
    chars: list[str] = []
    for char in reversed(text):
        char_len = len(char.encode("utf-8", errors="replace"))
        if total + char_len > byte_budget:
            break
        chars.append(char)
        total += char_len
    return "".join(reversed(chars))


def total_output_lines(payload: dict[str, Any], output_text: str) -> int | None:
    for key in (
        "aggregated_output_total_lines",
        "output_total_lines",
        "stdout_total_lines",
        "stderr_total_lines",
    ):
        value = _positive_int(payload.get(key))
        if value is not None:
            return value
    if bool(
        payload.get("aggregated_output_truncated")
        or payload.get("stdout_truncated")
        or payload.get("stderr_truncated")
    ):
        return len(str(output_text or "").splitlines())
    return None


def formatted_exec_output(payload: dict[str, Any], output_text: str) -> tuple[str, int | None]:
    max_tokens = _positive_int(payload.get("max_output_tokens")) or _DEFAULT_MAX_OUTPUT_TOKENS
    formatted, truncated, original_tokens = truncate_middle_by_tokens(output_text, max_tokens)
    total_char_tokens = (
        approx_tokens_from_length(payload.get("aggregated_output_total_chars"))
        or approx_tokens_from_length(payload.get("output_total_chars"))
        or approx_tokens_from_length(payload.get("stdout_total_chars"))
        or approx_tokens_from_length(payload.get("stderr_total_chars"))
    )
    if total_char_tokens is not None:
        original_tokens = max(original_tokens, total_char_tokens)
    if not truncated and _positive_int(payload.get("original_token_count")) is None:
        original_token_count: int | None = original_tokens
    else:
        original_token_count = _positive_int(payload.get("original_token_count")) or original_tokens
    if truncated:
        total_lines = total_output_lines(payload, output_text) or len(
            str(output_text or "").splitlines()
        )
        formatted = f"Total output lines: {total_lines}\n\n{formatted}"
    elif bool(
        payload.get("aggregated_output_truncated")
        or payload.get("stdout_truncated")
        or payload.get("stderr_truncated")
    ):
        tl = total_output_lines(payload, output_text)
        if tl is not None and not formatted.startswith("Total output lines: "):
            formatted = f"Total output lines: {tl}\n\n{formatted}"
    return formatted, original_token_count

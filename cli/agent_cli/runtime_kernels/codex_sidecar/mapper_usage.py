from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_kernels.codex_sidecar.mapper_normalization import (
    _field,
    _mapping,
)


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _int_field(payload: dict[str, Any], *names: str) -> int:
    return _int_value(_field(payload, *names))


def _normalize_usage(value: Any) -> dict[str, int]:
    raw = _mapping(value)
    if not raw:
        return {}

    def _int(item: Any) -> int:
        try:
            return max(0, int(item))
        except (TypeError, ValueError):
            return 0

    input_tokens = _int(_field(raw, "input_tokens", "inputTokens"))
    cached_input_tokens = _int(_field(raw, "cached_input_tokens", "cachedInputTokens"))
    output_tokens = _int(_field(raw, "output_tokens", "outputTokens"))
    reasoning_output_tokens = _int(_field(raw, "reasoning_output_tokens", "reasoningOutputTokens"))
    total_tokens = _int(_field(raw, "total_tokens", "totalTokens")) or (
        input_tokens + output_tokens
    )
    if not any(
        (
            input_tokens,
            cached_input_tokens,
            output_tokens,
            reasoning_output_tokens,
            total_tokens,
        )
    ):
        return {}
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "reasoning_output_tokens": reasoning_output_tokens,
        "total_tokens": total_tokens,
    }

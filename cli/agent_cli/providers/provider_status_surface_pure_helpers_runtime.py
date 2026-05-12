from __future__ import annotations

from typing import Any


_SOFT_FAILURE_CODES = frozenset(
    {
        "rate_limited",
        "timeout",
        "timed_out",
        "server_error",
        "service_unavailable",
        "temporary_unavailable",
        "network_error",
        "proxy_unavailable",
        "bad_gateway",
        "gateway_timeout",
    }
)
_HARD_FAILURE_CODES = frozenset(
    {
        "invalid_api_key",
        "unauthorized",
        "forbidden",
        "subscription_expired",
        "quota_exhausted",
        "insufficient_quota",
        "billing_required",
        "model_not_allowed",
        "auth_not_ready",
        "auth_missing_api_key",
        "auth_guardrail_blocked",
    }
)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _boolish(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    normalized = _normalized_text(value)
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def failure_code_is_soft(value: Any) -> bool:
    return _normalized_text(value) in _SOFT_FAILURE_CODES


def failure_code_is_hard(value: Any) -> bool:
    return _normalized_text(value) in _HARD_FAILURE_CODES


__all__ = [
    "_HARD_FAILURE_CODES",
    "_SOFT_FAILURE_CODES",
    "_boolish",
    "_normalized_text",
    "failure_code_is_hard",
    "failure_code_is_soft",
]

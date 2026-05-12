from __future__ import annotations

import os
import platform
import random
import time
from collections.abc import Callable
from typing import TypeVar

from cli.agent_cli import __version__ as _AGENTHUB_VERSION
from cli.agent_cli.debug_timeline import log_timeline, timeline_debug_enabled
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.error_diagnostics_runtime import (
    normalized_error_text,
    provider_error_status_code,
)

_REFERENCE_COMPAT_ORIGINATOR = "reference_cli_rs"
_CODEX_COMPAT_ORIGINATOR = "codex_exec"
_RETRYABLE_ERROR_MARKERS = (
    "proxy_unavailable",
    "all accounts are currently unavailable",
    "rate limit",
    "too many requests",
    "server overloaded",
    "overloaded_error",
    "temporarily unavailable",
    "temporarily overloaded",
    "network_error",
    "connection error",
    "connection reset",
    "connection aborted",
    "connection refused",
    "remoteprotocolerror",
    "stream closed before response.completed",
    "timed out",
    "timeout",
    "error code: 429",
    "error code: 500",
    "error code: 502",
    "error code: 503",
    "error code: 504",
    "error code: 529",
)
_PROVIDER_RETRY_ATTEMPTS = 5
_PROVIDER_RETRY_BASE_DELAY_SECONDS = 0.5
_PROVIDER_RETRY_MAX_DELAY_SECONDS = 4.0
_PROVIDER_RETRY_ATTEMPTS_DEFAULT = 4
_PROVIDER_RETRY_BASE_DELAY_SECONDS_DEFAULT = 0.5
_PROVIDER_RETRY_MAX_DELAY_SECONDS_DEFAULT = 4.0
_RetryResult = TypeVar("_RetryResult")


def _compat_originator(config: ProviderConfig) -> str:
    if str(getattr(config, "interaction_profile", "") or "").strip() == "codex_openai":
        return _CODEX_COMPAT_ORIGINATOR
    return _REFERENCE_COMPAT_ORIGINATOR


def _compat_user_agent(originator: str) -> str:
    system = platform.system() or "Unknown"
    release = platform.release() or "unknown"
    machine = platform.machine() or "unknown"
    return f"{originator}/{_AGENTHUB_VERSION} ({system} {release}; {machine}) AgentHubCLI"


def _reference_compat_headers(config: ProviderConfig) -> dict[str, str]:
    originator = _compat_originator(config)
    return {
        "originator": originator,
        "User-Agent": _compat_user_agent(originator),
    }


def _expected_api_key_env_name(config: ProviderConfig) -> str:
    auth = getattr(config, "auth", None)
    auth_mapping = auth if isinstance(auth, dict) else {}
    raw_provider = getattr(config, "raw_provider", None)
    provider_mapping = raw_provider if isinstance(raw_provider, dict) else {}
    candidates = (
        auth_mapping.get("env_var"),
        auth_mapping.get("api_key_env"),
        provider_mapping.get("api_key_env"),
        provider_mapping.get("auth_key_name"),
    )
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value:
            return value
    return ""


def _validate_openai_client_auth(config: ProviderConfig) -> None:
    auth_mode = str(getattr(config, "auth_mode", "") or "").strip().lower() or "api_key"
    if auth_mode == "none":
        return
    if str(getattr(config, "api_key", "") or "").strip():
        return
    provider_name = str(getattr(config, "provider_name", "") or "").strip() or "provider"
    expected_env = _expected_api_key_env_name(config)
    if expected_env:
        raise ValueError(
            f"missing API credential for provider `{provider_name}`; expected `{expected_env}`"
        )
    raise ValueError(f"missing API credential for provider `{provider_name}`")


def is_retryable_provider_error(exc: Exception) -> bool:
    try:
        from openai import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError

        if isinstance(
            exc, APIConnectionError | APITimeoutError | InternalServerError | RateLimitError
        ):
            return True
    except Exception:
        pass

    status_code = provider_error_status_code(exc)
    if status_code in {429, 500, 502, 503, 504, 529}:
        return True

    text = normalized_error_text(exc)
    if not text:
        return False
    return any(marker in text for marker in _RETRYABLE_ERROR_MARKERS)


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw_value = str(os.getenv(name, "") or "").strip()
    if not raw_value:
        return default
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, minimum), maximum)


def _env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw_value = str(os.getenv(name, "") or "").strip()
    if not raw_value:
        return default
    try:
        parsed = float(raw_value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, minimum), maximum)


def provider_retry_attempts() -> int:
    return _env_int(
        "AGENTHUB_PROVIDER_RETRY_ATTEMPTS",
        _PROVIDER_RETRY_ATTEMPTS_DEFAULT,
        minimum=1,
        maximum=8,
    )


def provider_retry_base_delay_seconds() -> float:
    return _env_float(
        "AGENTHUB_PROVIDER_RETRY_BASE_DELAY_SECONDS",
        _PROVIDER_RETRY_BASE_DELAY_SECONDS_DEFAULT,
        minimum=0.0,
        maximum=5.0,
    )


def provider_retry_max_delay_seconds() -> float:
    return _env_float(
        "AGENTHUB_PROVIDER_RETRY_MAX_DELAY_SECONDS",
        _PROVIDER_RETRY_MAX_DELAY_SECONDS_DEFAULT,
        minimum=0.0,
        maximum=10.0,
    )


def call_with_provider_retries(
    request_fn: Callable[[], _RetryResult],
    *,
    attempts: int = _PROVIDER_RETRY_ATTEMPTS,
    base_delay_seconds: float = _PROVIDER_RETRY_BASE_DELAY_SECONDS,
    max_delay_seconds: float = _PROVIDER_RETRY_MAX_DELAY_SECONDS,
) -> _RetryResult:
    effective_attempts = int(attempts)
    effective_base_delay_seconds = float(base_delay_seconds)
    effective_max_delay_seconds = float(max_delay_seconds)
    if effective_attempts == _PROVIDER_RETRY_ATTEMPTS:
        effective_attempts = provider_retry_attempts()
    if effective_base_delay_seconds == _PROVIDER_RETRY_BASE_DELAY_SECONDS:
        effective_base_delay_seconds = provider_retry_base_delay_seconds()
    if effective_max_delay_seconds == _PROVIDER_RETRY_MAX_DELAY_SECONDS:
        effective_max_delay_seconds = provider_retry_max_delay_seconds()
    max_attempts = max(1, effective_attempts)
    delay = max(0.0, effective_base_delay_seconds)
    max_delay = max(0.0, effective_max_delay_seconds)
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        if timeline_debug_enabled():
            log_timeline(
                "provider.retry.attempt",
                attempt=attempt,
                max_attempts=max_attempts,
                base_delay_seconds=delay,
                max_delay_seconds=max_delay,
            )
        try:
            result = request_fn()
            if timeline_debug_enabled():
                log_timeline(
                    "provider.retry.success",
                    attempt=attempt,
                    max_attempts=max_attempts,
                )
            return result
        except Exception as exc:
            last_error = exc
            retryable = is_retryable_provider_error(exc)
            if timeline_debug_enabled():
                log_timeline(
                    "provider.retry.error",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    retryable=retryable,
                    error_type=type(exc).__name__,
                    error_text=str(exc),
                )
            if attempt >= max_attempts or not retryable:
                if timeline_debug_enabled():
                    log_timeline(
                        "provider.retry.giveup",
                        attempt=attempt,
                        max_attempts=max_attempts,
                        error_type=type(exc).__name__,
                        error_text=str(exc),
                    )
                raise
            sleep_seconds = min(max_delay, delay * (2 ** (attempt - 1)))
            sleep_seconds += random.uniform(0.0, min(0.25, sleep_seconds * 0.2))
            if timeline_debug_enabled():
                log_timeline(
                    "provider.retry.sleep",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    sleep_seconds=round(sleep_seconds, 3),
                )
            time.sleep(sleep_seconds)
    if last_error is not None:
        raise last_error
    raise RuntimeError("provider retry loop exited without a result")


def build_openai_client(
    config: ProviderConfig,
    *,
    fallback_base_url: str | None = None,
):
    from openai import OpenAI

    _validate_openai_client_auth(config)
    base_url = config.base_url or fallback_base_url
    return OpenAI(
        api_key=config.api_key,
        base_url=base_url,
        max_retries=0,
        default_headers=_reference_compat_headers(config),
    )

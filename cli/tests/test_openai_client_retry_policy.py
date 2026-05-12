from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from cli.agent_cli.providers.openai_client import call_with_provider_retries, is_retryable_provider_error


def _retryable_provider_error() -> RuntimeError:
    return RuntimeError(
        "InternalServerError: Error code: 503 - "
        "{'error': {'type': 'proxy_unavailable', 'message': 'All accounts are currently unavailable.'}}"
    )


def test_call_with_provider_retries_uses_fast_default_attempt_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENTHUB_PROVIDER_RETRY_ATTEMPTS", raising=False)
    monkeypatch.delenv("AGENTHUB_PROVIDER_RETRY_BASE_DELAY_SECONDS", raising=False)
    monkeypatch.delenv("AGENTHUB_PROVIDER_RETRY_MAX_DELAY_SECONDS", raising=False)
    attempt_counter = {"count": 0}

    def _request_once():
        attempt_counter["count"] += 1
        raise _retryable_provider_error()

    with patch("cli.agent_cli.providers.openai_client.time.sleep", return_value=None):
        with patch("cli.agent_cli.providers.openai_client.random.uniform", return_value=0.0):
            with pytest.raises(RuntimeError):
                call_with_provider_retries(_request_once)

    assert attempt_counter["count"] == 4


def test_call_with_provider_retries_honors_env_attempt_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTHUB_PROVIDER_RETRY_ATTEMPTS", "3")
    attempt_counter = {"count": 0}

    def _request_once():
        attempt_counter["count"] += 1
        raise _retryable_provider_error()

    with patch("cli.agent_cli.providers.openai_client.time.sleep", return_value=None):
        with patch("cli.agent_cli.providers.openai_client.random.uniform", return_value=0.0):
            with pytest.raises(RuntimeError):
                call_with_provider_retries(_request_once)

    assert attempt_counter["count"] == 3


def test_call_with_provider_retries_explicit_attempts_override_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTHUB_PROVIDER_RETRY_ATTEMPTS", "6")
    attempt_counter = {"count": 0}

    def _request_once():
        attempt_counter["count"] += 1
        raise _retryable_provider_error()

    with patch("cli.agent_cli.providers.openai_client.time.sleep", return_value=None):
        with patch("cli.agent_cli.providers.openai_client.random.uniform", return_value=0.0):
            with pytest.raises(RuntimeError):
                call_with_provider_retries(_request_once, attempts=4, base_delay_seconds=0.0)

    assert attempt_counter["count"] == 4


def test_stream_closed_before_response_completed_is_retryable() -> None:
    assert is_retryable_provider_error(RuntimeError("stream closed before response.completed")) is True


def test_status_code_529_is_retryable_even_without_text_markers() -> None:
    exc = RuntimeError("overloaded")
    exc.status_code = 529
    assert is_retryable_provider_error(exc) is True


def test_response_status_code_429_is_retryable() -> None:
    exc = RuntimeError("rate limited")
    exc.response = SimpleNamespace(status_code=429)
    assert is_retryable_provider_error(exc) is True

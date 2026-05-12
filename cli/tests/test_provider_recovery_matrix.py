from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from cli.agent_cli.providers.adapters.openai_responses_error_runtime import (
    call_with_responses_503_diagnostics,
)
from cli.agent_cli.providers.anthropic_claude import AnthropicMessagesSession


class _ProviderError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _anthropic_text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


@pytest.mark.parametrize(
    ("error", "expected_classification", "expected_retryable"),
    [
        (_ProviderError("connection reset by peer"), "connection_error", True),
        (_ProviderError("provider returned malformed content: invalid json"), "malformed_content", False),
        (_ProviderError("invalid_request_error: malformed tool schema"), "malformed_content", False),
        (_ProviderError("image too large for request", status_code=413), "media_size_exceeded", False),
        (_ProviderError("stream idle timeout before response.completed"), "connection_error", True),
    ],
)
def test_openai_recovery_matrix_attaches_expected_diagnostics(
    error: Exception,
    expected_classification: str,
    expected_retryable: bool,
) -> None:
    with patch("cli.agent_cli.providers.openai_client.time.sleep", return_value=None):
        with patch("cli.agent_cli.providers.openai_client.random.uniform", return_value=0.0):
            with pytest.raises(Exception) as exc_info:
                call_with_responses_503_diagnostics(
                    lambda: (_ for _ in ()).throw(error),
                    payload={"input": [{"role": "user", "content": "hello"}]},
                    source="responses.send",
                )

    diagnostics = dict(getattr(exc_info.value, "agenthub_provider_diagnostics", {}) or {})
    assert diagnostics["provider_family"] == "openai"
    assert diagnostics["source"] == "responses.send"
    assert diagnostics["classification"] == expected_classification
    assert diagnostics["retryable"] is expected_retryable


def test_anthropic_recovery_matrix_retries_connection_reset_and_recovers() -> None:
    attempts = {"count": 0}

    def _create(**kwargs):
        del kwargs
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise _ProviderError("connection reset by peer")
        return SimpleNamespace(id="msg_ok", content=[_anthropic_text_block("recovered")])

    session = AnthropicMessagesSession(
        client=SimpleNamespace(messages=SimpleNamespace(create=_create)),
        model="claude-sonnet-4-6",
        system_prompt="You are AgentHub.",
        tool_specs=[],
        supports_tools=False,
        max_tokens=2048,
        create_fn=_create,
    )

    with patch("cli.agent_cli.providers.openai_client.time.sleep", return_value=None):
        with patch("cli.agent_cli.providers.openai_client.random.uniform", return_value=0.0):
            result = session.send(
                input_items=[
                    {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "hello"}],
                    }
                ],
                allow_tools=False,
            )

    assert attempts["count"] == 2
    assert result.output_text == "recovered"


@pytest.mark.parametrize(
    ("error", "expected_classification"),
    [
        (_ProviderError("provider returned malformed content: invalid json"), "malformed_content"),
        (_ProviderError("image too large for request", status_code=413), "media_size_exceeded"),
    ],
)
def test_anthropic_recovery_matrix_fail_closed_for_non_retryable_errors(
    error: Exception,
    expected_classification: str,
) -> None:
    def _create(**kwargs):
        del kwargs
        raise error

    session = AnthropicMessagesSession(
        client=SimpleNamespace(messages=SimpleNamespace(create=_create)),
        model="claude-sonnet-4-6",
        system_prompt="You are AgentHub.",
        tool_specs=[],
        supports_tools=False,
        max_tokens=2048,
        create_fn=_create,
    )

    with patch("cli.agent_cli.providers.openai_client.time.sleep", return_value=None):
        with patch("cli.agent_cli.providers.openai_client.random.uniform", return_value=0.0):
            with pytest.raises(Exception) as exc_info:
                session.send(
                    input_items=[
                        {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": "hello"}],
                        }
                    ],
                    allow_tools=False,
                )

    diagnostics = dict(getattr(exc_info.value, "agenthub_provider_diagnostics", {}) or {})
    assert diagnostics["provider_family"] == "anthropic"
    assert diagnostics["source"] == "anthropic.messages.create"
    assert diagnostics["classification"] == expected_classification
    assert diagnostics["retryable"] is False

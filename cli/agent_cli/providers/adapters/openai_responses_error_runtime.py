from __future__ import annotations

from typing import Any, Callable, Dict

from cli.agent_cli.providers.error_diagnostics_runtime import attach_provider_recovery_diagnostics
from cli.agent_cli.providers.openai_client import call_with_provider_retries, is_retryable_provider_error
from cli.agent_cli.providers.responses_503_diagnostics import attach_responses_503_risks

_OPENAI_CONNECTION_ERROR_MARKERS = (
    "stream idle timeout",
    "stream closed before response.completed",
)

_OPENAI_MALFORMED_CONTENT_MARKERS = (
    "invalid_request_error",
)


def _attach_openai_recovery_diagnostics(
    exc: Exception,
    *,
    source: str,
) -> None:
    attach_provider_recovery_diagnostics(
        exc,
        provider_family="openai",
        source=source,
        retryable=is_retryable_provider_error(exc),
        extra_connection_error_markers=_OPENAI_CONNECTION_ERROR_MARKERS,
        extra_malformed_content_markers=_OPENAI_MALFORMED_CONTENT_MARKERS,
    )


def call_with_responses_503_diagnostics(
    request_once: Callable[[], Any],
    *,
    payload: Dict[str, Any],
    source: str,
) -> Any:
    try:
        return call_with_provider_retries(request_once)
    except Exception as exc:
        attach_responses_503_risks(exc, payload, source=source)
        _attach_openai_recovery_diagnostics(exc, source=source)
        raise

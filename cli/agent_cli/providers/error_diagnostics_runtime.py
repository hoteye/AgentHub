from __future__ import annotations

from typing import Any, Iterable

CONNECTION_ERROR_MARKERS = (
    "connection reset",
    "connection aborted",
    "connection refused",
    "connection error",
    "remoteprotocolerror",
    "network error",
    "timed out",
    "timeout",
)
MEDIA_SIZE_MARKERS = (
    "payload too large",
    "request entity too large",
    "image too large",
    "file too large",
    "media too large",
    "maximum image size",
    "maximum file size",
)
MALFORMED_CONTENT_MARKERS = (
    "malformed",
    "invalid json",
    "response validation",
    "schema validation",
    "could not parse",
    "parse error",
)
PROMPT_TOO_LONG_MARKERS = (
    "prompt is too long",
    "context window",
    "too many tokens",
    "context_length_exceeded",
)


def provider_error_status_code(exc: Exception) -> int | None:
    candidates = (
        getattr(exc, "status_code", None),
        getattr(exc, "status", None),
        getattr(getattr(exc, "response", None), "status_code", None),
    )
    for candidate in candidates:
        try:
            if candidate is None or str(candidate).strip() == "":
                continue
            return int(candidate)
        except (TypeError, ValueError):
            continue
    return None


def normalized_error_text(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}".strip().lower()


def contains_any(text: str, markers: Iterable[str]) -> bool:
    return any(str(marker) in text for marker in markers)


def classify_provider_error(
    exc: Exception,
    *,
    retryable: bool,
    extra_connection_error_markers: Iterable[str] = (),
    extra_malformed_content_markers: Iterable[str] = (),
) -> dict[str, Any]:
    status_code = provider_error_status_code(exc)
    error_text = normalized_error_text(exc)
    connection_error_markers = tuple(CONNECTION_ERROR_MARKERS) + tuple(extra_connection_error_markers)
    malformed_content_markers = tuple(MALFORMED_CONTENT_MARKERS) + tuple(extra_malformed_content_markers)
    classification = "provider_error"
    normalized_retryable = bool(retryable)
    if status_code == 413 or contains_any(error_text, MEDIA_SIZE_MARKERS):
        classification = "media_size_exceeded"
        normalized_retryable = False
    elif contains_any(error_text, malformed_content_markers):
        classification = "malformed_content"
        normalized_retryable = False
    elif contains_any(error_text, PROMPT_TOO_LONG_MARKERS):
        classification = "prompt_too_long"
        normalized_retryable = False
    elif contains_any(error_text, connection_error_markers):
        classification = "connection_error"
        normalized_retryable = True
    elif normalized_retryable:
        classification = "provider_unavailable"
    return {
        "status_code": status_code,
        "error_text": error_text,
        "classification": classification,
        "retryable": normalized_retryable,
    }


def attach_provider_recovery_diagnostics(
    exc: Exception,
    *,
    provider_family: str,
    source: str,
    retryable: bool,
    extra_connection_error_markers: Iterable[str] = (),
    extra_malformed_content_markers: Iterable[str] = (),
) -> None:
    diagnostics = dict(getattr(exc, "agenthub_provider_diagnostics", {}) or {})
    classification = classify_provider_error(
        exc,
        retryable=retryable,
        extra_connection_error_markers=extra_connection_error_markers,
        extra_malformed_content_markers=extra_malformed_content_markers,
    )
    diagnostics.update(
        {
            "provider_family": str(provider_family or "").strip() or None,
            "source": str(source or "").strip() or None,
            "classification": classification["classification"],
            "retryable": bool(classification["retryable"]),
        }
    )
    if classification["status_code"] is not None:
        diagnostics["status_code"] = classification["status_code"]
    setattr(exc, "agenthub_provider_diagnostics", diagnostics)

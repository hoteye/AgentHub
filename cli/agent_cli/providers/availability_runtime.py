from __future__ import annotations

from datetime import timedelta
import re
from typing import Any

from cli.agent_cli.providers import availability_persistence_runtime
from cli.agent_cli.providers.availability_projection import get_availability_registry


_ERROR_CODE_PATTERN = re.compile(r"error code:\s*(\d+)", re.IGNORECASE)


def _registry_from_owner(owner: Any) -> Any | None:
    return get_availability_registry(owner)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _first_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return ""


def _first_number(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = payload.get(key)
        if value in (None, ""):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _planner_summary(planner: Any) -> dict[str, Any]:
    if planner is None:
        return {}
    public_summary = getattr(planner, "public_summary", None)
    if not callable(public_summary):
        return {}
    try:
        return _mapping(public_summary())
    except Exception:
        return {}


def _provider_and_model(planner: Any, diagnostics: dict[str, Any]) -> tuple[str, str]:
    summary = _planner_summary(planner)
    provider_name = _first_text(summary, "provider_name", "provider")
    model = _first_text(summary, "model", "provider_model", "model_key")
    if not provider_name:
        provider_name = _first_text(diagnostics, "provider_name", "provider")
    if not model:
        model = _first_text(diagnostics, "model", "provider_model", "model_key")
    return provider_name, model


def _failure_code(exc: Exception, diagnostics: dict[str, Any]) -> str:
    code = _first_text(
        diagnostics,
        "failure_code",
        "error_code",
        "code",
        "error_type",
        "type",
    )
    if code:
        return code
    error_text = f"{type(exc).__name__}: {exc}"
    matched = _ERROR_CODE_PATTERN.search(error_text)
    if matched:
        return f"http_{matched.group(1)}"
    lowered = error_text.lower()
    if "timeout" in lowered:
        return "timeout"
    if "rate limit" in lowered or "too many requests" in lowered or "429" in lowered:
        return "rate_limited"
    return type(exc).__name__.lower() or "provider_error"


def _failure_reason(exc: Exception, diagnostics: dict[str, Any]) -> str:
    reason = _first_text(diagnostics, "failure_reason", "reason", "error_message", "message")
    if reason:
        return reason
    return f"{type(exc).__name__}: {exc}"


def _retry_after(diagnostics: dict[str, Any]) -> timedelta | None:
    seconds = _first_number(diagnostics, "retry_after_seconds", "retry_after", "retry_after_sec")
    if seconds is not None:
        return timedelta(seconds=max(0.0, seconds))
    milliseconds = _first_number(diagnostics, "retry_after_ms", "retry_after_millis", "retry_after_milliseconds")
    if milliseconds is not None:
        return timedelta(milliseconds=max(0.0, milliseconds))
    return None


def _latency_ms(diagnostics: dict[str, Any]) -> int | None:
    direct_latency_ms = _first_number(
        diagnostics,
        "planner_elapsed_ms",
        "total_ms",
        "elapsed_ms",
        "request_elapsed_ms",
        "observed_elapsed_ms",
    )
    if direct_latency_ms is not None:
        return max(0, int(round(direct_latency_ms)))

    component_values = [
        _first_number(diagnostics, "initial_model_ms"),
        _first_number(diagnostics, "tool_execution_ms"),
        _first_number(diagnostics, "synthesis_model_ms"),
    ]
    component_numbers = [max(0.0, float(value)) for value in component_values if value is not None]
    if component_numbers:
        return int(round(sum(component_numbers)))

    fallback_latency_ms = _first_number(diagnostics, "model_ms")
    if fallback_latency_ms is not None:
        return max(0, int(round(fallback_latency_ms)))
    return None


def mark_provider_success(owner: Any, *, planner: Any, diagnostics: Any = None) -> None:
    registry = _registry_from_owner(owner)
    if registry is None:
        return
    diagnostics_payload = _mapping(diagnostics)
    provider_name, model = _provider_and_model(planner, diagnostics_payload)
    if not provider_name or not model:
        return
    mark_success = getattr(registry, "mark_success", None)
    if not callable(mark_success):
        return
    try:
        mark_success(
            provider_name=provider_name,
            model=model,
            latency_ms=_latency_ms(diagnostics_payload),
        )
    except Exception:
        return
    try:
        availability_persistence_runtime.persist_availability_registry_for_owner(owner)
    except Exception:
        return


def mark_provider_failure(
    owner: Any,
    *,
    planner: Any,
    exc: Exception,
    diagnostics: Any = None,
) -> None:
    registry = _registry_from_owner(owner)
    if registry is None:
        return
    diagnostics_payload = _mapping(diagnostics)
    provider_name, model = _provider_and_model(planner, diagnostics_payload)
    if not provider_name or not model:
        return
    mark_failure = getattr(registry, "mark_failure", None)
    if not callable(mark_failure):
        return
    try:
        mark_failure(
            provider_name=provider_name,
            model=model,
            failure_code=_failure_code(exc, diagnostics_payload),
            failure_reason=_failure_reason(exc, diagnostics_payload),
            retry_after=_retry_after(diagnostics_payload),
            latency_ms=_latency_ms(diagnostics_payload),
        )
    except Exception:
        return
    try:
        availability_persistence_runtime.persist_availability_registry_for_owner(owner)
    except Exception:
        return

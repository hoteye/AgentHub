from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict

from cli.agent_cli.providers.availability_models import (
    DEFAULT_PROVIDER_AVAILABILITY_STALE_AFTER_SECONDS,
    ProbeStatus,
    utc_now,
)


def get_availability_registry(owner: Any) -> Any | None:
    for attr_name in ("_provider_availability_registry", "provider_availability_registry"):
        registry = getattr(owner, attr_name, None)
        if registry is not None:
            return registry
    return None


def _datetime_value(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return ""
    return str(value)


def _integer_value(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def availability_surface_fields(
    registry: Any | None,
    *,
    provider_name: str,
    model: str,
    stale_after_seconds: int = DEFAULT_PROVIDER_AVAILABILITY_STALE_AFTER_SECONDS,
) -> Dict[str, Any]:
    if registry is None:
        return {}

    provider = str(provider_name or "").strip()
    model_name = str(model or "").strip()

    status_value = ProbeStatus.UNKNOWN.value
    checked_at_value = ""
    freshness = "unknown"
    stale = False
    age_seconds: int | None = None
    failure_code = ""
    failure_reason = ""
    retry_after_seconds: int | None = None
    last_success_at = ""
    last_failure_at = ""
    last_latency_ms: int | None = None
    avg_latency_ms: int | None = None
    latency_sample_count = 0
    success_count = 0
    failure_count = 0
    consecutive_failures = 0
    availability_known = False

    if provider and model_name:
        try:
            record = registry.get(provider, model_name) if callable(getattr(registry, "get", None)) else None
        except Exception:
            record = None

        if record is not None:
            raw_status = getattr(record, "status", ProbeStatus.UNKNOWN)
            status_value = raw_status.value if hasattr(raw_status, "value") else str(raw_status or ProbeStatus.UNKNOWN.value)
            checked_at = getattr(record, "checked_at", None)
            checked_at_value = _datetime_value(checked_at)
            if isinstance(checked_at, datetime):
                age_delta = utc_now() - checked_at
                age_seconds = max(0, int(age_delta.total_seconds()))
                stale = age_seconds > max(0, int(stale_after_seconds or DEFAULT_PROVIDER_AVAILABILITY_STALE_AFTER_SECONDS))
                freshness = "stale" if stale else "fresh"
            failure_code = str(getattr(record, "failure_code", "") or "")
            failure_reason = str(getattr(record, "failure_reason", "") or "")
            retry_after = getattr(record, "retry_after", None)
            if isinstance(retry_after, timedelta):
                retry_after_seconds = max(0, int(retry_after.total_seconds()))
            last_success_at = _datetime_value(getattr(record, "last_success_at", None))
            last_failure_at = _datetime_value(getattr(record, "last_failure_at", None))
            last_latency_ms = _integer_value(getattr(record, "last_latency_ms", None))
            avg_latency_ms = _integer_value(getattr(record, "avg_latency_ms", None))
            latency_sample_count = max(0, _integer_value(getattr(record, "latency_sample_count", 0)) or 0)
            success_count = max(0, _integer_value(getattr(record, "success_count", 0)) or 0)
            failure_count = max(0, _integer_value(getattr(record, "failure_count", 0)) or 0)
            consecutive_failures = max(0, _integer_value(getattr(record, "consecutive_failures", 0)) or 0)
        else:
            try:
                status = registry.status(provider, model_name) if callable(getattr(registry, "status", None)) else ProbeStatus.UNKNOWN
                status_value = status.value if hasattr(status, "value") else str(status or ProbeStatus.UNKNOWN.value)
            except Exception:
                status_value = ProbeStatus.UNKNOWN.value

    status_value = str(status_value or ProbeStatus.UNKNOWN.value).strip().lower() or ProbeStatus.UNKNOWN.value
    if status_value not in {ProbeStatus.AVAILABLE.value, ProbeStatus.UNAVAILABLE.value, ProbeStatus.UNKNOWN.value}:
        status_value = ProbeStatus.UNKNOWN.value
    availability_known = status_value != ProbeStatus.UNKNOWN.value
    health_bucket = "unknown"
    if status_value == ProbeStatus.AVAILABLE.value:
        health_bucket = "healthy"
    elif status_value == ProbeStatus.UNAVAILABLE.value:
        health_bucket = "degraded"

    summary_parts: list[str] = [
        f"status={status_value}",
        f"known={'true' if availability_known else 'false'}",
    ]
    if avg_latency_ms is not None:
        summary_parts.append(f"avg_latency_ms={avg_latency_ms}")
    if last_latency_ms is not None:
        summary_parts.append(f"last_latency_ms={last_latency_ms}")
    if failure_count > 0:
        summary_parts.append(f"failure_count={failure_count}")
    if consecutive_failures > 0:
        summary_parts.append(f"consecutive_failures={consecutive_failures}")
    if retry_after_seconds is not None:
        summary_parts.append(f"retry_after_seconds={retry_after_seconds}")
    if failure_code:
        summary_parts.append(f"failure_code={failure_code}")
    availability_summary = "; ".join(summary_parts)

    availability_payload = {
        "status": status_value,
        "known": availability_known,
        "health_bucket": health_bucket,
        "summary": availability_summary,
        "checked_at": checked_at_value,
        "snapshot_freshness": freshness,
        "stale": stale,
        "age_seconds": age_seconds,
        "stale_after_seconds": max(0, int(stale_after_seconds or DEFAULT_PROVIDER_AVAILABILITY_STALE_AFTER_SECONDS)),
        "failure_code": failure_code,
        "failure_reason": failure_reason,
        "retry_after_seconds": retry_after_seconds,
        "last_success_at": last_success_at,
        "last_failure_at": last_failure_at,
        "last_latency_ms": last_latency_ms,
        "avg_latency_ms": avg_latency_ms,
        "latency_sample_count": latency_sample_count,
        "success_count": success_count,
        "failure_count": failure_count,
        "consecutive_failures": consecutive_failures,
    }
    return {
        "availability_status": status_value,
        "availability_known": availability_known,
        "availability_health_bucket": health_bucket,
        "availability_summary": availability_summary,
        "availability_checked_at": checked_at_value,
        "availability_snapshot_freshness": freshness,
        "availability_stale": stale,
        "availability_age_seconds": age_seconds,
        "availability_stale_after_seconds": max(
            0,
            int(stale_after_seconds or DEFAULT_PROVIDER_AVAILABILITY_STALE_AFTER_SECONDS),
        ),
        "availability_failure_code": failure_code,
        "availability_failure_reason": failure_reason,
        "availability_retry_after_seconds": retry_after_seconds,
        "availability_last_success_at": last_success_at,
        "availability_last_failure_at": last_failure_at,
        "availability_last_latency_ms": last_latency_ms,
        "availability_avg_latency_ms": avg_latency_ms,
        "availability_latency_sample_count": latency_sample_count,
        "availability_success_count": success_count,
        "availability_failure_count": failure_count,
        "availability_consecutive_failures": consecutive_failures,
        "availability": availability_payload,
    }


def append_availability_surface(
    payload: Dict[str, Any],
    registry: Any | None,
    *,
    provider_name: str,
    model: str,
    stale_after_seconds: int = DEFAULT_PROVIDER_AVAILABILITY_STALE_AFTER_SECONDS,
) -> Dict[str, Any]:
    fields = availability_surface_fields(
        registry,
        provider_name=provider_name,
        model=model,
        stale_after_seconds=stale_after_seconds,
    )
    if fields:
        payload.update(fields)
    return payload

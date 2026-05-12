from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional
import re


DEFAULT_PROVIDER_AVAILABILITY_STALE_AFTER_SECONDS = 5 * 60 * 60


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProbeStatus(str, Enum):
    UNKNOWN = "unknown"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


_MODEL_TOKEN_RE = re.compile(r"[^a-z0-9]+")


def normalize_provider_name(provider_name: str) -> str:
    return str(provider_name or "").strip().lower()


def normalize_model_selector(model: str) -> str:
    return str(model or "").strip().lower()


def canonical_model_token(model: str) -> str:
    normalized = normalize_model_selector(model)
    return _MODEL_TOKEN_RE.sub("", normalized)


def _normalized_latency_ms(latency_ms: int | float | None) -> int | None:
    if latency_ms is None:
        return None
    try:
        value = int(round(float(latency_ms)))
    except (TypeError, ValueError):
        return None
    return max(0, value)


def _updated_latency_stats(
    *,
    previous_last_latency_ms: int | None,
    previous_avg_latency_ms: int | None,
    previous_latency_sample_count: int,
    latency_ms: int | float | None,
) -> tuple[int | None, int | None, int]:
    normalized_latency_ms = _normalized_latency_ms(latency_ms)
    if normalized_latency_ms is None:
        return previous_last_latency_ms, previous_avg_latency_ms, previous_latency_sample_count
    previous_count = max(0, int(previous_latency_sample_count or 0))
    next_count = previous_count + 1
    if previous_count > 0 and previous_avg_latency_ms is not None:
        weighted_total = (int(previous_avg_latency_ms) * previous_count) + normalized_latency_ms
        next_avg_latency_ms = int(round(weighted_total / next_count))
    else:
        next_avg_latency_ms = normalized_latency_ms
    return normalized_latency_ms, next_avg_latency_ms, next_count


@dataclass(slots=True)
class AvailabilityRecord:
    provider_name: str
    model: str
    status: ProbeStatus = ProbeStatus.UNKNOWN
    checked_at: datetime = field(default_factory=utc_now)
    failure_code: str = ""
    failure_reason: str = ""
    retry_after: Optional[timedelta] = None
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    last_latency_ms: Optional[int] = None
    avg_latency_ms: Optional[int] = None
    latency_sample_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    consecutive_failures: int = 0

    @property
    def known(self) -> bool:
        return self.status in {ProbeStatus.AVAILABLE, ProbeStatus.UNAVAILABLE}

    def with_success(
        self,
        *,
        checked_at: Optional[datetime] = None,
        latency_ms: int | float | None = None,
    ) -> "AvailabilityRecord":
        resolved_checked_at = checked_at or utc_now()
        next_last_latency_ms, next_avg_latency_ms, next_latency_sample_count = _updated_latency_stats(
            previous_last_latency_ms=self.last_latency_ms,
            previous_avg_latency_ms=self.avg_latency_ms,
            previous_latency_sample_count=self.latency_sample_count,
            latency_ms=latency_ms,
        )
        return AvailabilityRecord(
            provider_name=self.provider_name,
            model=self.model,
            status=ProbeStatus.AVAILABLE,
            checked_at=resolved_checked_at,
            failure_code="",
            failure_reason="",
            retry_after=None,
            last_success_at=resolved_checked_at,
            last_failure_at=self.last_failure_at,
            last_latency_ms=next_last_latency_ms,
            avg_latency_ms=next_avg_latency_ms,
            latency_sample_count=next_latency_sample_count,
            success_count=max(0, int(self.success_count or 0)) + 1,
            failure_count=max(0, int(self.failure_count or 0)),
            consecutive_failures=0,
        )

    def with_failure(
        self,
        *,
        failure_code: str,
        failure_reason: str,
        checked_at: Optional[datetime] = None,
        retry_after: Optional[timedelta] = None,
        latency_ms: int | float | None = None,
    ) -> "AvailabilityRecord":
        resolved_checked_at = checked_at or utc_now()
        next_last_latency_ms, next_avg_latency_ms, next_latency_sample_count = _updated_latency_stats(
            previous_last_latency_ms=self.last_latency_ms,
            previous_avg_latency_ms=self.avg_latency_ms,
            previous_latency_sample_count=self.latency_sample_count,
            latency_ms=latency_ms,
        )
        return AvailabilityRecord(
            provider_name=self.provider_name,
            model=self.model,
            status=ProbeStatus.UNAVAILABLE,
            checked_at=resolved_checked_at,
            failure_code=failure_code,
            failure_reason=failure_reason,
            retry_after=retry_after,
            last_success_at=self.last_success_at,
            last_failure_at=resolved_checked_at,
            last_latency_ms=next_last_latency_ms,
            avg_latency_ms=next_avg_latency_ms,
            latency_sample_count=next_latency_sample_count,
            success_count=max(0, int(self.success_count or 0)),
            failure_count=max(0, int(self.failure_count or 0)) + 1,
            consecutive_failures=max(0, int(self.consecutive_failures or 0)) + 1,
        )

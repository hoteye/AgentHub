from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Any, Dict, Mapping, Optional, Tuple

from cli.agent_cli.providers.availability_models import (
    AvailabilityRecord,
    ProbeStatus,
    canonical_model_token,
    normalize_model_selector,
    normalize_provider_name,
    utc_now,
)


RegistryKey = Tuple[str, str]


def _normalize_key(provider_name: str, model: str) -> RegistryKey:
    return (
        normalize_provider_name(provider_name),
        normalize_model_selector(model),
    )


def _same_model_identity(left: str, right: str) -> bool:
    if left == right:
        return True
    left_token = canonical_model_token(left)
    right_token = canonical_model_token(right)
    if not left_token or not right_token:
        return False
    return left_token == right_token


class AvailabilityRegistry:
    def __init__(self) -> None:
        self._records: Dict[RegistryKey, AvailabilityRecord] = {}
        self._lock = RLock()

    def get(self, provider_name: str, model: str) -> Optional[AvailabilityRecord]:
        key = _normalize_key(provider_name, model)
        with self._lock:
            record = self._records.get(key)
            if record is not None:
                return record
            provider_key, model_key = key
            if not provider_key or not model_key:
                return None
            for (candidate_provider, candidate_model), candidate_record in self._records.items():
                if candidate_provider != provider_key:
                    continue
                if _same_model_identity(candidate_model, model_key):
                    return candidate_record
            return None

    def _resolve_existing_key_locked(self, provider_name: str, model: str) -> RegistryKey:
        key = _normalize_key(provider_name, model)
        if key in self._records:
            return key
        provider_key, model_key = key
        if not provider_key or not model_key:
            return key
        for candidate_key in self._records:
            if candidate_key[0] != provider_key:
                continue
            if _same_model_identity(candidate_key[1], model_key):
                return candidate_key
        return key

    def set(self, record: AvailabilityRecord) -> AvailabilityRecord:
        with self._lock:
            key = self._resolve_existing_key_locked(record.provider_name, record.model)
            self._records[key] = record
            return record

    def mark_success(
        self,
        *,
        provider_name: str,
        model: str,
        checked_at: Optional[datetime] = None,
        latency_ms: int | float | None = None,
    ) -> AvailabilityRecord:
        with self._lock:
            key = self._resolve_existing_key_locked(provider_name, model)
            previous = self._records.get(key) or AvailabilityRecord(
                provider_name=provider_name,
                model=model,
            )
            next_record = previous.with_success(
                checked_at=checked_at,
                latency_ms=latency_ms,
            )
            self._records[key] = next_record
            return next_record

    def mark_failure(
        self,
        *,
        provider_name: str,
        model: str,
        failure_code: str,
        failure_reason: str,
        checked_at: Optional[datetime] = None,
        retry_after: Optional[timedelta] = None,
        latency_ms: int | float | None = None,
    ) -> AvailabilityRecord:
        with self._lock:
            key = self._resolve_existing_key_locked(provider_name, model)
            previous = self._records.get(key) or AvailabilityRecord(
                provider_name=provider_name,
                model=model,
            )
            next_record = previous.with_failure(
                failure_code=failure_code,
                failure_reason=failure_reason,
                checked_at=checked_at,
                retry_after=retry_after,
                latency_ms=latency_ms,
            )
            self._records[key] = next_record
            return next_record

    def is_stale(
        self,
        provider_name: str,
        model: str,
        *,
        ttl: timedelta,
        now: Optional[datetime] = None,
    ) -> bool:
        record = self.get(provider_name, model)
        if record is None:
            return True
        check_now = now or utc_now()
        return (check_now - record.checked_at) > ttl

    def status(self, provider_name: str, model: str) -> ProbeStatus:
        record = self.get(provider_name, model)
        if record is None:
            return ProbeStatus.UNKNOWN
        return record.status

    def to_payload(self) -> dict[str, Any]:
        with self._lock:
            records = [
                _record_to_payload(record)
                for _key, record in sorted(self._records.items(), key=lambda item: item[0])
            ]
        return {
            "version": 1,
            "records": records,
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any] | None) -> "AvailabilityRegistry":
        registry = cls()
        if not isinstance(payload, Mapping):
            return registry
        records = payload.get("records")
        if not isinstance(records, list):
            return registry
        for item in records:
            record = _record_from_payload(item)
            if record is None:
                continue
            registry.set(record)
        return registry


def _datetime_to_text(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.isoformat()


def _datetime_from_text(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _intish(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _floatish(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _status_from_text(value: Any) -> ProbeStatus:
    normalized = str(value or "").strip().lower()
    if normalized == ProbeStatus.AVAILABLE.value:
        return ProbeStatus.AVAILABLE
    if normalized == ProbeStatus.UNAVAILABLE.value:
        return ProbeStatus.UNAVAILABLE
    return ProbeStatus.UNKNOWN


def _record_to_payload(record: AvailabilityRecord) -> dict[str, Any]:
    retry_after = record.retry_after.total_seconds() if record.retry_after is not None else None
    return {
        "provider_name": record.provider_name,
        "model": record.model,
        "status": record.status.value,
        "checked_at": _datetime_to_text(record.checked_at),
        "failure_code": record.failure_code,
        "failure_reason": record.failure_reason,
        "retry_after_seconds": retry_after,
        "last_success_at": _datetime_to_text(record.last_success_at),
        "last_failure_at": _datetime_to_text(record.last_failure_at),
        "last_latency_ms": record.last_latency_ms,
        "avg_latency_ms": record.avg_latency_ms,
        "latency_sample_count": record.latency_sample_count,
        "success_count": record.success_count,
        "failure_count": record.failure_count,
        "consecutive_failures": record.consecutive_failures,
    }


def _record_from_payload(payload: Any) -> AvailabilityRecord | None:
    if not isinstance(payload, Mapping):
        return None
    provider_name = str(payload.get("provider_name") or "").strip()
    model = str(payload.get("model") or "").strip()
    checked_at = _datetime_from_text(payload.get("checked_at"))
    if not provider_name or not model or checked_at is None:
        return None
    retry_after_seconds = _floatish(payload.get("retry_after_seconds"))
    retry_after = (
        timedelta(seconds=max(0.0, retry_after_seconds))
        if retry_after_seconds is not None
        else None
    )
    return AvailabilityRecord(
        provider_name=provider_name,
        model=model,
        status=_status_from_text(payload.get("status")),
        checked_at=checked_at,
        failure_code=str(payload.get("failure_code") or "").strip(),
        failure_reason=str(payload.get("failure_reason") or "").strip(),
        retry_after=retry_after,
        last_success_at=_datetime_from_text(payload.get("last_success_at")),
        last_failure_at=_datetime_from_text(payload.get("last_failure_at")),
        last_latency_ms=_intish(payload.get("last_latency_ms")) if payload.get("last_latency_ms") is not None else None,
        avg_latency_ms=_intish(payload.get("avg_latency_ms")) if payload.get("avg_latency_ms") is not None else None,
        latency_sample_count=max(0, _intish(payload.get("latency_sample_count"))),
        success_count=max(0, _intish(payload.get("success_count"))),
        failure_count=max(0, _intish(payload.get("failure_count"))),
        consecutive_failures=max(0, _intish(payload.get("consecutive_failures"))),
    )

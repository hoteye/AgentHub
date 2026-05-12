from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal


ToolAvailability = Literal["supported", "unsupported", "unknown", "error"]
CapabilityConfidence = Literal["high", "medium", "low"]
CapabilityDecisionSource = Literal["static_rule", "probe_cache", "user_override", "fallback"]
ProbeCacheStatus = Literal["supported", "unsupported", "unknown", "error", "no_probe_adapter"]


DEFAULT_PROBE_CACHE_TTL_SECONDS = 21600
DEFAULT_PROBE_CACHE_FILENAME = "native_web_search_probe_cache.json"
DEFAULT_TOOL_KEY = "web_search"

_AVAILABLE_VALUES: tuple[ToolAvailability, ...] = ("supported", "unsupported", "unknown", "error")
_CONFIDENCE_VALUES: tuple[CapabilityConfidence, ...] = ("high", "medium", "low")
_PROBE_STATUS_VALUES: tuple[ProbeCacheStatus, ...] = (
    "supported",
    "unsupported",
    "unknown",
    "error",
    "no_probe_adapter",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso_utc(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalized_non_negative_int(value: Any, *, default: int) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return int(default)
    return max(0, normalized)


def _normalized_availability(value: Any) -> ToolAvailability:
    normalized = str(value or "").strip().lower()
    if normalized in _AVAILABLE_VALUES:
        return normalized  # type: ignore[return-value]
    return "unknown"


def _normalized_confidence(value: Any) -> CapabilityConfidence:
    normalized = str(value or "").strip().lower()
    if normalized in _CONFIDENCE_VALUES:
        return normalized  # type: ignore[return-value]
    return "low"


def _normalized_probe_status(value: Any) -> ProbeCacheStatus:
    normalized = str(value or "").strip().lower()
    if normalized in _PROBE_STATUS_VALUES:
        return normalized  # type: ignore[return-value]
    return "unknown"


@dataclass(frozen=True, slots=True)
class CapabilityFact:
    tool: str
    selected_backend: str
    availability: ToolAvailability
    confidence: CapabilityConfidence
    decision_source: CapabilityDecisionSource
    reason: str = ""
    checked_at: str = ""

    @property
    def capability_key(self) -> str:
        return self.tool


@dataclass(frozen=True, slots=True)
class CapabilitySnapshot:
    tool: str
    selected_backend: str
    availability: ToolAvailability
    confidence: CapabilityConfidence
    decision_source: CapabilityDecisionSource
    reason: str = ""
    checked_at: str = ""
    cache_key: str = ""
    cache_status: str = ""
    cache_expires_at: str = ""
    cache_source: str = ""

    @property
    def capability_key(self) -> str:
        return self.tool

    def to_fact(self) -> CapabilityFact:
        return CapabilityFact(
            tool=self.tool,
            selected_backend=self.selected_backend,
            availability=self.availability,
            confidence=self.confidence,
            decision_source=self.decision_source,
            reason=self.reason,
            checked_at=self.checked_at,
        )


@dataclass(frozen=True, slots=True)
class ProbeCacheKey:
    provider_name: str = ""
    model: str = ""
    wire_api: str = ""
    planner_kind: str = ""
    tool: str = DEFAULT_TOOL_KEY

    def as_lookup_key(self) -> str:
        parts = (
            str(self.provider_name or "").strip().lower(),
            str(self.model or "").strip().lower(),
            str(self.wire_api or "").strip().lower(),
            str(self.planner_kind or "").strip().lower(),
        )
        if str(self.tool or "").strip().lower() in {"", DEFAULT_TOOL_KEY}:
            return "|".join(parts)
        return "|".join((str(self.tool or "").strip().lower(), *parts))


@dataclass(frozen=True, slots=True)
class ProbeCacheRecord:
    selected_backend: str
    availability: ToolAvailability
    confidence: CapabilityConfidence
    checked_at: str
    ttl_seconds: int = DEFAULT_PROBE_CACHE_TTL_SECONDS
    reason: str = ""
    probe_status: ProbeCacheStatus = "unknown"
    source: str = "probe_script"
    tool: str = DEFAULT_TOOL_KEY

    @property
    def capability_key(self) -> str:
        return self.tool

    def expires_at(self) -> str:
        checked_at = _parse_iso_utc(self.checked_at)
        if checked_at is None:
            return ""
        return (checked_at + timedelta(seconds=max(0, int(self.ttl_seconds)))).replace(microsecond=0).isoformat()

    def is_stale(self, *, now_iso: str | None = None) -> bool:
        checked_at = _parse_iso_utc(self.checked_at)
        if checked_at is None:
            return True
        now_dt = _parse_iso_utc(now_iso or "") or datetime.now(timezone.utc)
        return now_dt > (checked_at + timedelta(seconds=max(0, int(self.ttl_seconds))))


def capability_fact(
    *,
    tool: str,
    selected_backend: str,
    availability: ToolAvailability,
    confidence: CapabilityConfidence,
    decision_source: CapabilityDecisionSource,
    reason: str = "",
    checked_at: str | None = None,
) -> CapabilityFact:
    return CapabilityFact(
        tool=str(tool or "").strip(),
        selected_backend=str(selected_backend or "").strip(),
        availability=_normalized_availability(availability),
        confidence=_normalized_confidence(confidence),
        decision_source=str(decision_source or "").strip() or "fallback",
        reason=str(reason or "").strip(),
        checked_at=str(checked_at or "").strip() or utc_now_iso(),
    )


def capability_snapshot(
    *,
    tool: str,
    selected_backend: str,
    availability: ToolAvailability,
    confidence: CapabilityConfidence,
    decision_source: CapabilityDecisionSource,
    reason: str = "",
    checked_at: str | None = None,
    cache_key: str = "",
    cache_status: str = "",
    cache_expires_at: str = "",
    cache_source: str = "",
) -> CapabilitySnapshot:
    return CapabilitySnapshot(
        tool=str(tool or "").strip(),
        selected_backend=str(selected_backend or "").strip(),
        availability=_normalized_availability(availability),
        confidence=_normalized_confidence(confidence),
        decision_source=str(decision_source or "").strip() or "fallback",
        reason=str(reason or "").strip(),
        checked_at=str(checked_at or "").strip() or utc_now_iso(),
        cache_key=str(cache_key or "").strip(),
        cache_status=str(cache_status or "").strip(),
        cache_expires_at=str(cache_expires_at or "").strip(),
        cache_source=str(cache_source or "").strip(),
    )


def capability_fact_from_snapshot(snapshot: CapabilitySnapshot) -> CapabilityFact:
    return snapshot.to_fact()


def probe_cache_key(
    *,
    provider_name: str = "",
    model: str = "",
    wire_api: str = "",
    planner_kind: str = "",
    tool: str = DEFAULT_TOOL_KEY,
) -> ProbeCacheKey:
    return ProbeCacheKey(
        provider_name=str(provider_name or "").strip().lower(),
        model=str(model or "").strip().lower(),
        wire_api=str(wire_api or "").strip().lower(),
        planner_kind=str(planner_kind or "").strip().lower(),
        tool=str(tool or "").strip().lower() or DEFAULT_TOOL_KEY,
    )


def probe_cache_record(
    *,
    selected_backend: str,
    availability: ToolAvailability,
    confidence: CapabilityConfidence,
    checked_at: str | None = None,
    ttl_seconds: int = DEFAULT_PROBE_CACHE_TTL_SECONDS,
    reason: str = "",
    probe_status: ProbeCacheStatus = "unknown",
    source: str = "probe_script",
    tool: str = DEFAULT_TOOL_KEY,
) -> ProbeCacheRecord:
    return ProbeCacheRecord(
        selected_backend=str(selected_backend or "").strip(),
        availability=_normalized_availability(availability),
        confidence=_normalized_confidence(confidence),
        checked_at=str(checked_at or "").strip() or utc_now_iso(),
        ttl_seconds=_normalized_non_negative_int(ttl_seconds, default=DEFAULT_PROBE_CACHE_TTL_SECONDS),
        reason=str(reason or "").strip(),
        probe_status=_normalized_probe_status(probe_status),
        source=str(source or "").strip() or "probe_script",
        tool=str(tool or "").strip().lower() or DEFAULT_TOOL_KEY,
    )


def coerce_probe_cache_record(value: Any, *, default_tool: str = DEFAULT_TOOL_KEY) -> ProbeCacheRecord | None:
    if isinstance(value, ProbeCacheRecord):
        return value
    if not isinstance(value, dict):
        return None
    selected_backend = str(value.get("selected_backend") or "").strip()
    if not selected_backend:
        return None
    return probe_cache_record(
        selected_backend=selected_backend,
        availability=_normalized_availability(value.get("availability")),
        confidence=_normalized_confidence(value.get("confidence")),
        checked_at=str(value.get("checked_at") or "").strip() or None,
        ttl_seconds=_normalized_non_negative_int(
            value.get("ttl_seconds"),
            default=DEFAULT_PROBE_CACHE_TTL_SECONDS,
        ),
        reason=str(value.get("reason") or "").strip(),
        probe_status=_normalized_probe_status(value.get("probe_status")),
        source=str(value.get("source") or "").strip() or "probe_script",
        tool=str(value.get("tool") or value.get("capability_key") or default_tool or "").strip().lower()
        or DEFAULT_TOOL_KEY,
    )

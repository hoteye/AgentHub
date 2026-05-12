from __future__ import annotations

from typing import Any

from cli.agent_cli.tools_core.capability_discovery_models import (
    DEFAULT_PROBE_CACHE_FILENAME,
    DEFAULT_PROBE_CACHE_TTL_SECONDS,
    DEFAULT_TOOL_KEY,
    CapabilityConfidence,
    CapabilityDecisionSource,
    CapabilitySnapshot,
    ProbeCacheKey,
    ProbeCacheRecord,
    ProbeCacheStatus,
    ToolAvailability,
    capability_snapshot as _capability_snapshot,
    coerce_probe_cache_record,
    probe_cache_key as _probe_cache_key,
    probe_cache_record as _probe_cache_record,
    utc_now_iso,
)


# Backward-compatible web_search aliases used by the existing resolver/runtime.
WEB_SEARCH_TOOL_KEY = DEFAULT_TOOL_KEY
DEFAULT_WEB_SEARCH_PROBE_CACHE_TTL_SECONDS = DEFAULT_PROBE_CACHE_TTL_SECONDS
DEFAULT_WEB_SEARCH_PROBE_CACHE_FILENAME = DEFAULT_PROBE_CACHE_FILENAME

ToolCapabilitySnapshot = CapabilitySnapshot
WebSearchProbeCacheKey = ProbeCacheKey
WebSearchProbeCacheValue = ProbeCacheRecord


def web_search_probe_cache_key(
    *,
    provider_name: str = "",
    model: str = "",
    wire_api: str = "",
    planner_kind: str = "",
) -> WebSearchProbeCacheKey:
    return _probe_cache_key(
        provider_name=provider_name,
        model=model,
        wire_api=wire_api,
        planner_kind=planner_kind,
        tool=WEB_SEARCH_TOOL_KEY,
    )


def web_search_probe_cache_value(
    *,
    selected_backend: str,
    availability: ToolAvailability,
    confidence: CapabilityConfidence,
    checked_at: str | None = None,
    ttl_seconds: int = DEFAULT_WEB_SEARCH_PROBE_CACHE_TTL_SECONDS,
    reason: str = "",
    probe_status: ProbeCacheStatus = "unknown",
    source: str = "probe_script",
) -> WebSearchProbeCacheValue:
    return _probe_cache_record(
        selected_backend=selected_backend,
        availability=availability,
        confidence=confidence,
        checked_at=checked_at,
        ttl_seconds=ttl_seconds,
        reason=reason,
        probe_status=probe_status,
        source=source,
        tool=WEB_SEARCH_TOOL_KEY,
    )


def coerce_web_search_probe_cache_value(value: Any) -> WebSearchProbeCacheValue | None:
    coerced = coerce_probe_cache_record(value, default_tool=WEB_SEARCH_TOOL_KEY)
    if coerced is None:
        return None
    if str(coerced.tool or "").strip().lower() != WEB_SEARCH_TOOL_KEY:
        return None
    return coerced


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
) -> ToolCapabilitySnapshot:
    return _capability_snapshot(
        tool=tool,
        selected_backend=selected_backend,
        availability=availability,
        confidence=confidence,
        decision_source=decision_source,
        reason=reason,
        checked_at=checked_at,
        cache_key=cache_key,
        cache_status=cache_status,
        cache_expires_at=cache_expires_at,
        cache_source=cache_source,
    )

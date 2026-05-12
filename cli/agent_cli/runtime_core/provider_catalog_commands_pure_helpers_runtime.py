from __future__ import annotations

from typing import Any


def ttl_seconds_from_provider(entry: Any) -> int:
    raw_provider = dict(getattr(entry, "raw_provider", {}) or {})
    for key in ("catalog_ttl_seconds", "catalog_ttl", "model_catalog_ttl_seconds"):
        if key not in raw_provider:
            continue
        try:
            return max(30, int(raw_provider.get(key) or 0))
        except Exception:
            break
    return 3600


def cache_freshness(*, fetched_at: int, expires_at: int, model_count: int, now: int) -> str:
    if fetched_at <= 0 and model_count <= 0:
        return "missing"
    if expires_at > now:
        return "fresh"
    return "stale"


def cached_model_count(models: Any) -> int:
    return len(models) if isinstance(models, list) else 0


def cache_ttl_seconds(*, fetched_at: int, expires_at: int, configured_ttl: int) -> int:
    if fetched_at > 0 and expires_at > 0:
        return max(0, expires_at - fetched_at)
    return configured_ttl


def ttl_remaining_seconds(*, expires_at: int, now: int) -> int:
    if expires_at > 0:
        return max(0, expires_at - now)
    return 0


__all__ = [
    "cache_freshness",
    "cache_ttl_seconds",
    "cached_model_count",
    "ttl_remaining_seconds",
    "ttl_seconds_from_provider",
]

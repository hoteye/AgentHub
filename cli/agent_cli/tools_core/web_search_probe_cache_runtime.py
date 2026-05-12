from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping

from cli.agent_cli.tools_core.tool_capabilities import (
    DEFAULT_WEB_SEARCH_PROBE_CACHE_FILENAME,
    WEB_SEARCH_TOOL_KEY,
    ToolCapabilitySnapshot,
    WebSearchProbeCacheKey,
    capability_snapshot,
    coerce_web_search_probe_cache_value,
    web_search_probe_cache_key,
)


def default_web_search_probe_cache_path(*, environ: Mapping[str, str] | None = None) -> Path | None:
    env = os.environ if environ is None else environ
    explicit = str(env.get("AGENTHUB_WEB_SEARCH_PROBE_CACHE") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    provider_home = str(env.get("AGENTHUB_PROVIDER_HOME") or "").strip()
    if provider_home:
        return Path(provider_home).expanduser() / DEFAULT_WEB_SEARCH_PROBE_CACHE_FILENAME
    return None


@lru_cache(maxsize=8)
def _load_probe_cache_entries_cached(path_str: str, mtime_ns: int) -> dict[str, Any]:
    del mtime_ns
    payload = json.loads(Path(path_str).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {}
    entries = payload.get("entries")
    if isinstance(entries, dict):
        return dict(entries)
    probe_cache = payload.get("probe_cache")
    if isinstance(probe_cache, dict):
        nested_entries = probe_cache.get("entries")
        if isinstance(nested_entries, dict):
            return dict(nested_entries)
    return {}


def load_web_search_probe_cache_entries(cache_path: Path | None) -> dict[str, Any]:
    if cache_path is None:
        return {}
    try:
        if not cache_path.exists():
            return {}
        stat_result = cache_path.stat()
        return _load_probe_cache_entries_cached(
            str(cache_path.resolve()),
            int(stat_result.st_mtime_ns),
        )
    except Exception:
        return {}


def default_web_search_probe_cache_lookup(cache_key: WebSearchProbeCacheKey) -> Any:
    cache_path = default_web_search_probe_cache_path()
    entries = load_web_search_probe_cache_entries(cache_path)
    return entries.get(cache_key.as_lookup_key())


def probe_cache_web_search_snapshot(
    *,
    provider_name: str,
    model: str,
    wire_api: str,
    planner_kind: str,
    probe_cache_lookup: Callable[[WebSearchProbeCacheKey], Any] | None,
) -> ToolCapabilitySnapshot | None:
    if not callable(probe_cache_lookup):
        return None
    cache_key = web_search_probe_cache_key(
        provider_name=provider_name,
        model=model,
        wire_api=wire_api,
        planner_kind=planner_kind,
    )
    try:
        cache_value = coerce_web_search_probe_cache_value(probe_cache_lookup(cache_key))
    except Exception:
        return None
    if cache_value is None or cache_value.is_stale():
        return None
    return capability_snapshot(
        tool=WEB_SEARCH_TOOL_KEY,
        selected_backend=cache_value.selected_backend,
        availability=cache_value.availability,
        confidence=cache_value.confidence,
        decision_source="probe_cache",
        reason=str(cache_value.reason or "").strip() or f"probe_cache_{cache_value.probe_status}",
        checked_at=cache_value.checked_at,
        cache_key=cache_key.as_lookup_key(),
        cache_status=cache_value.probe_status,
        cache_expires_at=cache_value.expires_at(),
        cache_source=cache_value.source,
    )

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(slots=True, frozen=True)
class WebSearchExecutionContext:
    route: dict[str, Any]
    resolved_config: Any | None
    effective_backend_id: str
    execution_path: str
    fallback_reason: str

    def annotation_kwargs(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "effective_backend_id": self.effective_backend_id,
            "execution_path": self.execution_path,
            "fallback_reason": self.fallback_reason,
        }


def web_search_event_status_and_summary(payload: Mapping[str, Any]) -> tuple[bool, str]:
    ok = bool(payload.get("ok"))
    summary = f"web results={int(payload.get('count') or 0)}" if ok else "web search failed"
    return ok, summary


def web_fetch_event_status_and_summary(payload: Mapping[str, Any]) -> tuple[bool, str]:
    ok = bool(payload.get("ok"))
    return ok, "web page loaded" if ok else "web fetch failed"


def web_search_result_arguments(
    *,
    query: str,
    limit: int,
    domains: list[str] | None,
    recency_days: int | None,
    market: str | None,
) -> dict[str, Any]:
    return {
        "query": query,
        "limit": limit,
        "domains": list(domains or []) or None,
        "recency_days": recency_days,
        "market": market,
    }


def web_fetch_result_arguments(*, url: str, max_chars: int) -> dict[str, Any]:
    return {"url": url, "max_chars": max_chars}


__all__ = [
    "WebSearchExecutionContext",
    "web_fetch_event_status_and_summary",
    "web_fetch_result_arguments",
    "web_search_event_status_and_summary",
    "web_search_result_arguments",
]

from __future__ import annotations

import json
import re
import time
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from cli.agent_cli.providers.adapters.openai_responses_output import (
    _stream_item_to_dict,
    extract_responses_output_text,
)
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.openai_client import build_openai_client, call_with_provider_retries
from cli.agent_cli.tools_core.tool_capability_resolver import resolve_native_web_search_capability

_URL_PATTERN = re.compile(r"https?://[^\s)\]>\"']+")
_WEATHER_QUERY_MARKERS = (
    "weather",
    "天气",
    "气温",
    "温度",
    "降雨",
    "降雪",
    "风力",
    "预报",
    "台风",
)


def _normalized_domains(domains: Optional[Iterable[str]]) -> List[str]:
    seen: set[str] = set()
    normalized: List[str] = []
    for value in list(domains or []):
        text = str(value or "").strip().lower()
        if not text:
            continue
        if text.startswith("http://") or text.startswith("https://"):
            text = urlparse(text).netloc.lower()
        text = text.lstrip(".")
        if text and text not in seen:
            seen.add(text)
            normalized.append(text)
    return normalized


def _looks_like_weather_query(query: str) -> bool:
    normalized = str(query or "").strip().lower()
    if not normalized:
        return False
    return any(marker in normalized for marker in _WEATHER_QUERY_MARKERS)


def _normalized_limit(limit: int) -> int:
    return max(1, min(int(limit or 5), 10))


def _constraints_text(
    *,
    domains: Optional[Iterable[str]],
    recency_days: Optional[int],
    market: Optional[str],
) -> str:
    domain_values = ", ".join(_normalized_domains(domains))
    constraints: list[str] = []
    if domain_values:
        constraints.append(f"preferred_domains={domain_values}")
    if recency_days is not None:
        constraints.append(f"recency_days={int(recency_days)}")
    if market:
        constraints.append(f"market={str(market).strip()}")
    return " ; ".join(constraints) if constraints else "none"


def _search_prompt(
    *,
    query: str,
    limit: int,
    domains: Optional[Iterable[str]],
    recency_days: Optional[int],
    market: Optional[str],
) -> str:
    normalized_limit = _normalized_limit(limit)
    constraints_text = _constraints_text(
        domains=domains,
        recency_days=recency_days,
        market=market,
    )
    if _looks_like_weather_query(query):
        return (
            "Answer the weather question using the native web_search tool exactly once. "
            "You may reformulate the search internally instead of searching the user text literally. "
            "Only use information that clearly matches the requested city/location; ignore mismatched cities. "
            "Return strict JSON only (no markdown) with this schema: "
            '{"assistant_text":"...","confidence":"high|medium|low","location":"...","results":[{"title":"...","url":"...","snippet":"..."}]} '
            "assistant_text must be concise Chinese and include current conditions and today's high/low when available. "
            f"Limit results to at most {normalized_limit}. "
            f"user_question={str(query or '').strip()} ; constraints={constraints_text}"
        )
    return (
        "Search the web for the query exactly as given. Use the native web_search tool exactly once. "
        "Then return strict JSON only (no markdown) with this schema: "
        '{"results":[{"title":"...","url":"...","snippet":"..."}],"assistant_text":"..."} '
        f"Limit results to at most {normalized_limit}. "
        f"query={str(query or '').strip()} ; constraints={constraints_text}"
    )


def _extract_json_object(text: str) -> dict[str, Any]:
    candidate = str(text or "").strip()
    if not candidate:
        return {}
    if candidate.startswith("{") and candidate.endswith("}"):
        try:
            parsed = json.loads(candidate)
        except Exception:
            parsed = {}
        if isinstance(parsed, dict):
            return parsed
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        parsed = json.loads(candidate[start : end + 1])
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _results_from_output_text(text: str, *, limit: int) -> list[dict[str, Any]]:
    normalized = str(text or "").strip()
    if not normalized:
        return []
    urls: list[str] = []
    seen: set[str] = set()
    for match in _URL_PATTERN.findall(normalized):
        url = str(match or "").strip().rstrip(".,;")
        if not url or url in seen:
            continue
        seen.add(url)
        urls.append(url)
        if len(urls) >= max(1, min(int(limit or 5), 10)):
            break
    rows: list[dict[str, Any]] = []
    for index, url in enumerate(urls, start=1):
        domain = urlparse(url).netloc.lower()
        rows.append(
            {
                "rank": index,
                "title": domain or url,
                "url": url,
                "snippet": "",
                "source_domain": domain,
                "page_age": None,
            }
        )
    return rows


def _normalize_results(raw_results: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(raw_results, list):
        return []
    rows: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        rows.append(
            {
                "title": str(item.get("title") or url).strip(),
                "url": url,
                "snippet": str(item.get("snippet") or "").strip(),
                "source_domain": urlparse(url).netloc.lower(),
                "page_age": None,
            }
        )
        if len(rows) >= max(1, min(int(limit or 5), 10)):
            break
    return [
        {
            "rank": index,
            "title": str(item.get("title") or "").strip(),
            "url": str(item.get("url") or "").strip(),
            "snippet": str(item.get("snippet") or "").strip(),
            "source_domain": str(item.get("source_domain") or "").strip(),
            "page_age": item.get("page_age"),
        }
        for index, item in enumerate(rows, start=1)
    ]


def _mode_contract_for_config(config: ProviderConfig) -> tuple[str, str, bool]:
    requested_mode = "cached"
    effective_mode = "cached"
    try:
        capability = resolve_native_web_search_capability(config)
    except Exception:
        capability = None
    if capability is not None:
        requested_mode = str(getattr(capability, "requested_mode", "") or "").strip().lower() or requested_mode
        effective_mode = str(getattr(capability, "effective_mode", "") or "").strip().lower() or effective_mode
    external_web_access = effective_mode == "live"
    return requested_mode, effective_mode, external_web_access


def native_web_search_payload(
    config: ProviderConfig,
    *,
    query: str,
    limit: int = 5,
    domains: Optional[Iterable[str]] = None,
    recency_days: Optional[int] = None,
    market: Optional[str] = None,
) -> Dict[str, Any]:
    client = build_openai_client(config)
    normalized_query = str(query or "").strip()
    requested_mode, effective_mode, external_web_access = _mode_contract_for_config(config)
    started_at = time.perf_counter()
    response = call_with_provider_retries(
        lambda: client.responses.create(
            model=str(config.model or "").strip(),
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are an assistant for provider-native web search execution. "
                        "Use native web_search and return JSON exactly as requested."
                    ),
                },
                {
                    "role": "user",
                    "content": _search_prompt(
                        query=normalized_query,
                        limit=limit,
                        domains=domains,
                        recency_days=recency_days,
                        market=market,
                    ),
                },
            ],
            tools=[{"type": "web_search", "external_web_access": external_web_access}],
            tool_choice="auto",
            store=False,
            timeout=25.0,
        )
    )
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)
    output_items = [_stream_item_to_dict(item) for item in list(getattr(response, "output", []) or [])]
    marker_types = [str(item.get("type") or "").strip() for item in output_items if str(item.get("type") or "").strip()]
    web_search_calls = [item for item in output_items if str(item.get("type") or "").strip() == "web_search_call"]
    first_call = web_search_calls[0] if web_search_calls else {}
    action = dict(first_call.get("action") or {}) if isinstance(first_call, dict) else {}
    issued_queries = [str(item).strip() for item in list(action.get("queries") or []) if str(item).strip()]
    if not issued_queries:
        single_query = str(action.get("query") or "").strip()
        if single_query:
            issued_queries = [single_query]

    output_text = str(extract_responses_output_text(response) or "").strip()
    parsed_object = _extract_json_object(output_text)
    normalized_results = _normalize_results(parsed_object.get("results"), limit=limit)
    if not normalized_results:
        normalized_results = _normalize_results(parsed_object.get("sources"), limit=limit)
    if not normalized_results:
        normalized_results = _results_from_output_text(output_text, limit=limit)

    assistant_text = str(parsed_object.get("assistant_text") or "").strip() or output_text
    response_status = str(getattr(response, "status", "") or "").strip().lower()
    search_dispatched = bool(web_search_calls)
    search_results_received = bool(normalized_results)
    if not search_dispatched:
        native_interrupted = False
        web_search_outcome = "provider_error_without_search"
        retryable = response_status == "incomplete"
        if retryable:
            issue = "provider-native response was incomplete before web_search_call dispatch"
            error_code = "native_web_search_incomplete_before_dispatch"
        else:
            issue = "response accepted but native web_search_call marker was absent"
            error_code = "native_web_search_call_missing"
    elif not search_results_received:
        issue = "native web_search_call completed without usable structured results"
        error_code = "native_web_search_results_missing"
        native_interrupted = True
        web_search_outcome = "native_interrupted"
        retryable = response_status == "incomplete"
        if retryable:
            issue = "native web search response was incomplete before usable results were received"
            error_code = "native_web_search_incomplete"
    else:
        issue = ""
        error_code = ""
        native_interrupted = False
        web_search_outcome = "search_results_received"
        retryable = False
    ok = search_dispatched and search_results_received and bool(assistant_text or normalized_results)
    requested_domains = _normalized_domains(domains)

    return {
        "ok": ok,
        "engine": "openai_native_web_search",
        "provider": str(config.provider_name or "").strip(),
        "model": str(config.model or "").strip(),
        "query": normalized_query,
        "requested_mode": requested_mode,
        "effective_mode": effective_mode,
        "external_web_access": external_web_access,
        "issued_queries": issued_queries,
        "count": len(normalized_results),
        "results": normalized_results,
        "text": assistant_text,
        "assistant_text": assistant_text,
        "confidence": str(parsed_object.get("confidence") or "").strip(),
        "location": str(parsed_object.get("location") or "").strip(),
        "marker_types": marker_types,
        "native_markers": ["web_search_call"] if web_search_calls else [],
        "requested_domains": requested_domains,
        "applied_domains": requested_domains,
        "applied_recency_days": recency_days,
        "market": market,
        "response_status": response_status,
        "search_dispatched": search_dispatched,
        "search_results_received": search_results_received,
        "native_interrupted": native_interrupted,
        "web_search_outcome": web_search_outcome,
        "errors": [] if ok else [issue],
        "error_code": "" if ok else error_code,
        "retryable": retryable,
        "response_id": str(getattr(response, "id", "") or "").strip(),
        "elapsed_ms": elapsed_ms,
    }

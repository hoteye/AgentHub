from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from cli.agent_cli.providers.anthropic_claude_runtime import content_block_dict
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.openai_client import call_with_provider_retries


def _build_client(config: ProviderConfig) -> Any:
    try:
        from anthropic import Anthropic
    except ImportError as exc:
        raise RuntimeError(
            "Anthropic native web search requires the `anthropic` package. Install cli/requirements.txt first."
        ) from exc

    kwargs: Dict[str, Any] = {"api_key": config.api_key}
    if str(config.base_url or "").strip():
        kwargs["base_url"] = str(config.base_url)
    return Anthropic(**kwargs)


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


def _tool_spec(*, limit: int, domains: Optional[Iterable[str]]) -> Dict[str, Any]:
    spec: Dict[str, Any] = {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": max(1, min(int(limit or 5), 8)),
    }
    allowed_domains = _normalized_domains(domains)
    if allowed_domains:
        spec["allowed_domains"] = allowed_domains
    return spec


def _server_tool_query(payload: Dict[str, Any]) -> str:
    tool_input = payload.get("input")
    if not isinstance(tool_input, dict):
        return ""
    for key in ("query", "search_query"):
        text = str(tool_input.get(key) or "").strip()
        if text:
            return text
    return ""


def native_web_search_payload(
    config: ProviderConfig,
    *,
    query: str,
    limit: int = 5,
    domains: Optional[Iterable[str]] = None,
    recency_days: Optional[int] = None,
    market: Optional[str] = None,
) -> Dict[str, Any]:
    client = _build_client(config)
    started_at = time.perf_counter()
    response = call_with_provider_retries(
        lambda: client.messages.create(
            model=str(config.model or "").strip(),
            max_tokens=768,
            system="You are an assistant for performing a web search tool use.",
            messages=[
                {
                    "role": "user",
                    "content": f"Perform a web search for the query: {str(query or '').strip()}",
                }
            ],
            tools=[_tool_spec(limit=limit, domains=domains)],
            tool_choice={"type": "tool", "name": "web_search"},
        )
    )
    elapsed_ms = int((time.perf_counter() - started_at) * 1000)

    result_rows: List[Dict[str, Any]] = []
    text_parts: List[str] = []
    server_tool_uses: List[str] = []
    issued_queries: List[str] = []
    errors: List[str] = []
    response_block_types: List[str] = []
    web_search_tool_result_count = 0

    for block in list(getattr(response, "content", []) or []):
        payload = content_block_dict(block)
        block_type = str(payload.get("type") or "").strip()
        if block_type:
            response_block_types.append(block_type)
        if block_type == "server_tool_use":
            tool_name = str(payload.get("name") or "").strip()
            if tool_name:
                server_tool_uses.append(tool_name)
            issued_query = _server_tool_query(payload)
            if issued_query:
                issued_queries.append(issued_query)
            continue
        if block_type == "web_search_tool_result":
            web_search_tool_result_count += 1
            content = payload.get("content")
            if isinstance(content, dict):
                error_code = str(content.get("error_code") or "").strip()
                if error_code:
                    errors.append(error_code)
                continue
            if not isinstance(content, list):
                continue
            for entry in content:
                if not isinstance(entry, dict):
                    continue
                url = str(entry.get("url") or "").strip()
                title = str(entry.get("title") or "").strip()
                snippet = str(entry.get("encrypted_content") or entry.get("content") or "").strip()
                if not url or not title:
                    continue
                result_rows.append(
                    {
                        "title": title,
                        "url": url,
                        "snippet": snippet,
                        "source_domain": urlparse(url).netloc.lower(),
                        "page_age": entry.get("page_age"),
                    }
                )
            continue
        if block_type == "text":
            text = str(payload.get("text") or "").strip()
            if text:
                text_parts.append(text)

    deduped_results: List[Dict[str, Any]] = []
    seen_urls: set[str] = set()
    for entry in result_rows:
        url = str(entry.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        deduped_results.append(entry)

    final_text = "\n\n".join(text_parts).strip()
    normalized_results = [
        {
            "rank": index,
            "title": str(entry.get("title") or "").strip(),
            "url": str(entry.get("url") or "").strip(),
            "snippet": str(entry.get("snippet") or "").strip(),
            "source_domain": str(entry.get("source_domain") or "").strip(),
            "page_age": entry.get("page_age"),
        }
        for index, entry in enumerate(deduped_results[: max(1, int(limit or 5))], start=1)
    ]
    response_status = str(getattr(response, "stop_reason", "") or "").strip()
    search_dispatched = bool(server_tool_uses)
    search_results_received = bool(normalized_results)
    if not search_dispatched:
        issue = "anthropic response accepted without server_tool_use dispatch"
        error_code = str(errors[0] or "").strip() if errors else "server_tool_use_missing"
        native_interrupted = False
        web_search_outcome = "provider_error_without_search"
        retryable = False
    elif not search_results_received:
        native_interrupted = True
        web_search_outcome = "native_interrupted"
        retryable = True
        if errors:
            error_code = str(errors[0] or "").strip()
            issue = "web_search_tool_result returned provider-side error without usable results"
        elif web_search_tool_result_count <= 0:
            error_code = "server_tool_result_missing"
            issue = "server_tool_use observed without matching web_search_tool_result"
        else:
            error_code = "web_search_tool_result_empty"
            issue = "web_search_tool_result returned without usable structured results"
    else:
        issue = ""
        error_code = ""
        native_interrupted = False
        web_search_outcome = "search_results_received"
        retryable = False

    return {
        "ok": search_results_received and bool(final_text or normalized_results),
        "engine": "anthropic_native_web_search",
        "provider": str(config.provider_name or "").strip(),
        "model": str(config.model or "").strip(),
        "query": str(query or "").strip(),
        "issued_queries": issued_queries,
        "count": len(normalized_results),
        "results": normalized_results,
        "text": final_text,
        "assistant_text": final_text,
        "server_tool_uses": server_tool_uses,
        "response_block_types": response_block_types,
        "requested_domains": _normalized_domains(domains),
        "applied_domains": _normalized_domains(domains),
        "applied_recency_days": recency_days,
        "market": market,
        "errors": [] if search_results_received else errors or [issue],
        "error_code": "" if search_results_received else error_code,
        "retryable": retryable,
        "response_status": response_status,
        "search_dispatched": search_dispatched,
        "search_results_received": search_results_received,
        "native_interrupted": native_interrupted,
        "web_search_outcome": web_search_outcome,
        "web_search_tool_result_count": web_search_tool_result_count,
        "response_id": str(getattr(response, "id", "") or "").strip(),
        "elapsed_ms": elapsed_ms,
    }

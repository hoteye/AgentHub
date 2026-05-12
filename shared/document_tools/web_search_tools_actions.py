from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from cli.agent_cli.models import CommandExecutionResult
from shared.document_tools.web_search_tools_support import (
    _host_matches_policy,
    _matches_domain,
    _normalize_domains,
    _safe_max_chars,
    _structured_result,
    _web_fetch_failure_payload,
)


def web_search(
    self: Any,
    query: str,
    *,
    limit: int = 5,
    domains: Iterable[str] | None = None,
    recency_days: int | None = None,
    market: str | None = None,
) -> dict[str, Any]:
    normalized_query = str(query or "").strip()
    if not normalized_query:
        return {
            "ok": False,
            "error": "query is required",
            "query": normalized_query,
            "count": 0,
            "results": [],
        }

    requested_domains = _normalize_domains(domains)
    recommended_domains = self._policy.recommended_domains(normalized_query)
    effective_domains = requested_domains or self._policy.allowed_domains
    safe_limit = max(1, min(int(limit or 5), 10))
    try:
        xml_text = self._fetch_text(self._search_url(normalized_query, market=market))
        parsed = self._parse_bing_rss(xml_text)
        filtered = [
            item
            for item in parsed
            if _matches_domain(item.url, effective_domains)
            and not any(
                _host_matches_policy(item.source_domain, domain)
                for domain in self._policy.denied_domains
            )
            and self._matches_recency(item.published_at, recency_days)
        ]
        ranked = [
            self._build_search_result_payload(
                normalized_query,
                item,
                rank=index,
                recommended_domains=recommended_domains,
            )
            for index, item in enumerate(filtered, start=1)
        ]
        ranked.sort(
            key=lambda item: (
                int(item.get("official_hint") is True),
                int(item.get("credibility_score") or 0),
                str(item.get("published_at") or ""),
            ),
            reverse=True,
        )
        for index, item in enumerate(ranked, start=1):
            item["rank"] = index
        results = ranked[:safe_limit]
        return {
            "ok": True,
            "engine": "bing_rss",
            "query": normalized_query,
            "count": len(results),
            "results": results,
            "applied_domains": effective_domains,
            "requested_domains": requested_domains,
            "recommended_domains": recommended_domains,
            "official_domains": list(self._policy.official_domains),
            "preferred_domains": list(self._policy.preferred_domains),
            "applied_recency_days": int(recency_days) if recency_days else None,
            "market": str(market or "").strip() or None,
            "search_url": self._search_url(normalized_query, market=market),
            "policy_path": self._policy_path,
        }
    except Exception as exc:
        return {
            "ok": False,
            "engine": "bing_rss",
            "query": normalized_query,
            "count": 0,
            "results": [],
            "applied_domains": effective_domains,
            "requested_domains": requested_domains,
            "recommended_domains": recommended_domains,
            "official_domains": list(self._policy.official_domains),
            "preferred_domains": list(self._policy.preferred_domains),
            "applied_recency_days": int(recency_days) if recency_days else None,
            "market": str(market or "").strip() or None,
            "error": f"{type(exc).__name__}: {exc}",
            "search_url": self._search_url(normalized_query, market=market),
            "policy_path": self._policy_path,
        }


def web_search_result(
    self: Any,
    query: str,
    *,
    limit: int = 5,
    domains: Iterable[str] | None = None,
    recency_days: int | None = None,
    market: str | None = None,
) -> CommandExecutionResult:
    payload = self.web_search(
        query,
        limit=limit,
        domains=domains,
        recency_days=recency_days,
        market=market,
    )
    ok = bool(payload.get("ok"))
    summary = f"web results={int(payload.get('count') or 0)}" if ok else "web search failed"
    return _structured_result(
        tool_name="web_search",
        payload=payload,
        assistant_text="Search the web.",
        arguments={
            "query": query,
            "limit": limit,
            "domains": list(domains or []) or None,
            "recency_days": recency_days,
            "market": market,
        },
        summary=summary,
    )


def web_fetch(self: Any, url: str, *, max_chars: int = 12000) -> dict[str, Any]:
    normalized_url = str(url or "").strip()
    if not normalized_url:
        return {"ok": False, "error": "url is required", "url": normalized_url}
    if not normalized_url.startswith(("http://", "https://")):
        return {
            "ok": False,
            "error": "url must start with http:// or https://",
            "url": normalized_url,
        }

    safe_max_chars = _safe_max_chars(max_chars)
    try:
        page = self._open_url(normalized_url)
        return {
            "ok": True,
            "url": normalized_url,
            "ref_id": page.ref_id,
            "final_url": page.final_url,
            "source_domain": page.source_domain,
            "content_type": page.content_type,
            "title": page.title,
            "text": page.text[:safe_max_chars],
            "truncated": len(page.text) > safe_max_chars,
            "max_chars": safe_max_chars,
            "line_count": len(page.lines),
            "link_count": len(page.links),
            "source_scope": page.source_scope,
        }
    except Exception as exc:
        return {
            "ok": False,
            "url": normalized_url,
            "max_chars": safe_max_chars,
            **_web_fetch_failure_payload(exc),
        }


def web_fetch_result(self: Any, url: str, *, max_chars: int = 12000) -> CommandExecutionResult:
    payload = self.web_fetch(url, max_chars=max_chars)
    return _structured_result(
        tool_name="web_fetch",
        payload=payload,
        assistant_text="Fetch the webpage.",
        arguments={"url": url, "max_chars": max_chars},
        summary="web page loaded" if payload.get("ok") else "web fetch failed",
    )


def open(self: Any, ref: str, *, line: int = 1) -> dict[str, Any]:
    raw_ref = str(ref or "").strip()
    if not raw_ref:
        return {"ok": False, "error": "ref is required"}
    try:
        page = self._resolve_page(raw_ref)
        if page is None:
            if not raw_ref.startswith(("http://", "https://")):
                return {"ok": False, "error": f"unknown ref_id: {raw_ref}", "ref_id": raw_ref}
            page = self._open_url(raw_ref)
        excerpt = page.excerpt(line)
        return {
            "ok": True,
            "ref_id": page.ref_id,
            "url": page.url,
            "final_url": page.final_url,
            "source_domain": page.source_domain,
            "content_type": page.content_type,
            "title": page.title,
            "line_count": len(page.lines),
            "link_count": len(page.links),
            "source_scope": page.source_scope,
            "links": [link.to_dict() for link in page.links[:20]],
            **excerpt,
        }
    except Exception as exc:
        return {"ok": False, "ref_id": raw_ref, **_web_fetch_failure_payload(exc)}


def open_result(self: Any, ref: str, *, line: int = 1) -> CommandExecutionResult:
    payload = self.open(ref, line=line)
    return _structured_result(
        tool_name="open",
        payload=payload,
        assistant_text="Open webpage.",
        arguments={"ref": ref, "line": line},
        summary="page opened" if payload.get("ok") else "open failed",
    )


def click(self: Any, ref_id: str, *, id: int) -> dict[str, Any]:
    raw_ref_id = str(ref_id or "").strip()
    page = self._resolve_page(raw_ref_id)
    if page is None:
        return {"ok": False, "error": f"unknown ref_id: {raw_ref_id}", "ref_id": raw_ref_id}
    link_id = int(id)
    target = next((item for item in page.links if item.id == link_id), None)
    if target is None:
        return {"ok": False, "error": f"unknown link id: {link_id}", "ref_id": raw_ref_id}
    try:
        opened = self._open_url(target.url)
        excerpt = opened.excerpt(1)
        return {
            "ok": True,
            "source_ref_id": raw_ref_id,
            "clicked_link_id": link_id,
            "clicked_link_text": target.text,
            "ref_id": opened.ref_id,
            "url": opened.url,
            "final_url": opened.final_url,
            "source_domain": opened.source_domain,
            "content_type": opened.content_type,
            "title": opened.title,
            "line_count": len(opened.lines),
            "link_count": len(opened.links),
            "source_scope": opened.source_scope,
            "links": [link.to_dict() for link in opened.links[:20]],
            **excerpt,
        }
    except Exception as exc:
        return {
            "ok": False,
            "ref_id": raw_ref_id,
            "clicked_link_id": link_id,
            **_web_fetch_failure_payload(exc),
        }


def click_result(self: Any, ref_id: str, *, id: int) -> CommandExecutionResult:
    payload = self.click(ref_id, id=id)
    return _structured_result(
        tool_name="click",
        payload=payload,
        assistant_text="Open clicked link.",
        arguments={"ref_id": ref_id, "id": id},
        summary="link opened" if payload.get("ok") else "click failed",
    )


def find(self: Any, ref_id: str, *, pattern: str) -> dict[str, Any]:
    raw_ref_id = str(ref_id or "").strip()
    normalized_pattern = str(pattern or "").strip()
    if not normalized_pattern:
        return {"ok": False, "error": "pattern is required", "ref_id": raw_ref_id}
    page = self._resolve_page(raw_ref_id)
    if page is None:
        return {"ok": False, "error": f"unknown ref_id: {raw_ref_id}", "ref_id": raw_ref_id}
    needle = normalized_pattern.lower()
    matches = [
        {"line": index, "text": line}
        for index, line in enumerate(page.lines, start=1)
        if needle in line.lower()
    ]
    return {
        "ok": True,
        "ref_id": raw_ref_id,
        "pattern": normalized_pattern,
        "count": len(matches),
        "matches": matches[:50],
        "source_scope": page.source_scope,
    }


def find_result(self: Any, ref_id: str, *, pattern: str) -> CommandExecutionResult:
    payload = self.find(ref_id, pattern=pattern)
    return _structured_result(
        tool_name="find",
        payload=payload,
        assistant_text="Find text in page.",
        arguments={"ref_id": ref_id, "pattern": pattern},
        summary=f"matches={int(payload.get('count') or 0)}" if payload.get("ok") else "find failed",
    )

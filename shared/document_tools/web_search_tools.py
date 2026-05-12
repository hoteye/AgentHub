from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from shared.document_tools.web_search_tools_actions import (
    click,
    click_result,
    find,
    find_result,
    open,
    open_result,
    web_fetch,
    web_fetch_result,
    web_search,
    web_search_result,
)
from shared.document_tools.web_search_tools_parser import _HTMLPageExtractor
from shared.document_tools.web_search_tools_support import (
    _NETWORK_UNREACHABLE_ERRNOS,
    _NETWORK_UNREACHABLE_TEXT,
    _TRUSTED_SUFFIX_SCORES,
    _clean_multiline,
    _credibility_label,
    _filter_navigation_links,
    _host_labels,
    _host_matches_policy,
    _load_domain_policy,
    _PageLink,
    _PageSnapshot,
    _parse_pub_date,
    _query_tokens,
    _SearchResult,
    _WebDomainPolicy,
)

WEB_SEARCH_SKILLS: list[dict[str, Any]] = [
    {
        "name": "web_search",
        "description": (
            "Search the public web for current information. "
            "Returns ranked result items with title, url, snippet, source domain, and credibility metadata."
        ),
        "params": ["query", "limit", "domains", "recency_days", "market"],
    },
    {
        "name": "web_fetch",
        "description": (
            "Fetch one webpage and extract readable text for the model. "
            "Returns normalized title, final URL, content type, and bounded body text."
        ),
        "params": ["url", "max_chars"],
    },
    {
        "name": "open",
        "description": "Open one webpage or revisit a stored page reference and return a line-based snapshot plus clickable links.",
        "params": ["ref", "line"],
    },
    {
        "name": "click",
        "description": "Open one link from a previously opened page by link id.",
        "params": ["ref_id", "id"],
    },
    {
        "name": "find",
        "description": "Find text in a previously opened page and return matching lines.",
        "params": ["ref_id", "pattern"],
    },
]


class WebSearchTools:
    USER_AGENT = "Mozilla/5.0 (compatible; AgentHubCLI/0.1; +https://www.bing.com)"
    SEARCH_TIMEOUT_SEC = 8
    FETCH_TIMEOUT_SEC = 12
    NETWORK_FAILURE_COOLDOWN_SEC = 8.0

    def __init__(self, *, policy_path: str | None = None) -> None:
        self._page_seq = 0
        self._pages: dict[str, _PageSnapshot] = {}
        self._policy: _WebDomainPolicy = _load_domain_policy(policy_path)
        self._policy_path = str(policy_path or "").strip() or None
        self._network_blocked_until = 0.0
        self._network_failure_message: str | None = None

    def list_skills(self) -> dict[str, Any]:
        return {
            "ok": True,
            "count": len(WEB_SEARCH_SKILLS),
            "skills": WEB_SEARCH_SKILLS,
            "policy_path": self._policy_path,
            "policy": self._policy.to_dict(),
        }

    @classmethod
    def _search_url(cls, query: str, *, market: str | None = None) -> str:
        params: dict[str, str] = {"format": "rss", "q": str(query or "").strip()}
        market_text = str(market or "").strip()
        if market_text:
            params["cc"] = market_text
        return "https://www.bing.com/search?" + urlencode(params)

    @classmethod
    def _request(cls, url: str) -> Request:
        return Request(
            url,
            headers={
                "User-Agent": cls.USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,text/plain;q=0.8,*/*;q=0.7",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
        )

    @staticmethod
    def _network_failure_detail(exc: BaseException) -> str | None:
        for candidate in (getattr(exc, "reason", None), exc):
            if candidate is None:
                continue
            if (
                isinstance(candidate, OSError)
                and getattr(candidate, "errno", None) in _NETWORK_UNREACHABLE_ERRNOS
            ):
                return str(candidate).strip() or "network is unreachable"
            text = str(candidate).strip()
            lowered = text.lower()
            if any(token in lowered for token in _NETWORK_UNREACHABLE_TEXT):
                return text or "network is unreachable"
        return None

    def _raise_if_network_blocked(self) -> None:
        if monotonic() >= self._network_blocked_until:
            return
        detail = self._network_failure_message or "network is unreachable"
        raise URLError(f"{detail} (cached)")

    def _remember_network_failure(self, exc: BaseException) -> None:
        detail = self._network_failure_detail(exc)
        if not detail:
            return
        self._network_failure_message = detail
        self._network_blocked_until = monotonic() + self.NETWORK_FAILURE_COOLDOWN_SEC

    def _clear_network_failure(self) -> None:
        self._network_failure_message = None
        self._network_blocked_until = 0.0

    def _fetch_text(self, url: str, *, timeout_sec: int = SEARCH_TIMEOUT_SEC) -> str:
        self._raise_if_network_blocked()
        try:
            with urlopen(self._request(url), timeout=timeout_sec) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                text = response.read().decode(charset, "ignore")
        except Exception as exc:
            self._remember_network_failure(exc)
            raise
        self._clear_network_failure()
        return text

    def _fetch_response(self, url: str, *, timeout_sec: int = FETCH_TIMEOUT_SEC) -> dict[str, str]:
        self._raise_if_network_blocked()
        try:
            with urlopen(self._request(url), timeout=timeout_sec) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                text = response.read().decode(charset, "ignore")
                payload = {
                    "text": text,
                    "content_type": str(response.headers.get_content_type() or "").strip(),
                    "final_url": str(getattr(response, "geturl", lambda: url)() or url),
                }
        except Exception as exc:
            self._remember_network_failure(exc)
            raise
        self._clear_network_failure()
        return payload

    @staticmethod
    def _parse_bing_rss(xml_text: str) -> list[_SearchResult]:
        root = ET.fromstring(xml_text)
        results: list[_SearchResult] = []
        for item in root.findall("./channel/item"):
            title = str(item.findtext("title", default="") or "").strip()
            title = " ".join(title.split())
            url = str(item.findtext("link", default="") or "").strip()
            url = " ".join(url.split())
            snippet = str(item.findtext("description", default="") or "").strip()
            snippet = " ".join(snippet.split())
            published_at = str(item.findtext("pubDate", default="") or "").strip()
            published_at = " ".join(published_at.split())
            source_domain = urlparse(url).netloc.lower()
            if not title or not url:
                continue
            results.append(
                _SearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
                    published_at=published_at,
                    source_domain=source_domain,
                )
            )
        return results

    def _build_search_result_payload(
        self,
        query: str,
        result: _SearchResult,
        *,
        rank: int,
        recommended_domains: list[str],
    ) -> dict[str, Any]:
        parsed = urlparse(result.url)
        host = parsed.netloc.lower()
        path_lower = parsed.path.lower()
        path_segments = [segment for segment in path_lower.split("/") if segment]
        host_labels = _host_labels(host)
        title_lower = result.title.lower()
        snippet_lower = result.snippet.lower()
        token_matches = _query_tokens(query)
        score = 0
        reasons: list[str] = []
        official_hint = False

        if parsed.scheme == "https":
            score += 5
            reasons.append("https")

        for suffix, suffix_score in _TRUSTED_SUFFIX_SCORES.items():
            if host.endswith(suffix):
                score += suffix_score
                reasons.append(f"trusted_suffix:{suffix}")
                break

        if any(_host_matches_policy(host, domain) for domain in self._policy.official_domains):
            score += 55
            reasons.append("official_domain")
            official_hint = True

        if any(_host_matches_policy(host, domain) for domain in recommended_domains):
            score += 35
            reasons.append("recommended_domain")
            official_hint = True

        if any(_host_matches_policy(host, domain) for domain in self._policy.preferred_domains):
            score += 20
            reasons.append("preferred_domain")

        for token in token_matches:
            if token in host_labels:
                score += 30
                reasons.append(f"host_match:{token}")
                break

        for token in token_matches:
            if token in path_segments:
                score += 18
                reasons.append(f"path_match:{token}")
                break

        if not official_hint:
            for token in token_matches:
                if token in host:
                    score += 6
                    reasons.append(f"host_substring:{token}")
                    break

        for token in token_matches:
            if token in title_lower:
                score += min(8 + len(token) * 2, 24)
                reasons.append(f"title_match:{token}")
                break

        for token in token_matches:
            if token in snippet_lower:
                score += min(4 + len(token), 14)
                reasons.append(f"snippet_match:{token}")
                break

        published_at = _parse_pub_date(result.published_at)
        if published_at is not None:
            age_days = (datetime.now(UTC) - published_at).days
            if age_days <= 7:
                score += 8
                reasons.append("fresh<=7d")
            elif age_days <= 30:
                score += 4
                reasons.append("fresh<=30d")

        return {
            "rank": rank,
            "title": result.title,
            "url": result.url,
            "snippet": result.snippet,
            "published_at": result.published_at,
            "source_domain": result.source_domain,
            "credibility_score": score,
            "credibility_label": _credibility_label(score),
            "official_hint": official_hint,
            "ranking_reasons": reasons,
        }

    @staticmethod
    def _matches_recency(value: str, recency_days: int | None) -> bool:
        if not recency_days or recency_days <= 0:
            return True
        published_at = _parse_pub_date(value)
        if published_at is None:
            return False
        return published_at >= datetime.now(UTC) - timedelta(days=int(recency_days))

    def _next_ref_id(self) -> str:
        self._page_seq += 1
        return f"page_{self._page_seq}"

    @staticmethod
    def _page_from_response(url: str, response: dict[str, str], *, ref_id: str) -> _PageSnapshot:
        text = str(response.get("text") or "")
        content_type = str(response.get("content_type") or "").strip() or "text/plain"
        final_url = str(response.get("final_url") or url)
        if "html" in content_type.lower():
            parser = _HTMLPageExtractor()
            parser.feed(text)
            extracted = parser.extract()
            links = [
                _PageLink(
                    id=index,
                    text=item_text,
                    url=urljoin(final_url, href),
                    in_main=in_main,
                )
                for index, (href, item_text, in_main) in enumerate(extracted["links"], start=1)
                if href
            ]
            filtered_links = _filter_navigation_links(links)
            page_text = str(extracted["text"] or "")
            lines = list(extracted["lines"] or [])
            title = str(extracted["title"] or "").strip()
            scope = str(extracted.get("scope") or "full")
        else:
            page_text = _clean_multiline(text)
            lines = [line for line in page_text.split("\n") if line.strip()]
            filtered_links = []
            title = ""
            scope = "full"
        return _PageSnapshot(
            ref_id=ref_id,
            url=url,
            final_url=final_url,
            source_domain=urlparse(final_url).netloc.lower(),
            title=title,
            content_type=content_type,
            text=page_text,
            lines=lines,
            links=filtered_links,
            source_scope=scope,
        )

    def _store_page(self, page: _PageSnapshot) -> _PageSnapshot:
        self._pages[page.ref_id] = page
        return page

    def _resolve_page(self, ref_id: str) -> _PageSnapshot | None:
        return self._pages.get(str(ref_id or "").strip())

    def _open_url(self, url: str) -> _PageSnapshot:
        ref_id = self._next_ref_id()
        page = self._page_from_response(url, self._fetch_response(url), ref_id=ref_id)
        return self._store_page(page)


WebSearchTools.web_search = web_search
WebSearchTools.web_search_result = web_search_result
WebSearchTools.web_fetch = web_fetch
WebSearchTools.web_fetch_result = web_fetch_result
WebSearchTools.open = open
WebSearchTools.open_result = open_result
WebSearchTools.click = click
WebSearchTools.click_result = click_result
WebSearchTools.find = find
WebSearchTools.find_result = find_result

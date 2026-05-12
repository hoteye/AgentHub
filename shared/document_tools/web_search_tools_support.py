from __future__ import annotations

import html
import re
import tomllib
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from cli.agent_cli.models import CommandExecutionResult, ToolEvent, generic_tool_call_item_events
from shared.document_tools.web_search_tools_support_fetch_errors import (
    _FETCH_FALLBACK_HINT as _FETCH_FALLBACK_HINT,
)
from shared.document_tools.web_search_tools_support_fetch_errors import (
    _NETWORK_UNREACHABLE_ERRNOS as _NETWORK_UNREACHABLE_ERRNOS,
)
from shared.document_tools.web_search_tools_support_fetch_errors import (
    _NETWORK_UNREACHABLE_TEXT as _NETWORK_UNREACHABLE_TEXT,
)
from shared.document_tools.web_search_tools_support_fetch_errors import (
    _classify_fetch_failure as _classify_fetch_failure,
)
from shared.document_tools.web_search_tools_support_fetch_errors import (
    _exception_reason as _exception_reason,
)
from shared.document_tools.web_search_tools_support_fetch_errors import (
    _header_value as _header_value,
)
from shared.document_tools.web_search_tools_support_fetch_errors import (
    _read_exception_body as _read_exception_body,
)
from shared.document_tools.web_search_tools_support_fetch_errors import (
    _web_fetch_failure_payload as _web_fetch_failure_payload,
)
from shared.document_tools.web_search_tools_support_models import (
    _DomainRecommendation as _DomainRecommendation,
)
from shared.document_tools.web_search_tools_support_models import (
    _PageLink as _PageLink,
)
from shared.document_tools.web_search_tools_support_models import (
    _PageSnapshot as _PageSnapshot,
)
from shared.document_tools.web_search_tools_support_models import (
    _SearchResult as _SearchResult,
)
from shared.document_tools.web_search_tools_support_models import (
    _WebDomainPolicy as _WebDomainPolicy,
)

_BLOCK_TAGS = {
    "article",
    "aside",
    "blockquote",
    "br",
    "div",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "li",
    "main",
    "nav",
    "p",
    "pre",
    "section",
}
_MAIN_CONTENT_TAGS = {"main", "article"}
_TRUSTED_SUFFIX_SCORES = {
    ".gov": 45,
    ".gov.cn": 45,
    ".edu": 30,
    ".edu.cn": 30,
    ".mil": 35,
    ".org": 12,
}
_NAV_LINK_TEXT = {
    "sign in",
    "skip to content",
    "skip to main content",
    "navigation menu",
    "toggle navigation",
    "privacy",
    "terms",
    "appearance settings",
}


def _structured_result(
    *,
    tool_name: str,
    payload: dict[str, Any],
    assistant_text: str,
    arguments: dict[str, Any] | None = None,
    summary: str = "",
) -> CommandExecutionResult:
    normalized_payload = dict(payload or {})
    ok = bool(normalized_payload.get("ok"))
    resolved_summary = str(summary or "").strip() or (
        f"{tool_name} ok" if ok else f"{tool_name} failed"
    )
    event = ToolEvent(
        name=tool_name,
        ok=ok,
        summary=resolved_summary,
        payload=normalized_payload,
    )
    return CommandExecutionResult(
        assistant_text=str(assistant_text or ""),
        tool_events=[event],
        item_events=generic_tool_call_item_events(
            tool_name=tool_name,
            arguments=dict(arguments or {}) or None,
            ok=ok,
            summary=resolved_summary,
            structured_content=normalized_payload,
        ),
    )


def _clean_text(value: str) -> str:
    return " ".join(html.unescape(str(value or "")).split()).strip()


def _clean_multiline(value: str) -> str:
    text = html.unescape(str(value or ""))
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _safe_max_chars(value: int, *, default: int = 12000) -> int:
    return max(500, min(int(value or default), 30000))


def _normalize_domains(domains: Iterable[str] | None) -> list[str]:
    items: list[str] = []
    for value in domains or []:
        text = str(value or "").strip().lower()
        if not text:
            continue
        if text.startswith("http://") or text.startswith("https://"):
            text = urlparse(text).netloc.lower()
        items.append(text.lstrip("."))
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _host_matches_policy(host: str, pattern: str) -> bool:
    normalized_host = str(host or "").lower().strip()
    normalized_pattern = str(pattern or "").lower().strip().lstrip(".")
    if not normalized_host or not normalized_pattern:
        return False
    return normalized_host == normalized_pattern or normalized_host.endswith(
        f".{normalized_pattern}"
    )


def _matches_domain(url: str, domains: list[str]) -> bool:
    if not domains:
        return True
    host = urlparse(url).netloc.lower()
    return any(_host_matches_policy(host, domain) for domain in domains)


def _parse_pub_date(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _matches_recency(value: str, recency_days: int | None) -> bool:
    if not recency_days or recency_days <= 0:
        return True
    published_at = _parse_pub_date(value)
    if published_at is None:
        return False
    return published_at >= datetime.now(UTC) - timedelta(days=int(recency_days))


def _query_tokens(query: str) -> list[str]:
    lowered = str(query or "").lower()
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]{2,}", lowered)
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", lowered):
        chunk = chunk.strip()
        if not chunk:
            continue
        if len(chunk) <= 4:
            tokens.append(chunk)
            continue
        max_window = min(len(chunk), 4)
        min_window = 2
        for window in range(max_window, min_window - 1, -1):
            for start in range(0, len(chunk) - window + 1):
                tokens.append(chunk[start : start + window])
    seen: set[str] = set()
    result: list[str] = []
    for token in tokens:
        if token not in seen:
            seen.add(token)
            result.append(token)
    return result


def _host_labels(host: str) -> list[str]:
    return [label for label in str(host or "").lower().split(".") if label]


def _credibility_label(score: int) -> str:
    if score >= 80:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def _default_policy() -> _WebDomainPolicy:
    return _WebDomainPolicy(
        allowed_domains=[],
        denied_domains=[],
        preferred_domains=[],
        official_domains=[],
        recommendations=[],
    )


def _load_domain_policy(policy_path: str | None) -> _WebDomainPolicy:
    if not policy_path:
        return _default_policy()
    path = Path(policy_path)
    if not path.exists():
        return _default_policy()
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    search_block = payload.get("search") if isinstance(payload.get("search"), dict) else {}
    recommendation_blocks = search_block.get("domain_recommendations") or []
    recommendations: list[_DomainRecommendation] = []
    for item in recommendation_blocks:
        if not isinstance(item, dict):
            continue
        recommendations.append(
            _DomainRecommendation(
                name=str(item.get("name") or "").strip(),
                match=[
                    str(value).strip().lower()
                    for value in item.get("match") or []
                    if str(value).strip()
                ],
                domains=_normalize_domains(item.get("domains") or []),
            )
        )
    return _WebDomainPolicy(
        allowed_domains=_normalize_domains(search_block.get("allowed_domains") or []),
        denied_domains=_normalize_domains(search_block.get("denied_domains") or []),
        preferred_domains=_normalize_domains(search_block.get("preferred_domains") or []),
        official_domains=_normalize_domains(search_block.get("official_domains") or []),
        recommendations=recommendations,
    )


def _filter_navigation_links(links: list[_PageLink]) -> list[_PageLink]:
    if not links:
        return []
    filtered: list[_PageLink] = []
    for item in links:
        text = str(item.text or "").strip()
        url = str(item.url or "").strip()
        text_lower = text.lower()
        if not text or len(text) < 2:
            continue
        if text_lower in _NAV_LINK_TEXT:
            continue
        if url.startswith(("javascript:", "mailto:")):
            continue
        if urlparse(url).fragment:
            continue
        filtered.append(item)
    main_links = [item for item in filtered if item.in_main]
    return main_links if len(main_links) >= 3 else filtered

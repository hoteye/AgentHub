from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class _SearchResult:
    title: str
    url: str
    snippet: str
    published_at: str
    source_domain: str


@dataclass(frozen=True)
class _PageLink:
    id: int
    text: str
    url: str
    in_main: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "url": self.url,
            "in_main": self.in_main,
        }


@dataclass(frozen=True)
class _DomainRecommendation:
    name: str
    match: list[str]
    domains: list[str]


@dataclass(frozen=True)
class _WebDomainPolicy:
    allowed_domains: list[str]
    denied_domains: list[str]
    preferred_domains: list[str]
    official_domains: list[str]
    recommendations: list[_DomainRecommendation]

    def recommended_domains(self, query: str) -> list[str]:
        lowered = str(query or "").lower()
        results: list[str] = []
        seen: set[str] = set()
        for item in self.recommendations:
            if not item.match:
                continue
            if not any(token and token in lowered for token in item.match):
                continue
            for domain in item.domains:
                if domain not in seen:
                    seen.add(domain)
                    results.append(domain)
        return results

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_domains": list(self.allowed_domains),
            "denied_domains": list(self.denied_domains),
            "preferred_domains": list(self.preferred_domains),
            "official_domains": list(self.official_domains),
            "recommendations": [
                {
                    "name": item.name,
                    "match": list(item.match),
                    "domains": list(item.domains),
                }
                for item in self.recommendations
            ],
        }


@dataclass
class _PageSnapshot:
    ref_id: str
    url: str
    final_url: str
    source_domain: str
    title: str
    content_type: str
    text: str
    lines: list[str]
    links: list[_PageLink]
    source_scope: str

    def excerpt(self, line: int, *, radius: int = 8) -> dict[str, Any]:
        if not self.lines:
            return {"requested_line": 1, "line_start": 1, "line_end": 0, "excerpt_lines": []}
        safe_line = max(1, min(int(line or 1), len(self.lines)))
        start = max(1, safe_line - radius)
        end = min(len(self.lines), safe_line + radius)
        excerpt_lines = [
            {"line": line_no, "text": self.lines[line_no - 1]} for line_no in range(start, end + 1)
        ]
        return {
            "requested_line": safe_line,
            "line_start": start,
            "line_end": end,
            "excerpt_lines": excerpt_lines,
        }

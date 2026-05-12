from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class SearchCase:
    case_id: str
    query: str
    prompt: str
    expected_domains: tuple[str, ...]
    expected_url_substrings: tuple[str, ...] = ()


CASES: tuple[SearchCase, ...] = (
    SearchCase(
        case_id="python_official",
        query="Python programming language",
        prompt=(
            "Use web search to find the official homepage for the Python programming language. "
            'Reply with compact JSON only: {"answer":"...","domain":"...","url":"..."}.'
        ),
        expected_domains=("python.org",),
    ),
    SearchCase(
        case_id="nodejs_official",
        query="Node.js website",
        prompt=(
            "Use web search to find the official website for Node.js. "
            'Reply with compact JSON only: {"answer":"...","domain":"...","url":"..."}.'
        ),
        expected_domains=("nodejs.org",),
    ),
    SearchCase(
        case_id="rust_official",
        query="Rust programming language website",
        prompt=(
            "Use web search to find the official website for the Rust programming language. "
            'Reply with compact JSON only: {"answer":"...","domain":"...","url":"..."}.'
        ),
        expected_domains=("rust-lang.org",),
    ),
    SearchCase(
        case_id="postgresql_docs",
        query="PostgreSQL docs",
        prompt=(
            "Use web search to find the official PostgreSQL documentation homepage. "
            'Reply with compact JSON only: {"answer":"...","domain":"...","url":"..."}.'
        ),
        expected_domains=("postgresql.org",),
    ),
    SearchCase(
        case_id="kubernetes_docs",
        query="Kubernetes documentation",
        prompt=(
            "Use web search to find the official Kubernetes documentation homepage. "
            'Reply with compact JSON only: {"answer":"...","domain":"...","url":"..."}.'
        ),
        expected_domains=("kubernetes.io",),
    ),
    SearchCase(
        case_id="openai_codex_page",
        query="OpenAI Codex",
        prompt=(
            "Use web search to find the official OpenAI Codex product page. "
            'Reply with compact JSON only: {"answer":"...","domain":"...","url":"..."}.'
        ),
        expected_domains=("openai.com",),
        expected_url_substrings=("openai.com", "codex"),
    ),
    SearchCase(
        case_id="codex_desktop_open_source_issue",
        query="OpenAI Codex desktop app open source GitHub issue 10733",
        prompt=(
            "Use web search to find the authoritative GitHub issue about whether the OpenAI Codex desktop app "
            'is open source. Reply with compact JSON only: {"answer":"...","domain":"...","url":"..."}.'
        ),
        expected_domains=("github.com",),
        expected_url_substrings=("github.com/openai/codex/issues/",),
    ),
)


def _host(url_or_domain: str) -> str:
    text = str(url_or_domain or "").strip()
    if not text:
        return ""
    parsed = urlparse(text if "://" in text else f"https://{text}")
    return str(parsed.netloc or parsed.path or "").lower().removeprefix("www.")


def _host_matches(host: str, expected_domain: str) -> bool:
    normalized_host = _host(host)
    expected = _host(expected_domain)
    return bool(
        normalized_host
        and expected
        and (normalized_host == expected or normalized_host.endswith(f".{expected}"))
    )


def _url_matches_expected(url: str, case: SearchCase) -> bool:
    lowered = str(url or "").lower()
    if case.expected_url_substrings:
        return all(substr.lower() in lowered for substr in case.expected_url_substrings)
    return any(_host_matches(_host(lowered), domain) for domain in case.expected_domains)


def _text_matches_expected(text: str, case: SearchCase) -> bool:
    lowered = str(text or "").lower()
    if case.expected_url_substrings:
        return all(substr.lower() in lowered for substr in case.expected_url_substrings)
    return any(domain.lower() in lowered for domain in case.expected_domains)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    candidates = [raw]
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _selected_cases(requested: list[str] | None) -> list[SearchCase]:
    if not requested:
        return list(CASES)
    wanted = {str(item or "").strip() for item in requested if str(item or "").strip()}
    return [case for case in CASES if case.case_id in wanted]

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from cli.agent_cli.runtime_services.expert_review_parse_runtime_pure_helpers_runtime import (
    _normalized_text,
    _normalized_token,
    _split_text_list,
)
from cli.agent_cli.runtime_services.expert_review_result_runtime import (
    EXPERT_REVIEW_FINDING_CATEGORIES,
    EXPERT_REVIEW_FINDING_SEVERITIES,
)


_FIELD_PREFIX_RE = re.compile(
    r"^\s*(?:verdict|decision|recommendation|review verdict|confidence|summary|rationale|"
    r"recommended action|action|findings?)\s*(?:[:=-]|\bis\b)",
    re.IGNORECASE,
)
_BULLET_RE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.+?)\s*$")
_FINDING_LINE_RE = re.compile(
    r"^\s*(?:finding|issue|concern|observation|risk)(?:\s+\d+)?\s*[:=-]\s*(.+?)\s*$",
    re.IGNORECASE,
)
_FINDINGS_HEADING_RE = re.compile(r"^\s*findings?\s*(?:[:=-]\s*(.*))?$", re.IGNORECASE)

_VERDICT_PATTERN_MAP = (
    (re.compile(r"\b(?:accept|accepted|approve|approved|pass)\b", re.IGNORECASE), "accept"),
    (
        re.compile(
            r"\b(?:revise|revision|needs[\s_-]+revision|changes[\s_-]+requested|fix)\b",
            re.IGNORECASE,
        ),
        "revise",
    ),
    (re.compile(r"\b(?:block|blocked|reject|rejected|fail)\b", re.IGNORECASE), "block"),
    (
        re.compile(
            r"\b(?:uncertain|unsure|inconclusive|unknown|cannot\s+determine)\b",
            re.IGNORECASE,
        ),
        "uncertain",
    ),
)
_CONFIDENCE_PATTERN_MAP = (
    (re.compile(r"\bhigh\b", re.IGNORECASE), "high"),
    (re.compile(r"\b(?:medium|moderate|med)\b", re.IGNORECASE), "medium"),
    (re.compile(r"\blow\b", re.IGNORECASE), "low"),
)


def _first_line_verdict_candidate(text: str) -> str:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _FIELD_PREFIX_RE.match(line):
            return ""
        verdict = _canonical_verdict_candidate(line, allow_raw=False)
        if verdict:
            return verdict
        return ""
    return ""


def _parsed_text_findings(text: str) -> list[dict[str, Any]]:
    blocks: list[str] = []
    current_block: list[str] = []
    in_findings_section = False

    def flush_current() -> None:
        nonlocal current_block
        if not current_block:
            return
        block = " ".join(current_block).strip()
        if block:
            blocks.append(block)
        current_block = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            flush_current()
            continue

        heading_match = _FINDINGS_HEADING_RE.match(stripped)
        if heading_match:
            flush_current()
            in_findings_section = True
            remainder = _normalized_text(heading_match.group(1))
            if remainder and remainder not in {"none", "no findings", "n/a"}:
                current_block = [heading_match.group(1).strip()]
            continue

        if _FIELD_PREFIX_RE.match(stripped):
            flush_current()
            if in_findings_section:
                in_findings_section = False
            continue

        bullet_match = _BULLET_RE.match(stripped) or _FINDING_LINE_RE.match(stripped)
        if bullet_match:
            flush_current()
            current_block = [bullet_match.group(1).strip()]
            continue

        if in_findings_section:
            if current_block:
                current_block.append(stripped)
            else:
                current_block = [stripped]

    flush_current()
    return [
        _parse_text_finding(block, index=index)
        for index, block in enumerate(blocks, start=1)
    ]


def _parse_text_finding(block: str, *, index: int) -> dict[str, Any]:
    text = block.strip()
    severity = ""
    category = ""
    evidence_refs: list[str] = []

    bracket_tags = re.findall(r"\[([^\]]+)\]", text)
    if bracket_tags:
        for tag in bracket_tags:
            normalized_tag = _normalized_token(tag)
            if not severity and normalized_tag in EXPERT_REVIEW_FINDING_SEVERITIES:
                severity = normalized_tag
                continue
            if not category and normalized_tag in EXPERT_REVIEW_FINDING_CATEGORIES:
                category = normalized_tag
        text = re.sub(r"\[[^\]]+\]\s*", "", text).strip()

    severity_value, severity_present = _inline_field_value(
        text,
        field="severity",
        allowed=EXPERT_REVIEW_FINDING_SEVERITIES,
    )
    if severity_present:
        severity = severity or severity_value
        text = _remove_inline_field(text, field="severity")

    category_value, category_present = _inline_field_value(
        text,
        field="category",
        allowed=EXPERT_REVIEW_FINDING_CATEGORIES,
    )
    if category_present:
        category = category or category_value
        text = _remove_inline_field(text, field="category")

    evidence_match = re.search(
        r"\b(?:evidence(?:[_\s-]*refs?)?|refs?)\s*[:=-]\s*(.+?)\s*$",
        text,
        re.IGNORECASE,
    )
    if evidence_match:
        evidence_refs = _split_text_list(evidence_match.group(1))
        text = text[: evidence_match.start()].rstrip(" ;,-")

    title = ""
    detail = text.strip()
    for separator in (" - ", ": "):
        if separator not in detail:
            continue
        candidate_title, candidate_detail = detail.split(separator, 1)
        if _normalized_text(candidate_title) and _normalized_text(candidate_detail):
            title = candidate_title.strip()
            detail = candidate_detail.strip()
            break

    finding: dict[str, Any] = {"detail": detail}
    if severity:
        finding["severity"] = severity
    if category:
        finding["category"] = category
    if title:
        finding["title"] = title
    if evidence_refs:
        finding["evidence_refs"] = evidence_refs
    if not detail and not title:
        finding["title"] = f"Finding {index}"
    return finding


def _inline_field_value(
    text: str,
    *,
    field: str,
    allowed: Sequence[str],
) -> tuple[str, bool]:
    match = re.search(
        rf"\b{re.escape(field)}\s*[:=-]\s*([A-Za-z_\- ]+)\b",
        text,
        re.IGNORECASE,
    )
    if not match:
        return "", False
    normalized_value = _normalized_token(match.group(1))
    if normalized_value in allowed:
        return normalized_value, True
    return normalized_value, True


def _remove_inline_field(text: str, *, field: str) -> str:
    return re.sub(
        rf"\b{re.escape(field)}\s*[:=-]\s*[A-Za-z_\- ]+\b[;,]?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()


def _canonical_verdict_candidate(value: Any, *, allow_raw: bool = True) -> str:
    normalized = _normalized_text(value)
    if not normalized:
        return ""
    matched = _matched_verdict_candidate(normalized)
    if matched:
        return matched
    return normalized if allow_raw else ""


def _matched_verdict_candidate(value: Any) -> str:
    normalized = _normalized_text(value)
    if not normalized:
        return ""
    for pattern, verdict in _VERDICT_PATTERN_MAP:
        if pattern.search(normalized):
            return verdict
    return ""


def _canonical_confidence_candidate(value: Any) -> str:
    normalized = _normalized_text(value)
    if not normalized:
        return ""
    for pattern, confidence in _CONFIDENCE_PATTERN_MAP:
        if pattern.search(normalized):
            return confidence
    return normalized


__all__ = [
    "_BULLET_RE",
    "_canonical_confidence_candidate",
    "_canonical_verdict_candidate",
    "_CONFIDENCE_PATTERN_MAP",
    "_FIELD_PREFIX_RE",
    "_FINDINGS_HEADING_RE",
    "_FINDING_LINE_RE",
    "_first_line_verdict_candidate",
    "_inline_field_value",
    "_matched_verdict_candidate",
    "_parse_text_finding",
    "_parsed_text_findings",
    "_remove_inline_field",
    "_VERDICT_PATTERN_MAP",
]

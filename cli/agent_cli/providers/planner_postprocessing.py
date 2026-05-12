from __future__ import annotations

import re
from typing import Sequence

from cli.agent_cli.providers.planner_tool_events import (
    executed_item_event_context_blocks,
    generic_tool_event_context_blocks,
    generic_tool_event_summary_lines,
    structured_tool_fallback_text,
)


COMMON_CONCISE_ANSWER_RULES: tuple[str, ...] = (
    "Answer the user's question directly in the first sentence.",
    "Do not use markdown headings, horizontal rules, or tables unless the user explicitly asks for them.",
    "Prefer short paragraphs and plain bullet lists over section titles like ## or ###.",
    "For one factual lookup or one metric request, return only the requested fact plus minimal source context.",
    "Do not summarize unrelated page content.",
    "Never repeat raw tool status phrases such as web page loaded, page opened, link opened, or results=5.",
)


GENERIC_SYNTHESIS_RULES: tuple[str, ...] = (
    "You already have the completed tool results for the current turn.",
    "Do not call more tools.",
    "Do not describe tool-call mechanics.",
    "Answer the original user request directly in concise Chinese.",
    "Put the main answer in the first sentence.",
    "Do not use markdown headings, horizontal rules, or tables unless the user explicitly asks for them.",
    "Prefer short paragraphs and plain bullet lists over section titles like ## or ###.",
    "If the user asked for one exact metric or fact, return only that fact and minimal source context.",
    "Do not summarize unrelated page content.",
    "Never repeat raw tool status phrases such as web page loaded or page opened.",
    "If the result is insufficient, say exactly what is missing.",
)


def concise_answer_prompt_text() -> str:
    return " ".join(COMMON_CONCISE_ANSWER_RULES)


def sanitize_final_answer_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    raw_lines = _flatten_markdown_heavy_answer(text.splitlines())
    text = "\n".join(raw_lines).strip()
    text = re.sub(r"\n+\s*(?:policy matches|matches|tool result)\s*=\s*\d+\s*$", "", text, flags=re.IGNORECASE)
    return text.strip()


_HEADING_LINE_RE = re.compile(r"^\s*#{1,6}\s+(.*\S)\s*$")
_RULE_LINE_RE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
_FENCE_LINE_RE = re.compile(r"^\s*(```|~~~)")
_LIST_LINE_RE = re.compile(r"^\s*(?:[-+*]|\d+[.)])\s+")


def _flatten_markdown_heavy_answer(raw_lines: Sequence[str]) -> List[str]:
    lines = [str(line).rstrip() for line in list(raw_lines or [])]
    heading_count = sum(1 for line in lines if _HEADING_LINE_RE.match(line))
    rule_count = sum(1 for line in lines if _RULE_LINE_RE.match(line))
    if heading_count + rule_count <= 1:
        return _collapse_blank_lines(lines)

    flattened: List[str] = []
    in_fence = False
    for index, line in enumerate(lines):
        if _FENCE_LINE_RE.match(line):
            in_fence = not in_fence
            flattened.append(line)
            continue
        if in_fence:
            flattened.append(line)
            continue
        if _RULE_LINE_RE.match(line):
            if flattened and flattened[-1] != "":
                flattened.append("")
            continue
        heading_match = _HEADING_LINE_RE.match(line)
        if heading_match:
            title = heading_match.group(1).strip()
            if not title:
                continue
            if flattened and flattened[-1] != "":
                flattened.append("")
            flattened.append(_flatten_heading_text(title, lines=lines, index=index))
            flattened.append("")
            continue
        flattened.append(line)
    return _collapse_blank_lines(flattened)


def _flatten_heading_text(title: str, *, lines: Sequence[str], index: int) -> str:
    normalized = str(title or "").strip()
    if not normalized:
        return ""
    if normalized.endswith(("：", ":", "。", "！", "？", "!", "?")):
        return normalized
    for candidate in lines[index + 1 :]:
        stripped = str(candidate or "").strip()
        if not stripped:
            continue
        if _LIST_LINE_RE.match(stripped):
            return f"{normalized}："
        return f"{normalized}："
    return normalized


def _collapse_blank_lines(lines: Sequence[str]) -> List[str]:
    collapsed: List[str] = []
    last_blank = True
    for line in list(lines or []):
        text = str(line or "").rstrip()
        blank = not text.strip()
        if blank:
            if last_blank:
                continue
            collapsed.append("")
            last_blank = True
            continue
        collapsed.append(text)
        last_blank = False
    while collapsed and not collapsed[0].strip():
        collapsed.pop(0)
    while collapsed and not collapsed[-1].strip():
        collapsed.pop()
    return collapsed

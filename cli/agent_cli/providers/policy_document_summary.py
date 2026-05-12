from __future__ import annotations

import re
from typing import Any, Dict, List


class PolicyDocumentSummaryMixin:
    @staticmethod
    def _policy_compact_cjk_spacing(text: str) -> str:
        value = str(text or "").strip()
        previous = ""
        while value != previous:
            previous = value
            value = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", value)
        return value

    @classmethod
    def _policy_clean_heading(cls, raw_line: str) -> str:
        line = re.sub(r"^#+\s*", "", str(raw_line or "")).strip()
        line = re.sub(r"\s+", " ", line)
        match = re.match(r"^(第[一二三四五六七八九十百千万0-9]+章)\s*(.*?)(?:\s+\d+)?$", line)
        if not match:
            return ""
        chapter = match.group(1).strip()
        suffix = cls._policy_compact_cjk_spacing(match.group(2))
        return f"{chapter} {suffix}".strip()

    @classmethod
    def _policy_clean_summary_line(cls, raw_line: str) -> str:
        line = re.sub(r"^#+\s*", "", str(raw_line or "")).strip()
        line = re.sub(r"\s+", " ", line)
        line = re.sub(r"\s+\d+$", "", line).strip()
        return cls._policy_compact_cjk_spacing(line)

    @classmethod
    def _policy_outline_headings(cls, text: str, *, limit: int = 8) -> List[str]:
        headings: List[str] = []
        seen: set[str] = set()
        for raw_line in str(text or "").splitlines():
            line = cls._policy_clean_heading(raw_line)
            if not line:
                continue
            if line in seen:
                continue
            seen.add(line)
            headings.append(line)
            if len(headings) >= limit:
                break
        return headings

    @classmethod
    def _policy_lead_sentence(cls, text: str) -> str:
        primary_purpose_markers = ("制定本办法", "制定本细则", "制定本制度")
        secondary_purpose_markers = ("适用于", "规范", "明确", "建立", "加强")
        skip_lines = {"目录", "目 录", "目  录", "总则", "术语定义", "附则"}
        purpose_candidates: List[str] = []
        fallback_sentences: List[str] = []
        for raw_line in str(text or "").splitlines():
            line = cls._policy_clean_summary_line(raw_line)
            if not line or line in skip_lines:
                continue
            if cls._policy_clean_heading(raw_line):
                continue
            if re.fullmatch(r"[0-9一二三四五六七八九十百千万]+", line):
                continue
            if "管理办法" in line and "。" not in line and "！" not in line and "？" not in line:
                continue
            sentences = [item.strip() for item in re.split(r"(?<=[。！？；])", line) if item.strip()]
            for sentence in sentences:
                item = sentence.strip()
                if not re.search(r"[。！？；]$", item):
                    item = item + "。"
                if len(item) < 16 or len(item) > 200:
                    continue
                if any(marker in item for marker in primary_purpose_markers):
                    return item
                if any(marker in item for marker in secondary_purpose_markers):
                    purpose_candidates.append(item)
                    continue
                fallback_sentences.append(item)
        for item in purpose_candidates:
            if 16 <= len(item) <= 200:
                return item
        for item in fallback_sentences:
            if 16 <= len(item) <= 80:
                return item
        return ""

    def _policy_summary_fast_answer_v2(self, evidence_blocks: List[Dict[str, Any]]) -> str:
        if not evidence_blocks:
            return ""
        block = evidence_blocks[0]
        title = str(block.get("title") or block.get("doc_id") or "命中文档").strip()
        text = str(block.get("raw_text") or block.get("text") or "").strip()
        if not text:
            return ""
        headings = self._policy_outline_headings(text)
        lead = self._policy_lead_sentence(text)
        lines = [f"《{title}》主要内容可以概括为："]
        if lead:
            lines.append(lead)
        if headings:
            lines.append("核心章节包括：")
            lines.extend(f"- {heading}" for heading in headings[:8])
        else:
            lines.append("从正文开头看，它主要规定了适用范围、职责分工、管理要求和监督检查等内容。")
        lines.append("如果你需要，我可以继续按某一章或提炼成要点版。")
        return "\n".join(lines)

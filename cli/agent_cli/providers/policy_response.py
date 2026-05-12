from __future__ import annotations

import re
from typing import Any, Dict, List

from cli.agent_cli.models import ToolEvent
from cli.agent_cli.providers.planner_postprocessing import sanitize_final_answer_text


class PolicyResponseMixin:
    @classmethod
    def _unsupported_policy_claims(cls, answer_text: str, evidence_blocks: List[Dict[str, Any]]) -> List[str]:
        def _normalize_token(value: str) -> str:
            text_value = str(value or "").strip()
            text_value = text_value.replace("《", "").replace("》", "")
            text_value = re.sub(r"^[0-9]+\.", "", text_value)
            text_value = re.sub(r"\s+", "", text_value)
            return text_value

        text = str(answer_text or "").strip()
        if not text or not evidence_blocks:
            return []
        corpus = cls._policy_evidence_corpus(evidence_blocks)
        normalized_corpus = _normalize_token(corpus)
        unsupported: List[str] = []
        seen: set[str] = set()
        for pattern in (
            r"《[^》]{2,80}》",
            r"第[一二三四五六七八九十百千万零〇0-9]+条",
            r"\d+\s*(?:天|日|个月|月|季度|年)",
        ):
            for match in re.findall(pattern, text):
                token = str(match or "").strip()
                if not token or token in seen:
                    continue
                seen.add(token)
                normalized_token = _normalize_token(token)
                if normalized_token and normalized_token not in normalized_corpus:
                    unsupported.append(token)
        return unsupported

    def _policy_answer_contradictions_v2(
        self,
        user_text: str,
        answer_text: str,
        evidence_blocks: List[Dict[str, Any]],
    ) -> List[str]:
        text = str(answer_text or "").strip()
        question = str(user_text or "").strip()
        if not text or not question or not evidence_blocks:
            return []

        negative_markers = (
            "未找到直接依据",
            "未找到直接证据",
            "未规定具体",
            "未包含",
            "无法确定",
            "不能确定",
            "证据不足",
        )
        asks_time_requirement = self._policy_asks_time_requirement(question)
        if not asks_time_requirement:
            return []
        time_patterns = self._policy_time_patterns_v2()
        answer_has_explicit_time = any(re.search(pattern, text) for pattern in time_patterns)
        answer_is_negative = any(marker in text for marker in negative_markers)
        for block in evidence_blocks:
            corpus = "\n".join(
                part
                for part in (
                    str(block.get("priority_excerpt") or ""),
                    self._policy_targeted_snippet_v2(block, user_text=user_text, limit=220),
                    str(block.get("text") or ""),
                    str(block.get("excerpt") or ""),
                    str(block.get("evidence_summary") or ""),
                )
                if part
            )
            if any(re.search(pattern, corpus) for pattern in time_patterns) and (answer_is_negative or not answer_has_explicit_time):
                return ["contradiction:time_requirement"]
        return []

    @staticmethod
    def _policy_asks_time_requirement(user_text: str) -> bool:
        question = str(user_text or "").strip()
        return any(token in question for token in ("多久", "频次", "周期", "至少", "多长时间", "多久一次"))

    @staticmethod
    def _policy_time_patterns_v2() -> tuple[str, ...]:
        return (
            r"至少每[^\n。；，]{0,12}(?:天|周|月|个月|季度|年)",
            r"每[一二三四五六七八九十百\d]+(?:个)?(?:天|周|月|季度|年)",
            r"不少于[一二三四五六七八九十百\d]+(?:个)?(?:天|周|月|个月|季度|年)",
            r"最长为[一二三四五六七八九十百\d]+(?:个)?(?:天|周|月|个月|季度|年)",
            r"每半年",
            r"每季度",
            r"每年",
            r"每月",
            r"每周",
        )

    @staticmethod
    def _policy_pattern_windows_v2(text: str, patterns: tuple[str, ...]) -> List[str]:
        source = str(text or "")
        if not source:
            return []
        separators = "。！？；\n"
        windows: List[str] = []
        seen: set[str] = set()
        for pattern in patterns:
            for match in re.finditer(pattern, source):
                start = 0
                for separator in separators:
                    boundary = source.rfind(separator, 0, match.start())
                    if boundary >= 0:
                        start = max(start, boundary + 1)
                end_candidates = [source.find(separator, match.end()) for separator in separators]
                end_candidates = [candidate for candidate in end_candidates if candidate >= 0]
                end = min(end_candidates) + 1 if end_candidates else len(source)
                window = re.sub(r"\s+", " ", source[start:end]).strip()
                if window and window not in seen:
                    seen.add(window)
                    windows.append(window)
        return windows

    @classmethod
    def _policy_evidence_summary_lines(cls, evidence_blocks: List[Dict[str, Any]]) -> List[str]:
        lines: List[str] = []
        for index, block in enumerate(evidence_blocks[:5], start=1):
            title = str(block.get("title") or block.get("doc_id") or f"evidence-{index}").strip()
            snippet = cls._policy_snippet(block, limit=220)
            line = f"{index}. {title}"
            if snippet:
                line += f": {snippet}"
            lines.append(line)
        return lines

    @staticmethod
    def _sanitize_final_answer_text(value: str) -> str:
        return sanitize_final_answer_text(value)

    @staticmethod
    def _policy_answer_coverage_issues(answer_text: str, evidence_profile: Dict[str, Any]) -> List[str]:
        text = str(answer_text or "").strip()
        if not text:
            return []
        header_map = {
            "governance_base": "上位制度依据",
            "direct_rule": "直接适用制度",
            "supporting_reference": "补充参考",
        }
        groups = evidence_profile.get("groups") if isinstance(evidence_profile.get("groups"), dict) else {}
        issues: List[str] = []
        for group in list(evidence_profile.get("required_groups") or []):
            header = header_map.get(group, "")
            if header and header not in text:
                issues.append(f"missing_section:{group}")
                continue
            titles = [str(item.get("title") or "").strip() for item in list(groups.get(group) or [])[:2]]
            titles = [title for title in titles if title]
            if titles and not any(title in text for title in titles):
                issues.append(f"missing_evidence:{group}")
        return issues

    @staticmethod
    def _policy_answer_coverage_issues_v2(answer_text: str, evidence_profile: Dict[str, Any]) -> List[str]:
        text = str(answer_text or "").strip()
        if not text:
            return []
        header_map = {
            "primary_basis": "主依据",
            "scenario_basis": "场景补充依据",
            "supporting_reference": "补充参考",
        }
        sections = (
            evidence_profile.get("answer_sections")
            if isinstance(evidence_profile.get("answer_sections"), dict)
            else {}
        )
        issues: List[str] = []
        valid_evidence_ids = {
            str(item.get("evidence_id") or "").strip().upper()
            for docs in list(sections.values())
            for item in list(docs or [])
            if str(item.get("evidence_id") or "").strip()
        }
        for section in list(evidence_profile.get("required_sections") or []):
            header = header_map.get(section, "")
            if header and header not in text:
                issues.append(f"missing_section:{section}")
                continue
            titles = [str(item.get("title") or "").strip() for item in list(sections.get(section) or [])[:2]]
            titles = [title for title in titles if title]
            evidence_ids = [
                str(item.get("evidence_id") or "").strip().upper()
                for item in list(sections.get(section) or [])[:2]
                if str(item.get("evidence_id") or "").strip()
            ]
            has_title = any(title in text for title in titles)
            has_evidence_id = any(f"[{evidence_id}]" in text.upper() for evidence_id in evidence_ids)
            if (titles or evidence_ids) and not (has_title or has_evidence_id):
                issues.append(f"missing_evidence:{section}")
        for evidence_id in re.findall(r"\[(E\d+)\]", text, flags=re.IGNORECASE):
            if evidence_id.upper() not in valid_evidence_ids:
                issues.append(f"unknown_evidence_id:{evidence_id.upper()}")
                break
        for title in list(evidence_profile.get("discarded_titles") or [])[:10]:
            if title and title in text:
                issues.append(f"unselected_evidence:{title}")
                break
        return issues

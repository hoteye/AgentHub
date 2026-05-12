from __future__ import annotations

import re
from typing import Any, Dict, List


class PolicyAnswerSnippetsMixin:
    def _policy_targeted_snippet_v2(self, block: Dict[str, Any], *, user_text: str = "", limit: int = 180) -> str:
        preferred_text = "\n".join(
            part
            for part in (
                str(block.get("text") or ""),
                str(block.get("excerpt") or ""),
                str(block.get("evidence_summary") or ""),
                str(block.get("summary") or ""),
            )
            if part
        ).strip()
        if not preferred_text:
            return ""
        primary_anchors: List[str] = []
        for term in list(block.get("matched_terms") or []):
            value = str(term or "").strip()
            if value and value not in primary_anchors:
                primary_anchors.append(value)
        question_text = str(user_text or "").strip()
        if question_text:
            for term in self._policy_query_terms(question_text):
                if term and term not in primary_anchors:
                    primary_anchors.append(term)
            for marker in ("多久", "频次", "周期", "至少", "多长时间", "多久一次", "时限", "期限"):
                if marker in question_text and marker not in primary_anchors:
                    primary_anchors.append(marker)
        for source in list(block.get("source_queries") or []):
            for term in self._policy_query_terms(str(source or "")):
                if term and term not in primary_anchors:
                    primary_anchors.append(term)
        secondary_anchors: List[str] = []
        title_query = "\n".join(
            part for part in (str(block.get("title") or ""), str(block.get("source_name") or "")) if part
        )
        for term in self._policy_query_terms(title_query)[:10]:
            if term and term not in primary_anchors and term not in secondary_anchors:
                secondary_anchors.append(term)
        primary_anchors = [term for term in primary_anchors if len(term) >= 2][:16]
        secondary_anchors = [term for term in secondary_anchors if len(term) >= 2][:8]
        if not primary_anchors and not secondary_anchors:
            return self._policy_snippet(block, limit=limit)
        asks_time_requirement = self._policy_asks_time_requirement(question_text) or any(
            token in anchor for anchor in primary_anchors for token in ("多久", "频次", "周期", "至少", "多长时间", "多久一次")
        )
        time_patterns = self._policy_time_patterns_v2()

        time_chunks = self._policy_pattern_windows_v2(preferred_text, time_patterns) if asks_time_requirement else []
        chunks = time_chunks or [
            chunk.strip()
            for chunk in re.split(r"(?<=[。！？；\n])", preferred_text)
            if str(chunk or "").strip()
        ]
        if not chunks:
            return self._policy_snippet(block, limit=limit)

        def _chunk_score(text: str) -> tuple[int, int, int]:
            lowered = text.lower()
            matched_primary = [term for term in primary_anchors if term.lower() in lowered]
            matched_secondary = [term for term in secondary_anchors if term.lower() in lowered]
            if not matched_primary and not matched_secondary:
                return (0, 0, -len(text))
            weighted = sum(min(len(term), 12) * 4 for term in matched_primary) + sum(
                min(len(term), 12) for term in matched_secondary
            )
            if asks_time_requirement and any(re.search(pattern, text) for pattern in time_patterns):
                weighted += 200
            distinct = len({term.lower() for term in [*matched_primary, *matched_secondary]})
            return (weighted, distinct, -len(text))

        candidate_indexes = list(range(len(chunks)))

        best_index = -1
        best_score = (0, 0, 0)
        for index in candidate_indexes:
            chunk = chunks[index]
            score = _chunk_score(chunk)
            if score > best_score:
                best_score = score
                best_index = index
        if best_index < 0 and asks_time_requirement and candidate_indexes:
            best_index = candidate_indexes[0]
            best_score = _chunk_score(chunks[best_index])
        if best_index >= 0 and (best_score[0] > 0 or (asks_time_requirement and candidate_indexes)):
            snippet = chunks[best_index]
            if best_index + 1 < len(chunks) and not time_chunks:
                next_chunk = chunks[best_index + 1]
                next_score = _chunk_score(next_chunk)
                if next_score[0] > 0 and len(snippet) + 1 + len(next_chunk) <= limit:
                    snippet = f"{snippet} {next_chunk}".strip()
            if len(snippet) > limit:
                snippet = snippet[:limit].rstrip() + "..."
            return snippet
        return self._policy_snippet(block, limit=limit)

    def _policy_answer_focus_hints_v2(
        self,
        user_text: str,
        evidence_blocks: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        asks_time_requirement = self._policy_asks_time_requirement(user_text)
        highlights: List[Dict[str, str]] = []
        time_patterns = self._policy_time_patterns_v2()
        for block in evidence_blocks[:3]:
            excerpt = str(block.get("priority_excerpt") or "").strip() or self._policy_targeted_snippet_v2(
                block,
                user_text=user_text,
                limit=220,
            )
            if not excerpt:
                continue
            if asks_time_requirement and not any(re.search(pattern, excerpt) for pattern in time_patterns):
                continue
            highlights.append(
                {
                    "evidence_id": str(block.get("evidence_id") or "").strip(),
                    "title": str(block.get("title") or block.get("doc_id") or "").strip(),
                    "excerpt": excerpt,
                }
            )
        return {
            "asks_time_requirement": asks_time_requirement,
            "highlights": highlights,
        }

    def _policy_section_summary_lines_v2(
        self,
        evidence_profile: Dict[str, Any],
        evidence_blocks: List[Dict[str, Any]],
    ) -> Dict[str, List[str]]:
        block_map = {
            (str(block.get("doc_id") or ""), str(block.get("title") or "")): block
            for block in evidence_blocks
        }
        section_lines: Dict[str, List[str]] = {
            "primary_basis": [],
            "scenario_basis": [],
            "supporting_reference": [],
        }
        for section, docs in dict(evidence_profile.get("answer_sections") or {}).items():
            for item in list(docs or [])[:2]:
                key = (str(item.get("doc_id") or ""), str(item.get("title") or ""))
                block = block_map.get(key, {})
                title = str(item.get("title") or "").strip()
                evidence_id = str(block.get("evidence_id") or item.get("evidence_id") or "").strip()
                snippet = str(block.get("priority_excerpt") or "").strip() or self._policy_targeted_snippet_v2(block, limit=180)
                line = f"- [{evidence_id}] {title or key[0]}" if evidence_id else f"- {title or key[0]}"
                if snippet:
                    line += f": {snippet}"
                matched_terms = list(block.get("matched_terms") or [])
                if matched_terms:
                    line += f" [matched: {', '.join(matched_terms[:4])}]"
                section_lines.setdefault(section, []).append(line)
        return section_lines

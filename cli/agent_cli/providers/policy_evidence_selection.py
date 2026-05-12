from __future__ import annotations

from typing import Any, Dict, List


class PolicyEvidenceSelectionMixin:
    def _policy_effective_evidence(self, user_text: str, evidence_blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not evidence_blocks:
            return []
        query_terms = self._policy_selection_query_terms(user_text, evidence_blocks)

        grouped: Dict[str, List[Dict[str, Any]]] = {
            "governance_base": [],
            "direct_rule": [],
            "supporting_reference": [],
        }
        for block in evidence_blocks:
            group = str(block.get("doc_group") or "supporting_reference")
            grouped.setdefault(group, []).append(dict(block))

        selected: List[Dict[str, Any]] = []
        has_normative = bool(grouped.get("governance_base") or grouped.get("direct_rule"))
        for group, max_items in (("governance_base", 2), ("direct_rule", 1), ("supporting_reference", 1)):
            candidates = list(grouped.get(group) or [])
            if not candidates:
                continue
            candidates.sort(key=lambda item: self._policy_selection_rank(item, query_terms), reverse=True)
            if group in {"governance_base", "direct_rule"}:
                positive_hits = [item for item in candidates if int(item.get("selection_query_hits") or 0) > 0]
                if positive_hits:
                    candidates = positive_hits
            if group == "supporting_reference" and has_normative:
                filtered = [
                    item
                    for item in candidates
                    if not bool(item.get("is_noise_candidate")) and int(item.get("selection_query_hits") or 0) > 0
                ]
                candidates = filtered or []
            selected.extend(candidates[:max_items])

        selected.sort(
            key=lambda item: (
                {"governance_base": 0, "direct_rule": 1, "supporting_reference": 2}.get(
                    str(item.get("doc_group") or "supporting_reference"),
                    9,
                ),
                -int(item.get("authority_rank") or 0),
                -int(item.get("query_term_hits") or 0),
                -float(item.get("score") or 0),
                str(item.get("title") or ""),
            )
        )
        for index, item in enumerate(selected, start=1):
            item["evidence_id"] = f"E{index}"
        return selected

    def _policy_effective_evidence_v2(self, user_text: str, evidence_blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not evidence_blocks:
            return []
        llm_rerank = self._policy_llm_rerank(user_text, evidence_blocks)
        rerank_by_index = {
            int(item.get("index") or 0): item
            for item in list(llm_rerank.get("ranked") or [])
            if int(item.get("index") or 0) > 0
        }
        query_terms = self._policy_selection_query_terms(user_text, evidence_blocks)

        grouped: Dict[str, List[Dict[str, Any]]] = {
            "governance_base": [],
            "direct_rule": [],
            "supporting_reference": [],
        }
        for candidate_index, block in enumerate(evidence_blocks, start=1):
            group = str(block.get("doc_group") or "supporting_reference")
            item = dict(block)
            rerank_item = rerank_by_index.get(candidate_index) or {}
            item["llm_basis_type"] = str(rerank_item.get("basis_type") or item.get("llm_basis_type") or "").strip()
            item["llm_relevance"] = int(rerank_item.get("relevance") or item.get("llm_relevance") or 0)
            item["llm_reason"] = str(rerank_item.get("reason") or item.get("llm_reason") or "").strip()
            if str(llm_rerank.get("issue_label") or "").strip():
                item["llm_issue_label"] = str(llm_rerank.get("issue_label") or "").strip()
            if list(llm_rerank.get("focus_terms") or []):
                item["llm_focus_terms"] = [str(term).strip() for term in list(llm_rerank.get("focus_terms") or []) if str(term).strip()]
            grouped.setdefault(group, []).append(item)

        selected: List[Dict[str, Any]] = []
        has_normative = bool(grouped.get("governance_base") or grouped.get("direct_rule"))
        governance_cap = 2
        if grouped.get("governance_base"):
            governance_candidates = [dict(item) for item in grouped.get("governance_base") or []]
            governance_candidates.sort(key=lambda item: self._policy_selection_rank_v2(item, query_terms), reverse=True)
            if int(governance_candidates[0].get("selection_semantic_score") or 0) >= 12:
                governance_cap = 1
        for group, max_items in (("governance_base", governance_cap), ("direct_rule", 1), ("supporting_reference", 1)):
            candidates = list(grouped.get(group) or [])
            if not candidates:
                continue
            candidates.sort(key=lambda item: self._policy_selection_rank_v2(item, query_terms), reverse=True)
            if group in {"governance_base", "direct_rule"}:
                positive_hits = [
                    item
                    for item in candidates
                    if int(item.get("selection_query_hits") or 0) > 0
                    or int(item.get("selection_semantic_score") or 0) > 0
                    or int(item.get("llm_relevance") or 0) >= 60
                ]
                if positive_hits:
                    candidates = positive_hits
            if group == "supporting_reference" and has_normative:
                filtered = [
                    item
                    for item in candidates
                    if not bool(item.get("is_noise_candidate"))
                    and str(item.get("llm_basis_type") or "").strip() != "noise"
                    and (
                        int(item.get("selection_query_hits") or 0) > 0
                        or int(item.get("selection_semantic_score") or 0) >= 6
                        or int(item.get("llm_relevance") or 0) >= 60
                    )
                ]
                candidates = filtered or []
            selected.extend(candidates[:max_items])

        selected.sort(
            key=lambda item: (
                {"primary_basis": 0, "scenario_basis": 1, "supporting_reference": 2, "noise": 3}.get(
                    str(item.get("llm_basis_type") or ""),
                    {"governance_base": 0, "direct_rule": 1, "supporting_reference": 2}.get(
                        str(item.get("doc_group") or "supporting_reference"),
                        9,
                    ),
                ),
                -int(item.get("llm_relevance") or 0),
                -int(item.get("selection_semantic_score") or 0),
                -int(item.get("authority_rank") or 0),
                -int(item.get("query_term_hits") or 0),
                -float(item.get("score") or 0),
                str(item.get("title") or ""),
            )
        )
        for index, item in enumerate(selected, start=1):
            item["evidence_id"] = f"E{index}"
            priority_excerpt = self._policy_targeted_snippet_v2(item, user_text=user_text, limit=220)
            if priority_excerpt:
                item["priority_excerpt"] = priority_excerpt
        return selected

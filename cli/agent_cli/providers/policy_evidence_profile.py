from __future__ import annotations

from typing import Any, Dict, List, Optional


class PolicyEvidenceProfileMixin:
    @classmethod
    def _policy_answer_sections(cls, evidence_blocks: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        sections: Dict[str, List[Dict[str, Any]]] = {
            "primary_basis": [],
            "scenario_basis": [],
            "supporting_reference": [],
        }
        grouped: Dict[str, List[Dict[str, Any]]] = {
            "governance_base": [],
            "direct_rule": [],
            "supporting_reference": [],
        }
        for block in evidence_blocks:
            grouped.setdefault(str(block.get("doc_group") or "supporting_reference"), []).append(block)

        primary_llm = [
            block
            for block in evidence_blocks
            if str(block.get("llm_basis_type") or "").strip() == "primary_basis" and not bool(block.get("is_noise_candidate"))
        ]
        scenario_llm = [
            block
            for block in evidence_blocks
            if str(block.get("llm_basis_type") or "").strip() == "scenario_basis" and not bool(block.get("is_noise_candidate"))
        ]
        support_llm = [
            block
            for block in evidence_blocks
            if str(block.get("llm_basis_type") or "").strip() == "supporting_reference" and not bool(block.get("is_noise_candidate"))
        ]

        primary_llm.sort(
            key=lambda item: (
                -int(item.get("llm_relevance") or 0),
                -int(item.get("authority_rank") or 0),
                -int(item.get("selection_semantic_score") or 0),
            )
        )
        scenario_llm.sort(
            key=lambda item: (
                -int(item.get("llm_relevance") or 0),
                -int(item.get("authority_rank") or 0),
                -int(item.get("selection_semantic_score") or 0),
            )
        )
        support_llm.sort(
            key=lambda item: (
                -int(item.get("llm_relevance") or 0),
                -int(item.get("authority_rank") or 0),
                -int(item.get("selection_semantic_score") or 0),
            )
        )

        governance = list(grouped.get("governance_base") or [])
        direct = list(grouped.get("direct_rule") or [])
        support = list(grouped.get("supporting_reference") or [])

        if primary_llm:
            sections["primary_basis"].append(primary_llm[0])
        if scenario_llm:
            primary_keys = {
                (str(block.get("doc_id") or ""), str(block.get("title") or ""))
                for block in sections["primary_basis"]
            }
            for block in scenario_llm:
                key = (str(block.get("doc_id") or ""), str(block.get("title") or ""))
                if key in primary_keys:
                    continue
                sections["scenario_basis"].append(block)
                break
        if support_llm:
            used_keys = {
                (str(block.get("doc_id") or ""), str(block.get("title") or ""))
                for docs in sections.values()
                for block in docs
            }
            for block in support_llm:
                key = (str(block.get("doc_id") or ""), str(block.get("title") or ""))
                if key in used_keys:
                    continue
                sections["supporting_reference"].append(block)
                break

        if sections["primary_basis"] and sections["scenario_basis"]:
            return sections

        if governance:
            sections["primary_basis"].append(governance[0])
        elif direct:
            sections["primary_basis"].append(direct[0])
            direct = direct[1:]

        primary_ids = {
            (str(block.get("doc_id") or ""), str(block.get("title") or ""))
            for block in sections["primary_basis"]
        }
        scenario_candidates = [
            block
            for block in direct
            if (str(block.get("doc_id") or ""), str(block.get("title") or "")) not in primary_ids
            and (
                int(block.get("selection_query_hits") or 0) > 0
                or int(block.get("selection_semantic_score") or 0) >= 8
            )
        ]
        if scenario_candidates:
            sections["scenario_basis"].append(scenario_candidates[0])

        support_candidates = [
            block
            for block in support
            if not bool(block.get("is_noise_candidate"))
            and str(block.get("doc_kind") or "") not in {"audit_workpaper", "training_material"}
            and (
                int(block.get("selection_query_hits") or 0) > 0
                or int(block.get("selection_semantic_score") or 0) >= 6
            )
        ]
        if support_candidates:
            sections["supporting_reference"].append(support_candidates[0])
        return sections

    @staticmethod
    def _policy_has_readable_normative_evidence(evidence_blocks: List[Dict[str, Any]]) -> bool:
        for block in evidence_blocks:
            if bool(block.get("is_noise_candidate")):
                continue
            if str(block.get("doc_group") or "") not in {"governance_base", "direct_rule"}:
                continue
            if str(block.get("text") or "").strip():
                return True
        return False

    @staticmethod
    def _policy_evidence_profile(evidence_blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        groups: Dict[str, List[Dict[str, Any]]] = {
            "governance_base": [],
            "direct_rule": [],
            "supporting_reference": [],
        }
        for block in evidence_blocks:
            group = str(block.get("doc_group") or "supporting_reference")
            groups.setdefault(group, []).append(
                {
                    "evidence_id": str(block.get("evidence_id") or ""),
                    "doc_id": str(block.get("doc_id") or ""),
                    "title": str(block.get("title") or ""),
                    "doc_kind": str(block.get("doc_kind") or ""),
                    "authority_rank": int(block.get("authority_rank") or 0),
                    "has_full_text": bool(block.get("text")),
                    "score": float(block.get("score") or 0),
                    "query_term_hits": int(block.get("query_term_hits") or 0),
                }
            )
        required_groups = [group for group in ("governance_base", "direct_rule") if groups.get(group)]
        if not required_groups and groups.get("supporting_reference"):
            required_groups = ["supporting_reference"]
        return {
            "groups": groups,
            "required_groups": required_groups,
            "available_groups": [group for group, docs in groups.items() if docs],
        }

    @staticmethod
    def _policy_evidence_corpus(evidence_blocks: List[Dict[str, Any]]) -> str:
        return "\n".join(
            part
            for block in evidence_blocks
            for part in (
                str(block.get("title") or ""),
                str(block.get("evidence_summary") or ""),
                str(block.get("excerpt") or ""),
                str(block.get("text") or ""),
                str(block.get("doc_id") or ""),
            )
            if part
        )

    def _policy_evidence_profile_v2(
        self,
        evidence_blocks: List[Dict[str, Any]],
        all_evidence_blocks: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        evidence_id_by_key = {
            (str(block.get("doc_id") or ""), str(block.get("title") or "")): str(block.get("evidence_id") or "")
            for block in evidence_blocks
        }
        groups: Dict[str, List[Dict[str, Any]]] = {
            "governance_base": [],
            "direct_rule": [],
            "supporting_reference": [],
        }
        for block in evidence_blocks:
            group = str(block.get("doc_group") or "supporting_reference")
            groups.setdefault(group, []).append(
                {
                    "evidence_id": evidence_id_by_key.get(
                        (str(block.get("doc_id") or ""), str(block.get("title") or "")),
                        str(block.get("evidence_id") or ""),
                    ),
                    "doc_id": str(block.get("doc_id") or ""),
                    "title": str(block.get("title") or ""),
                    "doc_kind": str(block.get("doc_kind") or ""),
                    "authority_rank": int(block.get("authority_rank") or 0),
                    "has_full_text": bool(block.get("text")),
                    "score": float(block.get("score") or 0),
                    "query_term_hits": int(block.get("query_term_hits") or 0),
                    "selection_semantic_score": int(block.get("selection_semantic_score") or 0),
                    "llm_basis_type": str(block.get("llm_basis_type") or ""),
                    "llm_relevance": int(block.get("llm_relevance") or 0),
                }
            )
        answer_sections = self._policy_answer_sections(evidence_blocks)
        for docs in answer_sections.values():
            for item in list(docs or []):
                key = (str(item.get("doc_id") or ""), str(item.get("title") or ""))
                evidence_id = evidence_id_by_key.get(key, "")
                if evidence_id:
                    item["evidence_id"] = evidence_id
        required_sections = [section for section in ("primary_basis", "scenario_basis") if answer_sections.get(section)]
        if not required_sections and answer_sections.get("supporting_reference"):
            required_sections = ["supporting_reference"]
        selected_titles = [
            str(block.get("title") or "").strip()
            for block in evidence_blocks
            if str(block.get("title") or "").strip()
        ]
        discarded_titles: List[str] = []
        if all_evidence_blocks is not None:
            seen_selected = set(selected_titles)
            seen_discarded: set[str] = set()
            for block in all_evidence_blocks:
                title = str(block.get("title") or "").strip()
                if not title or title in seen_selected or title in seen_discarded:
                    continue
                seen_discarded.add(title)
                discarded_titles.append(title)
        return {
            "groups": groups,
            "answer_sections": answer_sections,
            "required_sections": required_sections,
            "available_groups": [group for group, docs in groups.items() if docs],
            "selected_titles": selected_titles,
            "discarded_titles": discarded_titles,
        }

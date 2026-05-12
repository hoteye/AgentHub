from __future__ import annotations

from typing import Any, Dict, List


class PolicyEvidenceRankingMixin:
    @staticmethod
    def _policy_matched_terms(text: str, query_terms: List[str]) -> List[str]:
        haystack = str(text or "").lower()
        hits = [term for term in query_terms if term and term in haystack]
        hits.sort(key=lambda item: (-len(item), item))
        return hits[:8]

    @staticmethod
    def _policy_contains_any(text: str, terms: List[str] | tuple[str, ...]) -> int:
        haystack = str(text or "").lower()
        return sum(1 for term in terms if term and term in haystack)

    @classmethod
    def _policy_semantic_priority(cls, block: Dict[str, Any]) -> int:
        title_text = "\n".join(
            part for part in (str(block.get("title") or ""), str(block.get("source_name") or "")) if part
        )
        body_text = "\n".join(
            part
            for part in (
                title_text,
                str(block.get("evidence_summary") or ""),
                str(block.get("excerpt") or ""),
                str(block.get("text") or ""),
            )
            if part
        )
        account_terms = (
            "账号",
            "用户账号",
            "权限",
            "授权",
            "锁定",
            "注销",
            "停用",
            "回收",
            "调整",
            "审计",
            "核查",
            "审核",
            "冗余账号",
            "多余账号",
            "长期未登录",
            "未登录",
            "最小授权",
            "动态控制",
            "离岗",
            "离职",
            "申请",
        )
        scenario_terms = (
            "堡垒",
            "运维安全",
            "运维管控",
            "运维管理平台",
            "生产系统",
            "ukey",
        )
        off_topic_terms = (
            "互信",
            "云计算",
            "云原生",
            "学习环境",
            "工具",
            "车辆",
            "园区",
            "机房",
            "办公终端",
        )
        title_account_hits = cls._policy_contains_any(title_text, account_terms)
        body_account_hits = cls._policy_contains_any(body_text, account_terms)
        title_scenario_hits = cls._policy_contains_any(title_text, scenario_terms)
        body_scenario_hits = cls._policy_contains_any(body_text, scenario_terms)
        title_noise_hits = cls._policy_contains_any(title_text, off_topic_terms)
        body_noise_hits = cls._policy_contains_any(body_text, off_topic_terms)
        score = (
            title_account_hits * 8
            + body_account_hits * 3
            + title_scenario_hits * 4
            + body_scenario_hits
            - title_noise_hits * 10
            - body_noise_hits * 3
        )
        title_lower = title_text.lower()
        if "账号" in title_lower and "权限" in title_lower:
            score += 18
        if "实施细则" in title_lower and ("账号" in title_lower or "权限" in title_lower):
            score += 12
        if "堡垒" in title_lower and any(token in body_text.lower() for token in ("申请", "注销", "锁定", "核查")):
            score += 8
        if "云计算" in title_lower or "云原生" in title_lower:
            score -= 15
        if "互信" in title_lower:
            score -= 12
        if bool(block.get("text")):
            score += 4
        return score

    def _policy_search_hit_is_specific(self, query: str, block: Dict[str, Any]) -> bool:
        significant_terms = [term for term in self._policy_query_terms(query)[:12] if len(term) >= 5]
        if not significant_terms:
            return True
        matched_terms = [str(item).strip() for item in list(block.get("matched_terms") or []) if str(item).strip()]
        haystack = "\n".join(
            part
            for part in (
                str(block.get("title") or ""),
                str(block.get("source_name") or ""),
                str(block.get("evidence_summary") or ""),
                str(block.get("excerpt") or ""),
                str(block.get("text") or ""),
            )
            if part
        )
        return any(term in matched_terms or term in haystack for term in significant_terms)

    def _policy_selection_query_terms(self, user_text: str, evidence_blocks: List[Dict[str, Any]]) -> List[str]:
        query_sources = [user_text]
        for block in evidence_blocks:
            query_sources.extend(str(item) for item in list(block.get("source_queries") or []) if item)
        query_terms: List[str] = []
        for source in query_sources:
            for term in self._policy_query_terms(source):
                if term not in query_terms:
                    query_terms.append(term)
        return query_terms

    def _policy_apply_selection_signals(
        self,
        block: Dict[str, Any],
        query_terms: List[str],
        *,
        include_semantic_score: bool,
    ) -> Dict[str, int | List[str]]:
        low_signal_terms = {"系统", "应用", "运行", "管理", "长期", "登录"}
        title_text = "\n".join(
            part for part in (str(block.get("title") or ""), str(block.get("source_name") or "")) if part
        )
        block_text = "\n".join(
            part
            for part in (
                title_text,
                str(block.get("evidence_summary") or ""),
                str(block.get("excerpt") or ""),
                str(block.get("text") or ""),
            )
            if part
        )
        matched_terms = self._policy_matched_terms(block_text, query_terms)
        title_matches = self._policy_matched_terms(title_text, query_terms)
        signal_matches = [term for term in matched_terms if term not in low_signal_terms]
        title_signal_hits = len([term for term in title_matches if term not in low_signal_terms])
        block["matched_terms"] = signal_matches or matched_terms
        block["selection_query_hits"] = len(signal_matches)
        result: Dict[str, int | List[str]] = {
            "signal_matches": signal_matches,
            "title_signal_hits": title_signal_hits,
        }
        if include_semantic_score:
            semantic_score = self._policy_semantic_priority(block)
            block["selection_semantic_score"] = semantic_score
            result["semantic_score"] = semantic_score
        return result

    def _policy_selection_rank(self, block: Dict[str, Any], query_terms: List[str]) -> tuple[int, int, int, int, int, float, str]:
        signals = self._policy_apply_selection_signals(block, query_terms, include_semantic_score=False)
        signal_matches = list(signals.get("signal_matches") or [])
        return (
            int(block.get("authority_rank") or 0),
            int(not bool(block.get("is_noise_candidate"))),
            int(signals.get("title_signal_hits") or 0),
            int("policy_doc_read" in list(block.get("source_tools") or [])),
            len(signal_matches),
            float(block.get("score") or 0.0),
            str(block.get("title") or ""),
        )

    def _policy_selection_rank_v2(
        self,
        block: Dict[str, Any],
        query_terms: List[str],
    ) -> tuple[int, int, int, int, int, int, int, float, str]:
        signals = self._policy_apply_selection_signals(block, query_terms, include_semantic_score=True)
        signal_matches = list(signals.get("signal_matches") or [])
        llm_basis_type = str(block.get("llm_basis_type") or "").strip()
        llm_basis_bonus = {
            "primary_basis": 40,
            "scenario_basis": 28,
            "supporting_reference": 10,
            "noise": -30,
        }.get(llm_basis_type, 0)
        return (
            int(block.get("llm_relevance") or 0) + llm_basis_bonus,
            int(signals.get("semantic_score") or 0),
            int(block.get("authority_rank") or 0),
            int(not bool(block.get("is_noise_candidate"))),
            int(signals.get("title_signal_hits") or 0),
            int("policy_doc_read" in list(block.get("source_tools") or [])),
            len(signal_matches),
            float(block.get("score") or 0.0),
            str(block.get("title") or ""),
        )

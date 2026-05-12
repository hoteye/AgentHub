from __future__ import annotations

import json
from hashlib import sha1
from typing import Any, Dict, List

from cli.agent_cli.providers import policy_llm_assist_runtime as policy_llm_assist_runtime_service


class PolicyLlmAssistMixin:
    @staticmethod
    def _policy_cache_key(*parts: Any) -> str:
        payload = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
        return sha1(payload.encode("utf-8", errors="replace")).hexdigest()

    @staticmethod
    def _merge_policy_queries(*query_sets: List[str], limit: int = 4) -> List[str]:
        return policy_llm_assist_runtime_service.merge_policy_queries(*query_sets, limit=limit)

    @staticmethod
    def _policy_list_values(value: Any) -> List[Any]:
        return policy_llm_assist_runtime_service.policy_list_values(value)

    @classmethod
    def _policy_normalize_list(
        cls,
        value: Any,
        *,
        limit: int | None = None,
        max_len: int = 120,
    ) -> List[str]:
        return policy_llm_assist_runtime_service.policy_normalize_list(
            value,
            limit=limit,
            max_len=max_len,
        )

    @staticmethod
    def _policy_result_metadata(
        *,
        fallback_used: bool,
        fallback_reason: str = "",
        result_state: str = "",
        quality_state: str = "",
    ) -> Dict[str, Any]:
        return policy_llm_assist_runtime_service.policy_result_metadata(
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            result_state=result_state,
            quality_state=quality_state,
        )

    @staticmethod
    def _policy_has_content(payload: Dict[str, Any], *, keys: List[str]) -> bool:
        return policy_llm_assist_runtime_service.policy_has_content(payload, keys=keys)

    @classmethod
    def _policy_issue_hints(cls, user_text: str) -> Dict[str, List[str]]:
        return policy_llm_assist_runtime_service.policy_issue_hints(user_text)

    @staticmethod
    def _policy_compact_user_query(user_text: str) -> str:
        return policy_llm_assist_runtime_service.policy_compact_user_query(user_text)

    def _policy_rewrite_fallback_payload(self, user_text: str, heuristic_queries: List[str]) -> Dict[str, Any]:
        return policy_llm_assist_runtime_service.policy_rewrite_fallback_payload(
            user_text,
            heuristic_queries,
        )

    def _policy_rerank_fallback_payload(self, user_text: str, candidate_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        return policy_llm_assist_runtime_service.policy_rerank_fallback_payload(
            user_text,
            candidate_items,
        )

    @staticmethod
    def _policy_normalize_basis_type(value: Any) -> str:
        return policy_llm_assist_runtime_service.policy_normalize_basis_type(value)

    @classmethod
    def _policy_sentences(cls, *texts: str, limit: int = 12) -> List[str]:
        return policy_llm_assist_runtime_service.policy_sentences(*texts, limit=limit)

    def _policy_extract_fallback_payload(self, user_text: str, candidate_items: List[Dict[str, Any]]) -> Dict[str, Any]:
        return policy_llm_assist_runtime_service.policy_extract_fallback_payload(
            user_text,
            candidate_items,
        )

    def _policy_llm_query_rewrite(self, user_text: str, heuristic_queries: List[str]) -> Dict[str, Any]:
        cache_key = self._policy_cache_key("rewrite", user_text, heuristic_queries)
        cached = self._policy_query_rewrite_cache.get(cache_key)
        if cached is not None:
            return dict(cached)
        payload = self._chat_json_payload(
            system_prompt=(
                "You rewrite Chinese internal-audit policy questions into short retrieval queries. "
                "Return strict JSON only."
            ),
            user_prompt="\n".join(
                [
                    "将下面的审计/制度问题改写成适合制度检索的短 query。",
                    "要求：",
                    "1. 每个 query 只保留对象词、动作词、制度词，不要保留“经查/请说明/制度依据”等套话。",
                    "2. 优先输出 3 到 5 个短 query，每个 query 不超过 20 个汉字或 40 个字符。",
                    "3. 适合内部制度检索，不要生成解释性句子。",
                    "4. 如果问题涉及账号/权限/UKey/尽职调查/统计报送/异常处置/双人复核/服务质量考核，要显式保留这些控制主题。",
                    "5. 可以参考候选 query，但不要机械照抄明显跑偏的项。",
                    "6. 如果题目是“权限与职责不匹配/权责不符”，应补出“最小授权/最小必要权限/工作职责/工作需要”等控制词。",
                    "7. 如果题目是“未按季度报送/季度报送不到位”，应补出“外包活动清单/驻场外包人员信息统计表/金融科技部/每季度末月25日前”等检索词。",
                    "8. 如果题目是“UKey出借/他人使用/访问凭证混用”，应补出“访问凭证/数字证书/私钥/不得借予他人使用/不得转授”等检索词。",
                    "9. 不要引入原题未涉及的无关控制主题；例如未提到升级、异常、双人复核时，不要生成“异常处置/双人复核”类 query。",
                    "10. 第一条 query 必须是最能直接命中制度条款的控制词组合，不要只是重复用户原话，也不要以“制度依据/问题定性/责任环节”收尾。",
                    "11. 对 UKey/访问凭证题，第一条 query 优先写成带禁止性控制词的检索式，例如包含“不得借予他人使用/不得转授/访问凭证”等。",
                    "",
                    "输出 JSON：",
                    '{"queries":["..."],"issue_labels":["..."],"must_terms":["..."],"role_terms":["..."]}',
                    "",
                    "原问题：",
                    user_text,
                    "",
                    "候选 query：",
                    json.dumps(heuristic_queries, ensure_ascii=False),
                ]
            ),
        )
        hints = self._policy_issue_hints(user_text)
        queries = self._policy_normalize_list(payload.get("queries"), limit=5, max_len=40)
        issue_labels = self._policy_normalize_list(payload.get("issue_labels"), limit=4, max_len=48) or list(
            hints.get("issue_labels") or []
        )
        must_terms = self._policy_normalize_list(payload.get("must_terms"), limit=6, max_len=48) or list(
            hints.get("must_terms") or []
        )
        role_terms = self._policy_normalize_list(payload.get("role_terms"), limit=4, max_len=48) or list(
            hints.get("role_terms") or []
        )
        fallback_used = False
        fallback_reason = ""
        if not queries:
            fallback_payload = self._policy_rewrite_fallback_payload(user_text, heuristic_queries)
            queries = list(fallback_payload.get("queries") or [])
            issue_labels = issue_labels or list(fallback_payload.get("issue_labels") or [])
            must_terms = must_terms or list(fallback_payload.get("must_terms") or [])
            role_terms = role_terms or list(fallback_payload.get("role_terms") or [])
            fallback_used = True
            fallback_reason = "empty_queries"
        quality_state = "empty"
        result_state = "empty"
        if queries:
            quality_state = "fallback" if fallback_used else ("ok" if issue_labels or must_terms or role_terms else "partial")
            result_state = "fallback_applied" if fallback_used else ("llm_ok" if quality_state == "ok" else "llm_partial")
        result = {
            "queries": queries,
            "issue_labels": issue_labels,
            "must_terms": must_terms,
            "role_terms": role_terms,
            **self._policy_result_metadata(
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
                result_state=result_state,
                quality_state=quality_state,
            ),
        }
        self._policy_query_rewrite_cache[cache_key] = dict(result)
        return result

    def _policy_llm_rerank(self, user_text: str, evidence_blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        candidate_items = []
        for index, block in enumerate(evidence_blocks[:8], start=1):
            candidate_items.append(
                {
                    "index": index,
                    "title": str(block.get("title") or block.get("doc_id") or "").strip(),
                    "source_name": str(block.get("source_name") or "").strip(),
                    "doc_group": str(block.get("doc_group") or "").strip(),
                    "doc_kind": str(block.get("doc_kind") or "").strip(),
                    "authority_rank": int(block.get("authority_rank") or 0),
                    "query_term_hits": int(block.get("query_term_hits") or 0),
                    "excerpt": self._policy_snippet(block, limit=220),
                    "has_text": bool(str(block.get("text") or "").strip()),
                }
            )
        if not candidate_items:
            return {}
        cache_key = self._policy_cache_key("rerank", user_text, candidate_items)
        cached = self._policy_rerank_cache.get(cache_key)
        if cached is not None:
            return dict(cached)
        payload = self._chat_json_payload(
            system_prompt=(
                "You rerank internal policy evidence for Chinese audit QA. "
                "Return strict JSON only."
            ),
            user_prompt="\n".join(
                [
                    "下面是一个审计/制度问答问题，以及候选制度文档。",
                    "请判断哪些文档最适合作为：主依据、场景补充依据、补充参考、噪音。",
                    "要求：",
                    "1. 优先选择能直接回答该问题控制要求的正式制度。",
                    "2. 对账号/权限/UKey/堡垒系统问题，优先账号权限、访问控制、堡垒系统制度，压低处分、积分、员工处理类文档。",
                    "3. 对统计报送问题，优先含“外包活动清单/驻场外包人员信息统计表/金融科技部/季度末月25日前”的制度。",
                    "4. 对尽职调查问题，优先含“外包服务提供商/尽职调查/财务情况/风险管理/业务连续性”的制度。",
                    "5. 审计底稿、培训、征求意见稿、处罚办法通常只能做补充参考或噪音，除非问题就是在问处罚。",
                    "",
                    "输出 JSON：",
                    '{"issue_label":"","focus_terms":["..."],"ranked":[{"index":1,"basis_type":"primary_basis","relevance":92,"reason":"..."}]}',
                    "",
                    "问题：",
                    user_text,
                    "",
                    "候选文档：",
                    json.dumps(candidate_items, ensure_ascii=False, indent=2),
                ]
            ),
        )
        hints = self._policy_issue_hints(user_text)
        ranked = [
            {
                "index": int(item.get("index") or 0),
                "basis_type": self._policy_normalize_basis_type(item.get("basis_type")),
                "relevance": max(0, min(100, int(item.get("relevance") or 0))),
                "reason": str(item.get("reason") or "").strip(),
            }
            for item in self._policy_list_values(payload.get("ranked"))
            if isinstance(item, dict)
            if int(item.get("index") or 0) > 0
        ]
        issue_label = str(payload.get("issue_label") or "").strip() or str((hints.get("issue_labels") or [""])[0] or "").strip()
        focus_terms = self._policy_normalize_list(payload.get("focus_terms"), limit=4, max_len=48) or list(
            hints.get("must_terms") or []
        )[:4]
        fallback_used = False
        fallback_reason = ""
        if not ranked:
            fallback_payload = self._policy_rerank_fallback_payload(user_text, candidate_items)
            ranked = list(fallback_payload.get("ranked") or [])
            issue_label = issue_label or str(fallback_payload.get("issue_label") or "").strip()
            focus_terms = focus_terms or list(fallback_payload.get("focus_terms") or [])
            fallback_used = True
            fallback_reason = "empty_ranked"
        result = {
            "issue_label": issue_label,
            "focus_terms": focus_terms,
            "ranked": ranked,
            **self._policy_result_metadata(
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
                result_state="fallback_applied" if fallback_used and ranked else ("llm_ok" if ranked and issue_label and focus_terms else "llm_partial" if ranked else "empty"),
                quality_state="fallback" if fallback_used and ranked else ("ok" if ranked and issue_label and focus_terms else "partial" if ranked else "empty"),
            ),
        }
        self._policy_rerank_cache[cache_key] = dict(result)
        return result

    def _policy_llm_extract(self, user_text: str, evidence_blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        candidate_items = []
        for block in evidence_blocks[:3]:
            candidate_items.append(
                {
                    "evidence_id": str(block.get("evidence_id") or "").strip(),
                    "title": str(block.get("title") or block.get("doc_id") or "").strip(),
                    "doc_group": str(block.get("doc_group") or "").strip(),
                    "priority_excerpt": str(block.get("priority_excerpt") or self._policy_snippet(block, limit=220)).strip(),
                    "text": str(block.get("text") or "")[:1600],
                }
            )
        if not candidate_items:
            return {}
        cache_key = self._policy_cache_key("extract", user_text, candidate_items)
        cached = self._policy_extract_cache.get(cache_key)
        if cached is not None:
            return dict(cached)
        payload = self._chat_json_payload(
            system_prompt=(
                "You extract structured policy evidence for Chinese audit QA. "
                "Return strict JSON only."
            ),
            user_prompt="\n".join(
                [
                    "基于下面的制度证据，抽取结构化事实。",
                    "要求：",
                    "1. 只能提取证据中直接支持的内容。",
                    "2. 不要编造条款号、时限、责任主体。",
                    "3. 如果证据没有明确写出，就留空数组或空字符串。",
                    "",
                    "输出 JSON：",
                    '{"issue_label":"","conclusion_points":["..."],"obligations":["..."],"prohibitions":["..."],"responsibility_roles":["..."],"time_requirements":["..."],"missing_evidence":["..."]}',
                    "",
                    "问题：",
                    user_text,
                    "",
                    "证据：",
                    json.dumps(candidate_items, ensure_ascii=False, indent=2),
                ]
            ),
        )
        hints = self._policy_issue_hints(user_text)
        result = {
            "issue_label": str(payload.get("issue_label") or "").strip() or str((hints.get("issue_labels") or [""])[0] or "").strip(),
            "conclusion_points": self._policy_normalize_list(payload.get("conclusion_points"), limit=4, max_len=160),
            "obligations": self._policy_normalize_list(payload.get("obligations"), limit=4, max_len=160),
            "prohibitions": self._policy_normalize_list(payload.get("prohibitions"), limit=4, max_len=160),
            "responsibility_roles": self._policy_normalize_list(payload.get("responsibility_roles"), limit=4, max_len=48),
            "time_requirements": self._policy_normalize_list(payload.get("time_requirements"), limit=4, max_len=160),
            "missing_evidence": self._policy_normalize_list(payload.get("missing_evidence"), limit=4, max_len=80),
        }
        fallback_used = False
        fallback_reason = ""
        if not self._policy_has_content(
            result,
            keys=[
                "conclusion_points",
                "obligations",
                "prohibitions",
                "responsibility_roles",
                "time_requirements",
            ],
        ):
            result = self._policy_extract_fallback_payload(user_text, candidate_items)
            fallback_used = True
            fallback_reason = "empty_extract"
        result.update(
            self._policy_result_metadata(
                fallback_used=fallback_used,
                fallback_reason=fallback_reason,
                result_state="fallback_applied" if fallback_used and self._policy_has_content(result, keys=["conclusion_points", "obligations", "prohibitions"]) else ("llm_ok" if self._policy_has_content(result, keys=["conclusion_points", "obligations", "prohibitions"]) and result.get("issue_label") else "llm_partial" if self._policy_has_content(result, keys=["conclusion_points", "obligations", "prohibitions"]) else "empty"),
                quality_state="fallback" if fallback_used and self._policy_has_content(result, keys=["conclusion_points", "obligations", "prohibitions"]) else ("ok" if self._policy_has_content(result, keys=["conclusion_points", "obligations", "prohibitions"]) and result.get("issue_label") else "partial" if self._policy_has_content(result, keys=["conclusion_points", "obligations", "prohibitions"]) else "empty"),
            )
        )
        self._policy_extract_cache[cache_key] = dict(result)
        return result

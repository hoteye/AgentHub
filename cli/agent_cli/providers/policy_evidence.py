from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from cli.agent_cli.models import ToolEvent
from shared.document_tools.policy_query import policy_query_compact_queries, policy_query_terms


class PolicyEvidenceMixin:
    @staticmethod
    def _normalize_policy_text(value: Any, *, limit: int = 1200) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        return text[:limit]

    @staticmethod
    def _policy_doc_kind(title: str, *, source_name: str = "", text: str = "") -> str:
        title_haystack = f"{title}\n{source_name}".lower()
        text_haystack = str(text or "").lower()
        haystack = f"{title_haystack}\n{text_haystack}"
        if any(token in haystack for token in ("审计", "底稿", "确认单", "检查发现", "问题整改")):
            return "audit_workpaper"
        if any(token in haystack for token in ("验证报告", "说明表", "修订说明")):
            return "supporting_reference"
        if any(token in haystack for token in ("宣贯", "培训", "解读", "课件", "ppt")):
            return "training_material"
        if any(token in title_haystack for token in ("管理规程", "操作规程", "规范", "标准", "指引")):
            return "specialized_policy"
        if any(token in title_haystack for token in ("管理办法", "实施细则", "管理细则", "制度")):
            return "governance_policy"
        if any(token in text_haystack for token in ("管理规程", "操作规程", "规范", "标准", "指引")):
            return "specialized_policy"
        if any(token in text_haystack for token in ("管理办法", "实施细则", "管理细则", "制度")):
            return "governance_policy"
        return "supporting_reference"

    @staticmethod
    def _policy_doc_group(doc_kind: str) -> str:
        if doc_kind == "governance_policy":
            return "governance_base"
        if doc_kind == "specialized_policy":
            return "direct_rule"
        return "supporting_reference"

    @staticmethod
    def _policy_authority_rank(doc_kind: str) -> int:
        ranks = {
            "governance_policy": 100,
            "specialized_policy": 90,
            "draft_policy": 70,
            "supporting_reference": 40,
            "training_material": 20,
            "audit_workpaper": 10,
        }
        return ranks.get(doc_kind, 0)

    @staticmethod
    def _policy_query_terms(user_text: str) -> List[str]:
        return policy_query_terms(user_text, limit=40)

    @staticmethod
    def _policy_is_summary_question(user_text: str) -> bool:
        text = str(user_text or "").strip().lower()
        if not text:
            return False
        summary_markers = (
            "内容是什么",
            "主要内容",
            "核心内容",
            "讲了什么",
            "主要讲什么",
            "全文",
            "概括",
            "概要",
        )
        exclusion_markers = (
            "依据",
            "条款",
            "第几条",
            "哪一条",
            "要求",
            "流程",
            "规定",
            "多久",
            "频次",
            "条件",
            "如何",
            "怎么",
            "是否",
            "审计",
            "核查",
            "责任",
        )
        if any(marker in text for marker in exclusion_markers):
            return False
        return any(marker in text for marker in summary_markers)

    @classmethod
    def _policy_should_preflight_before_model(cls, user_text: str) -> bool:
        text = str(user_text or "").strip()
        if not text:
            return False
        if cls._policy_is_summary_question(text):
            return True
        normalized = re.sub(r"\s+", "", text)
        scenario_markers = ("系统", "场景", "存在", "问题", "整改", "管控", "审计发现", "账号", "权限")
        return len(normalized) >= 24 and any(marker in text for marker in scenario_markers)

    @staticmethod
    def _policy_snippet(block: Dict[str, Any], *, limit: int = 180) -> str:
        snippet = str(
            block.get("evidence_summary")
            or block.get("excerpt")
            or block.get("summary")
            or block.get("text")
            or ""
        ).strip()
        if len(snippet) > limit:
            return snippet[:limit].rstrip() + "..."
        return snippet

    def _policy_query_plan(self, user_text: str) -> List[str]:
        heuristic_queries = policy_query_compact_queries(user_text, limit=6)
        if not self.policy_llm_assist:
            return heuristic_queries[:4]
        llm_payload = self._policy_llm_query_rewrite(user_text, heuristic_queries)
        llm_queries = [str(item).strip() for item in list(llm_payload.get("queries") or []) if str(item).strip()]
        seed_queries: List[str] = []
        must_terms = [str(item).strip() for item in list(llm_payload.get("must_terms") or []) if str(item).strip()]
        role_terms = [str(item).strip() for item in list(llm_payload.get("role_terms") or []) if str(item).strip()]
        if len(must_terms) >= 2:
            seed_queries.append(" ".join(must_terms[:4]))
        if must_terms and role_terms:
            seed_queries.append(" ".join([*must_terms[:2], *role_terms[:2]]))
        return self._merge_policy_queries(llm_queries, seed_queries, heuristic_queries, limit=4)

    def _policy_evidence_blocks(self, events: List[ToolEvent]) -> List[Dict[str, Any]]:
        blocks_by_key: Dict[tuple[str, str], Dict[str, Any]] = {}
        for event in events:
            payload = event.payload or {}
            if not event.ok:
                continue
            if event.name == "policy_doc_search":
                search_query = str(payload.get("query") or "").strip()
                for item in list(payload.get("documents") or [])[:6]:
                    if not isinstance(item, dict):
                        continue
                    doc_id = str(item.get("doc_id") or "").strip()
                    title = str(item.get("title") or "").strip()
                    source_name = str(item.get("source_name") or "").strip()
                    excerpt = self._normalize_policy_text(
                        item.get("evidence_summary") or item.get("excerpt") or item.get("summary") or "",
                        limit=500,
                    )
                    if not title and not excerpt:
                        continue
                    key = (doc_id, title or source_name)
                    block = blocks_by_key.setdefault(
                        key,
                        {
                            "doc_id": doc_id,
                            "title": title,
                            "source_name": source_name,
                            "source_tools": [],
                        },
                    )
                    block["doc_id"] = doc_id or str(block.get("doc_id") or "")
                    block["title"] = title or str(block.get("title") or "")
                    block["source_name"] = source_name or str(block.get("source_name") or "")
                    block["excerpt"] = excerpt or str(block.get("excerpt") or "")
                    for key_name in (
                        "doc_kind",
                        "doc_group",
                        "authority_rank",
                        "normalized_title",
                        "is_noise_candidate",
                        "matched_terms",
                        "query_term_hits",
                        "evidence_summary",
                    ):
                        if item.get(key_name) is not None:
                            block[key_name] = item.get(key_name)
                    if event.name not in block["source_tools"]:
                        block["source_tools"].append(event.name)
                    if search_query:
                        queries = list(block.get("source_queries") or [])
                        if search_query not in queries:
                            queries.append(search_query)
                        block["source_queries"] = queries
                    if item.get("score") is not None:
                        score_value = float(item.get("score") or 0)
                        if score_value > float(block.get("score") or 0):
                            block["score"] = score_value
            if event.name == "policy_doc_read":
                document = payload.get("document") if isinstance(payload.get("document"), dict) else {}
                doc_id = str(document.get("doc_id") or payload.get("doc_id") or "").strip()
                title = str(document.get("title") or payload.get("title") or "").strip()
                source_name = str(document.get("source_name") or payload.get("source_name") or "").strip()
                raw_text = str(payload.get("text") or "")
                text = self._normalize_policy_text(raw_text, limit=6500)
                if not title and not text:
                    continue
                key = (doc_id, title or source_name)
                block = blocks_by_key.setdefault(
                    key,
                    {
                        "doc_id": doc_id,
                        "title": title,
                        "source_name": source_name,
                        "source_tools": [],
                    },
                )
                block.update(
                    {
                        "source_tool": "policy_doc_read",
                        "doc_id": doc_id or str(block.get("doc_id") or ""),
                        "title": title or str(block.get("title") or ""),
                        "source_name": source_name or str(block.get("source_name") or ""),
                        "raw_text": raw_text[:6500],
                        "text": text,
                        "char_count": int(payload.get("char_count") or 0),
                        "summary": self._normalize_policy_text(payload.get("summary") or "", limit=240),
                        "evidence_summary": self._normalize_policy_text(payload.get("evidence_summary") or "", limit=240),
                    }
                )
                for key_name in (
                    "doc_kind",
                    "doc_group",
                    "authority_rank",
                    "normalized_title",
                    "is_noise_candidate",
                    "matched_terms",
                    "query_term_hits",
                    "evidence_summary",
                ):
                    if document.get(key_name) is not None:
                        block[key_name] = document.get(key_name)
                if event.name not in block["source_tools"]:
                    block["source_tools"].append(event.name)

        blocks: List[Dict[str, Any]] = []
        for block in blocks_by_key.values():
            title = str(block.get("title") or "").strip()
            source_name = str(block.get("source_name") or "").strip()
            text = str(block.get("text") or block.get("excerpt") or "").strip()
            doc_kind = str(block.get("doc_kind") or "").strip() or self._policy_doc_kind(title, source_name=source_name, text=text)
            block["doc_kind"] = doc_kind
            block["doc_group"] = str(block.get("doc_group") or "").strip() or self._policy_doc_group(doc_kind)
            block["authority_rank"] = int(block.get("authority_rank") or self._policy_authority_rank(doc_kind))
            block["evidence_summary"] = self._policy_snippet(block, limit=220)
            block["query_term_hits"] = int(block.get("query_term_hits") or 0)
            blocks.append(block)
        blocks.sort(
            key=lambda item: (
                int(bool(item.get("is_noise_candidate"))),
                -int(item.get("authority_rank") or 0),
                -int(bool(item.get("text"))),
                -int(item.get("query_term_hits") or 0),
                -float(item.get("score") or 0),
                str(item.get("title") or ""),
            )
        )
        return blocks

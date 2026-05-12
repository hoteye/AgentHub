from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli.providers.policy_llm_assist import PolicyLlmAssistMixin

class _Harness(PolicyLlmAssistMixin):
    def __init__(self, payloads: List[Dict[str, Any]]) -> None:
        self._payloads = [dict(item) for item in payloads]
        self._policy_query_rewrite_cache: Dict[str, Dict[str, Any]] = {}
        self._policy_rerank_cache: Dict[str, Dict[str, Any]] = {}
        self._policy_extract_cache: Dict[str, Dict[str, Any]] = {}

    def _chat_json_payload(self, *, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        del system_prompt, user_prompt
        if not self._payloads:
            return {}
        return dict(self._payloads.pop(0))

    @staticmethod
    def _policy_snippet(block: Dict[str, Any], *, limit: int = 220) -> str:
        text = str(block.get("excerpt") or block.get("text") or "").strip()
        if len(text) > limit:
            return text[:limit].rstrip() + "..."
        return text

def test_policy_llm_query_rewrite_falls_back_to_heuristics_with_metadata() -> None:
    harness = _Harness([{}])

    result = harness._policy_llm_query_rewrite(
        "请说明权限与职责不匹配时应检索哪些制度控制要求。",
        ["权限与职责不匹配", "最小授权", "最小必要权限"],
    )

    assert result["fallback_used"] is True
    assert result["fallback_reason"] == "empty_queries"
    assert result["result_state"] == "fallback_applied"
    assert result["quality_state"] == "fallback"
    assert result["queries"]
    assert "access_control" in result["issue_labels"]
    assert any("最小授权" in item or "权限" in item for item in result["queries"])

def test_policy_llm_rerank_falls_back_to_heuristic_ranking_with_metadata() -> None:
    harness = _Harness([{"ranked": []}])

    result = harness._policy_llm_rerank(
        "制度是否要求按季度报送外包活动清单和驻场外包人员信息统计表？",
        [
            {
                "title": "信息科技外包管理实施细则",
                "source_name": "信息科技外包管理实施细则",
                "doc_group": "direct_rule",
                "doc_kind": "policy",
                "authority_rank": 95,
                "query_term_hits": 4,
                "excerpt": "金融科技部应于每季度末月25日前汇总外包活动清单及驻场外包人员信息统计表。",
                "text": "制度明确金融科技部应于每季度末月25日前报送相关清单。",
            },
            {
                "title": "外包服务质量考核办法",
                "source_name": "外包服务质量考核办法",
                "doc_group": "supporting_reference",
                "doc_kind": "policy",
                "authority_rank": 61,
                "query_term_hits": 1,
                "excerpt": "规定服务质量年度评价。",
                "text": "本办法不直接回答季度报送要求。",
            },
        ],
    )

    assert result["fallback_used"] is True
    assert result["fallback_reason"] == "empty_ranked"
    assert result["result_state"] == "fallback_applied"
    assert result["quality_state"] == "fallback"
    assert result["ranked"][0]["index"] == 1
    assert result["ranked"][0]["basis_type"] == "primary_basis"
    assert result["focus_terms"]

def test_policy_llm_extract_falls_back_to_sentence_heuristics_with_metadata() -> None:
    harness = _Harness([{}])

    result = harness._policy_llm_extract(
        "制度对 UKey 出借和访问凭证管理有哪些明确要求？",
        [
            {
                "evidence_id": "E1",
                "title": "访问控制管理办法",
                "doc_group": "direct_rule",
                "priority_excerpt": "访问凭证不得借予他人使用，不得转授。",
                "text": "第十二条 访问凭证、数字证书和私钥应由本人专用保管，不得借予他人使用，不得转授。",
            },
            {
                "evidence_id": "E2",
                "title": "终端与介质安全管理细则",
                "doc_group": "supporting_reference",
                "priority_excerpt": "UKey 应由责任人妥善保管，离岗时应及时交回。",
                "text": "UKey 应由责任人妥善保管。人员离岗时应及时交回并办理注销或权限调整。",
            },
        ],
    )

    assert result["fallback_used"] is True
    assert result["fallback_reason"] == "empty_extract"
    assert result["result_state"] == "fallback_applied"
    assert result["quality_state"] == "fallback"
    assert any("不得借予他人使用" in item for item in result["prohibitions"])
    assert "责任人" in result["responsibility_roles"]
    assert any("及时交回" in item or "离岗" in item for item in result["time_requirements"])

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PolicyHelperCase:
    name: str
    phase: str
    user_text: str
    heuristic_queries: tuple[str, ...] = ()
    evidence_blocks: tuple[dict[str, Any], ...] = ()


CASES: tuple[PolicyHelperCase, ...] = (
    PolicyHelperCase(
        name="rewrite_permission_mismatch",
        phase="rewrite",
        user_text="请说明权限与职责不匹配时应检索哪些制度控制要求。",
        heuristic_queries=(
            "权限与职责不匹配",
            "最小授权",
            "最小必要权限",
        ),
    ),
    PolicyHelperCase(
        name="rewrite_ukey_borrowing",
        phase="rewrite",
        user_text="制度如何要求 UKey、访问凭证和数字证书不得借予他人使用？",
        heuristic_queries=(
            "UKey 出借",
            "访问凭证",
            "不得借予他人使用",
        ),
    ),
    PolicyHelperCase(
        name="rerank_quarterly_reporting",
        phase="rerank",
        user_text="制度是否要求按季度报送外包活动清单和驻场外包人员信息统计表？",
        evidence_blocks=(
            {
                "title": "信息科技外包管理实施细则",
                "source_name": "信息科技外包管理实施细则",
                "doc_group": "direct_rule",
                "doc_kind": "policy",
                "authority_rank": 95,
                "query_term_hits": 4,
                "excerpt": "金融科技部应于每季度末月25日前汇总外包活动清单及驻场外包人员信息统计表。",
                "text": (
                    "第十八条 金融科技部应于每季度末月25日前，组织汇总外包活动清单和驻场外包人员信息统计表，"
                    "按要求报送相关管理部门。"
                ),
            },
            {
                "title": "信息科技外包考核办法",
                "source_name": "信息科技外包考核办法",
                "doc_group": "supporting_reference",
                "doc_kind": "policy",
                "authority_rank": 62,
                "query_term_hits": 1,
                "excerpt": "对外包服务质量进行年度评价。",
                "text": "本办法主要规定外包服务质量的年度评价与扣分机制。",
            },
            {
                "title": "账号权限管理办法",
                "source_name": "账号权限管理办法",
                "doc_group": "supporting_reference",
                "doc_kind": "policy",
                "authority_rank": 70,
                "query_term_hits": 0,
                "excerpt": "账号权限应遵循最小授权原则。",
                "text": "制度要求账号权限配置遵循最小授权原则，与外包统计报送无直接关系。",
            },
        ),
    ),
    PolicyHelperCase(
        name="rerank_vendor_due_diligence",
        phase="rerank",
        user_text="制度对外包服务提供商尽职调查是否覆盖财务情况、风险管理和业务连续性？",
        evidence_blocks=(
            {
                "title": "信息科技外包风险管理办法",
                "source_name": "信息科技外包风险管理办法",
                "doc_group": "direct_rule",
                "doc_kind": "policy",
                "authority_rank": 93,
                "query_term_hits": 4,
                "excerpt": "外包服务提供商准入前应完成尽职调查，覆盖财务情况、风险管理和业务连续性能力。",
                "text": (
                    "第十条 对拟合作的外包服务提供商，应开展尽职调查，"
                    "重点评估其财务情况、风险管理、业务连续性和交付能力。"
                ),
            },
            {
                "title": "信息科技外包服务质量考核办法",
                "source_name": "信息科技外包服务质量考核办法",
                "doc_group": "supporting_reference",
                "doc_kind": "policy",
                "authority_rank": 61,
                "query_term_hits": 1,
                "excerpt": "年度考核关注服务质量和协作效率。",
                "text": "本办法关注服务质量年度考核，对准入尽职调查要求不构成直接依据。",
            },
            {
                "title": "办公设备领用规定",
                "source_name": "办公设备领用规定",
                "doc_group": "supporting_reference",
                "doc_kind": "policy",
                "authority_rank": 18,
                "query_term_hits": 0,
                "excerpt": "规定办公设备领用流程。",
                "text": "本规定仅涉及办公设备领用，与外包服务提供商尽职调查无关。",
            },
        ),
    ),
    PolicyHelperCase(
        name="extract_ukey_controls",
        phase="extract",
        user_text="制度对 UKey 出借和访问凭证管理有哪些明确要求？",
        evidence_blocks=(
            {
                "evidence_id": "E1",
                "title": "访问控制管理办法",
                "doc_group": "direct_rule",
                "priority_excerpt": "访问凭证不得借予他人使用，不得转授。",
                "text": (
                    "第十二条 访问凭证、数字证书和私钥应由本人专用保管，"
                    "不得借予他人使用，不得转授，不得混用。"
                ),
            },
            {
                "evidence_id": "E2",
                "title": "终端与介质安全管理细则",
                "doc_group": "supporting_reference",
                "priority_excerpt": "UKey 应由责任人妥善保管，离岗时应及时交回。",
                "text": (
                    "UKey 应由责任人妥善保管。人员离岗、调岗或不再承担相关职责时，"
                    "应及时交回并办理注销或权限调整。"
                ),
            },
        ),
    ),
    PolicyHelperCase(
        name="extract_outsourcing_reporting",
        phase="extract",
        user_text="制度对按季度报送外包活动清单有哪些明确要求？",
        evidence_blocks=(
            {
                "evidence_id": "E1",
                "title": "信息科技外包管理实施细则",
                "doc_group": "direct_rule",
                "priority_excerpt": "金融科技部应于每季度末月25日前汇总外包活动清单和驻场外包人员信息统计表。",
                "text": (
                    "第十八条 金融科技部应于每季度末月25日前，"
                    "组织汇总外包活动清单和驻场外包人员信息统计表，按要求报送相关管理部门。"
                ),
            },
            {
                "evidence_id": "E2",
                "title": "信息科技外包风险管理办法",
                "doc_group": "supporting_reference",
                "priority_excerpt": "外包信息报送应确保真实、完整、及时。",
                "text": "外包信息报送应确保真实、完整、及时，出现重大变化时应同步更新。",
            },
        ),
    ),
)


CASE_META_KEYS = {
    "fallback_used",
    "fallback_reason",
    "result_state",
    "quality_state",
}

PROFILE_CHOICES = ("single", "policy_helper_regression", "policy_helper_matrix")


@dataclass(frozen=True)
class PolicyHelperCombo:
    combo_id: str
    provider: str = ""
    model: str = ""
    reasoning_effort: str = "low"
    timeout: int = 20
    source: str = "profile"
    description: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "combo_id": self.combo_id,
            "provider": self.provider,
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "timeout": int(self.timeout),
            "source": self.source,
            "description": self.description,
        }


POLICY_HELPER_COMBO_CATALOG: tuple[PolicyHelperCombo, ...] = (
    PolicyHelperCombo(
        combo_id="main_route_default",
        provider="",
        model="",
        reasoning_effort="low",
        timeout=20,
        source="main_route",
        description="Follow main provider/model route and enforce helper low-effort timeout guard.",
    ),
    PolicyHelperCombo(
        combo_id="glm_low_latency",
        provider="glm",
        model="glm_5",
        reasoning_effort="low",
        timeout=20,
        source="override",
        description="Pin helper route to glm_5 for baseline regression.",
    ),
    PolicyHelperCombo(
        combo_id="deepseek_low_latency",
        provider="deepseek",
        model="deepseek_chat",
        reasoning_effort="low",
        timeout=20,
        source="override",
        description="Pin helper route to deepseek_chat for alternate regression lane.",
    ),
)

POLICY_HELPER_PROFILE_MATRIX: dict[str, tuple[str, ...]] = {
    "policy_helper_regression": ("glm_low_latency", "deepseek_low_latency"),
    "policy_helper_matrix": ("main_route_default", "glm_low_latency", "deepseek_low_latency"),
}

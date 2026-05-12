from __future__ import annotations

from typing import Any, Dict, List, Optional

from cli.agent_cli.models import ToolEvent


class PolicyAnswerRenderingMixin:
    def _policy_grounded_fallback_text(
        self,
        user_text: str,
        evidence_blocks: List[Dict[str, Any]],
        *,
        unsupported_claims: Optional[List[str]] = None,
    ) -> str:
        lines = ["结论：", "本轮已基于命中的制度证据整理结论，仅保留能够从证据直接支持的制度依据。", "证据摘要："]
        lines.extend(self._policy_evidence_summary_lines(evidence_blocks) or ["1. 本轮未命中可直接引用的制度原文。"])
        if unsupported_claims:
            lines.append("证据缺口：")
            lines.append("- 以下表述未能从命中文档中确认：" + "、".join(unsupported_claims[:6]))
        else:
            lines.append("证据缺口：")
            lines.append("- 如需条款号、时限或更细结论，仍需继续读取命中文档原文。")
        return "\n".join(lines)

    def _policy_group_summary_lines(self, evidence_profile: Dict[str, Any], evidence_blocks: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        block_map = {
            (str(block.get("doc_id") or ""), str(block.get("title") or "")): block
            for block in evidence_blocks
        }
        grouped_lines: Dict[str, List[str]] = {
            "governance_base": [],
            "direct_rule": [],
            "supporting_reference": [],
        }
        for group, docs in dict(evidence_profile.get("groups") or {}).items():
            for item in list(docs or [])[:3]:
                key = (str(item.get("doc_id") or ""), str(item.get("title") or ""))
                block = block_map.get(key, {})
                title = str(item.get("title") or "").strip()
                snippet = self._policy_snippet(block, limit=180)
                line = f"- {title or key[0]}"
                if snippet:
                    line += f": {snippet}"
                matched_terms = list(block.get("matched_terms") or [])
                if matched_terms:
                    line += f" [matched: {', '.join(matched_terms[:4])}]"
                grouped_lines.setdefault(group, []).append(line)
        return grouped_lines

    def _policy_coverage_fallback_text(
        self,
        user_text: str,
        evidence_blocks: List[Dict[str, Any]],
        evidence_profile: Dict[str, Any],
        *,
        unsupported_claims: Optional[List[str]] = None,
        coverage_issues: Optional[List[str]] = None,
    ) -> str:
        grouped_lines = self._policy_group_summary_lines(evidence_profile, evidence_blocks)
        lines = ["结论："]
        if grouped_lines.get("governance_base") and grouped_lines.get("direct_rule"):
            lines.append("本轮问题同时命中了上位账号权限管理制度和具体系统运行规程，制度依据应分层说明，不能只引用单一材料。")
        elif grouped_lines.get("governance_base"):
            lines.append("本轮仅稳定命中上位制度依据，尚缺少更直接的场景化制度支撑。")
        elif grouped_lines.get("direct_rule"):
            lines.append("本轮命中了直接适用制度，但未稳定命中更上位的账号权限管理制度。")
        else:
            lines.append("本轮未形成足够完整的正式制度分层证据。")
        lines.append("上位制度依据：")
        lines.extend(grouped_lines.get("governance_base") or ["- 未找到"])
        lines.append("直接适用制度：")
        lines.extend(grouped_lines.get("direct_rule") or ["- 未找到"])
        lines.append("补充参考：")
        lines.extend(grouped_lines.get("supporting_reference") or ["- 未找到"])
        lines.append("与问题对应关系：")
        if grouped_lines.get("governance_base"):
            lines.append("- 上位制度用于说明账号和权限管理的总原则、总体控制要求。")
        if grouped_lines.get("direct_rule"):
            lines.append("- 直接适用制度用于说明具体系统场景下账号申请、保留、注销、锁定或核查要求。")
        if grouped_lines.get("supporting_reference"):
            lines.append("- 补充参考仅用于说明背景或发现情况，不能替代正式制度依据。")
        lines.append("证据缺口：")
        if coverage_issues:
            lines.append("- 当前模型答案未完整覆盖高权威证据分层：" + "、".join(coverage_issues[:4]))
        else:
            lines.append("- 当前未发现额外证据缺口。")
        if unsupported_claims:
            lines.append("- 以下表述未能从命中文档中确认：" + "、".join(unsupported_claims[:6]))
        return "\n".join(lines)

    def _policy_no_evidence_fallback_text(self, user_text: str, executed_events: List[ToolEvent]) -> str:
        search_summaries = [event.summary for event in executed_events if event.name == "policy_doc_search"]
        lines = [
            "结论：",
            "未找到可直接支撑结论的制度证据，当前不能给出条款号、时限或制度名称结论。",
            "上位制度依据：",
            "- 未找到",
            "直接适用制度：",
            "- 未找到",
            "补充参考：",
        ]
        if search_summaries:
            lines.append("- 本轮检索结果：" + "；".join(search_summaries[:3]))
        else:
            lines.append("- 本轮未命中可直接引用的制度原文。")
        lines.append("与问题对应关系：")
        lines.append(f"- 当前问题为：{user_text}")
        lines.append("证据缺口：")
        lines.append("- 建议继续扩大检索关键词，或直接读取更相关的正式制度原文。")
        return "\n".join(lines)

    def _policy_grounded_fallback_text_v2(
        self,
        user_text: str,
        evidence_blocks: List[Dict[str, Any]],
        evidence_profile: Dict[str, Any],
        *,
        unsupported_claims: Optional[List[str]] = None,
    ) -> str:
        del user_text
        section_lines = self._policy_section_summary_lines_v2(evidence_profile, evidence_blocks)
        lines = [
            "结论：",
            "本轮结论仅保留能够被命中文档直接支持的制度依据，优先引用与账号、权限、闲置账号处置最直接对应的正式制度。",
            "主依据（上位制度依据）：",
        ]
        lines.extend(section_lines.get("primary_basis") or ["- 未找到"])
        lines.append("场景补充依据（直接适用制度）：")
        lines.extend(section_lines.get("scenario_basis") or ["- 未找到"])
        lines.append("补充参考：")
        lines.extend(section_lines.get("supporting_reference") or ["- 未找到"])
        lines.append("与问题对应关系：")
        if section_lines.get("primary_basis"):
            lines.append("- 主依据用于回答账号长期未登录、权限保留、权限调整、审计核查等直接控制要求。")
        if section_lines.get("scenario_basis"):
            lines.append("- 场景补充依据仅用于补充特定系统或运维场景下的申请、注销、锁定、核查要求。")
        if section_lines.get("supporting_reference"):
            lines.append("- 补充参考不能替代正式制度依据。")
        lines.append("证据缺口：")
        if unsupported_claims:
            lines.append("- 以下表述未能从命中文档中确认：" + "；".join(unsupported_claims[:6]))
        else:
            lines.append("- 如需更细的条款号、时限或定性结论，仍需继续读取命中文档原文。")
        return "\n".join(lines)

    def _policy_coverage_fallback_text_v2(
        self,
        user_text: str,
        evidence_blocks: List[Dict[str, Any]],
        evidence_profile: Dict[str, Any],
        *,
        unsupported_claims: Optional[List[str]] = None,
        coverage_issues: Optional[List[str]] = None,
    ) -> str:
        lines = [
            self._policy_grounded_fallback_text_v2(
                user_text,
                evidence_blocks,
                evidence_profile,
                unsupported_claims=unsupported_claims,
            ),
            "覆盖校验：",
        ]
        if coverage_issues:
            normalized_issues = [
                "引用了未入选制度" if issue.startswith("unselected_evidence:") else issue
                for issue in coverage_issues[:4]
            ]
            lines.append("- 当前模型答案未完整覆盖主依据结构，或引用了未入选制度；也即未完整覆盖高权威证据分层：" + "；".join(normalized_issues))
        else:
            lines.append("- 当前未发现额外覆盖问题。")
        return "\n".join(lines)

    def _policy_no_evidence_fallback_text_v2(self, user_text: str, executed_events: List[ToolEvent]) -> str:
        search_summaries = [event.summary for event in executed_events if event.name == "policy_doc_search"]
        lines = [
            "结论：",
            "未找到可直接支撑结论的制度证据，当前不能给出条款号、时限或制度名称结论。",
            "主依据（上位制度依据）：",
            "- 未找到",
            "场景补充依据（直接适用制度）：",
            "- 未找到",
            "补充参考：",
        ]
        if search_summaries:
            lines.append("- 本轮检索结果：" + "；".join(search_summaries[:3]))
        else:
            lines.append("- 本轮未命中可直接引用的制度原文。")
        lines.append("与问题对应关系：")
        lines.append(f"- 当前问题为：{user_text}")
        lines.append("证据缺口：")
        lines.append("- 建议继续扩大检索关键词，或直接读取更相关的正式制度原文。")
        return "\n".join(lines)

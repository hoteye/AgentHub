from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli.models import ActivityEvent, ToolEvent
from cli.agent_cli.providers.policy_routing import looks_like_policy_question as _looks_like_policy_question_impl


class PolicyActivityReportingMixin:
    @staticmethod
    def _policy_selected_evidence_detail(evidence_blocks: List[Dict[str, Any]]) -> str:
        lines: List[str] = []
        for block in evidence_blocks[:3]:
            evidence_id = str(block.get("evidence_id") or "").strip()
            title = str(block.get("title") or block.get("doc_id") or "-").strip()
            if evidence_id:
                lines.append(f"[{evidence_id}] {title}")
            else:
                lines.append(title)
        return "\n".join(lines)

    def _policy_activity_events_v2(
        self,
        *,
        user_text: str,
        query_plan: List[str],
        executed_events: List[ToolEvent],
        evidence_blocks: List[Dict[str, Any]],
        evidence_profile: Dict[str, Any],
        final_text: str,
        unsupported_claims: List[str],
        coverage_issues: List[str],
    ) -> List[ActivityEvent]:
        if not (_looks_like_policy_question_impl(user_text) or self._is_policy_grounded_turn(user_text, executed_events)):
            return []

        activities: List[ActivityEvent] = []
        planned_queries = [query for query in query_plan if str(query or "").strip()]
        if planned_queries:
            activities.append(
                ActivityEvent(
                    title="Planned policy queries",
                    status="info",
                    detail="\n".join(f"{index}. {query}" for index, query in enumerate(planned_queries[:4], start=1)),
                    kind="plan",
                    code="policy.plan",
                    params={"queries": list(planned_queries[:4])},
                )
            )

        search_count = sum(1 for event in executed_events if event.name == "policy_doc_search" and event.ok)
        read_count = sum(1 for event in executed_events if event.name == "policy_doc_read" and event.ok)
        normative_count = sum(
            1
            for block in evidence_blocks
            if str(block.get("doc_group") or "") in {"governance_base", "direct_rule"}
            and not bool(block.get("is_noise_candidate"))
        )
        readable_count = sum(
            1
            for block in evidence_blocks
            if str(block.get("doc_group") or "") in {"governance_base", "direct_rule"}
            and str(block.get("text") or "").strip()
            and not bool(block.get("is_noise_candidate"))
        )
        activities.append(
            ActivityEvent(
                title="Retrieved policy evidence",
                status="success" if evidence_blocks else "warning",
                detail=(
                    f"searches={search_count} | reads={read_count} | selected={len(evidence_blocks)} | "
                    f"normative={normative_count} | readable={readable_count}"
                ),
                kind="policy",
                code="policy.retrieve_evidence",
                params={"search_count": search_count, "read_count": read_count, "selected_count": len(evidence_blocks)},
            )
        )

        if evidence_blocks:
            activities.append(
                ActivityEvent(
                    title="Bound evidence answer",
                    status="success",
                    detail=self._policy_selected_evidence_detail(evidence_blocks)
                    + (
                        "\nfocus: "
                        + " | ".join(
                            str(block.get("priority_excerpt") or "").strip()
                            for block in evidence_blocks[:2]
                            if str(block.get("priority_excerpt") or "").strip()
                        )
                        if any(str(block.get("priority_excerpt") or "").strip() for block in evidence_blocks[:2])
                        else ""
                    ),
                    kind="policy",
                    code="policy.bind_answer",
                    params={"selected_count": len(evidence_blocks)},
                )
            )
        else:
            activities.append(
                ActivityEvent(
                    title="Bound evidence answer",
                    status="warning",
                    detail="No selected policy evidence.",
                    kind="policy",
                    code="policy.bind_answer",
                    params={"selected_count": 0},
                )
            )

        verification_parts: List[str] = []
        if evidence_profile:
            verification_parts.append(
                "required_sections=" + ",".join(str(item) for item in list(evidence_profile.get("required_sections") or []))
            )
        if unsupported_claims:
            verification_parts.append("unsupported=" + "; ".join(unsupported_claims[:3]))
        if coverage_issues:
            verification_parts.append("coverage=" + "; ".join(coverage_issues[:3]))
        if not verification_parts:
            verification_parts.append("coverage ok")
        activities.append(
            ActivityEvent(
                title="Verified policy answer",
                status="success" if not unsupported_claims and not coverage_issues and str(final_text or "").strip() else "warning",
                detail="\n".join(verification_parts),
                kind="policy",
                code="policy.verify_answer",
                params={"unsupported_count": len(unsupported_claims), "coverage_issue_count": len(coverage_issues)},
            )
        )
        return activities

    def _native_web_search_activity_events(
        self,
        *,
        user_text: str,
        executed_events: List[ToolEvent],
    ) -> List[ActivityEvent]:
        if not self.use_glm_native_web_search:
            return []
        if any(event.name == "web_search" and event.ok for event in executed_events):
            return []
        browse_events = [
            event
            for event in executed_events
            if event.ok and event.name in {"web_fetch", "open", "find", "click"}
        ]
        if not browse_events:
            return []
        path = " -> ".join(event.name for event in browse_events[:4])
        detail_parts = [
            f"query={str(user_text or '').strip()}",
            "mode=inferred from provider-native search followed by local page inspection",
        ]
        if path:
            detail_parts.append(f"path={path}")
        return [
            ActivityEvent(
                title="Used native web search",
                status="success",
                detail="\n".join(detail_parts),
                kind="web",
                code="web.native_search",
                params={"query": str(user_text or "").strip(), "path": path},
            )
        ]

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from cli.agent_cli.models import PromptAttachment, ToolEvent
from cli.agent_cli.providers.planner_postprocessing import (
    GENERIC_SYNTHESIS_RULES,
    executed_item_event_context_blocks,
    generic_tool_event_context_blocks,
    structured_tool_fallback_text,
)


class ChatCompletionsSynthesisMixin:
    def _synthesis_messages(
        self,
        *,
        user_text: str,
        executed_events: List[ToolEvent],
        executed_item_events: Optional[List[Dict[str, Any]]] = None,
        attachments: Optional[List[PromptAttachment]] = None,
    ) -> List[Dict[str, Any]]:
        evidence_blocks = self._policy_effective_evidence_v2(user_text, self._policy_evidence_blocks(executed_events))
        if self._is_policy_grounded_turn(user_text, executed_events) and evidence_blocks:
            evidence_profile = self._policy_evidence_profile_v2(
                evidence_blocks,
                self._policy_evidence_blocks(executed_events),
            )
            answer_focus = self._policy_answer_focus_hints_v2(user_text, evidence_blocks)
            policy_extract = self._policy_llm_extract(user_text, evidence_blocks) if self.policy_llm_assist else {}
            parts = [
                "You already have the completed tool results for the current turn.",
                "This is an evidence-driven policy QA turn.",
                "Do not call more tools.",
                "Answer in concise Chinese.",
                "Use only the evidence in POLICY_EVIDENCE_JSON.",
                "Prefer POLICY_EXTRACTION_JSON as a structured reading guide, but never go beyond the actual evidence.",
                "Prefer the most directly applicable authority for the user's exact issue, not just the most specific document form.",
                "Cover all required answer sections from POLICY_EVIDENCE_PROFILE_JSON.",
                "Do not add policy names, article numbers, chapter numbers, day-count thresholds, or compliance conclusions unless they appear in the evidence.",
                "If the evidence does not directly support a claim, explicitly say 未找到直接依据.",
                "Cite the supporting policy title and evidence id like [E1] after each conclusion.",
                "Do not mention any policy title that is not included in POLICY_EVIDENCE_PROFILE_JSON answer_sections.",
                "Follow this exact section order: 结论 / 主依据 / 场景补充依据 / 补充参考 / 与问题对应关系 / 证据缺口.",
                "",
                "ORIGINAL_USER_REQUEST:",
                user_text,
                "",
                "POLICY_ANSWER_RULES:",
                "1. Only rely on POLICY_EVIDENCE_JSON.",
                "2. Do not invent any article/chapter/day count.",
                "3. 主依据 must use the most direct formal policy basis for the issue, especially for account, permission, idle-account, adjustment, lock, revoke, and audit topics.",
                "4. 场景补充依据 can only supplement the main basis and cannot replace it.",
                "5. Supporting_reference cannot replace 主依据 or 场景补充依据 when those sections exist.",
                "6. Prefer obligation, prohibition, responsibility-role, and time/frequency items already extracted in POLICY_EXTRACTION_JSON when they are supported by evidence.",
                "7. If evidence is indirect, say it is an inferred management requirement based on the cited evidence.",
                "8. If no direct evidence exists, say 未找到直接依据 and state what was actually found.",
                "9. Keep each evidence citation concise; do not paste long raw excerpts.",
                "10. When citing evidence, prefer [E1]/[E2] style ids from POLICY_EVIDENCE_JSON.",
                "11. When POLICY_ANSWER_FOCUS_JSON highlights an explicit time/frequency sentence, state that exact time requirement directly in the conclusion instead of saying the frequency is unknown.",
                "",
                "POLICY_EVIDENCE_PROFILE_JSON:",
                json.dumps(evidence_profile, ensure_ascii=False, indent=2),
                "",
                "POLICY_EXTRACTION_JSON:",
                json.dumps(policy_extract, ensure_ascii=False, indent=2),
                "",
                "POLICY_ANSWER_FOCUS_JSON:",
                json.dumps(answer_focus, ensure_ascii=False, indent=2),
                "",
                "POLICY_EVIDENCE_JSON:",
                json.dumps(evidence_blocks, ensure_ascii=False, indent=2),
            ]
            return [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": "\n".join(parts)},
            ]
        parts = [
            *GENERIC_SYNTHESIS_RULES,
            "",
            "ORIGINAL_USER_REQUEST:",
            user_text,
            "",
            "TOOL_RESULT_SUMMARY:",
            "\n".join(self._tool_event_summary_lines(executed_events)) or "- no tool events",
            "",
            "TOOL_RESULT_CONTEXT_JSON:",
            json.dumps(generic_tool_event_context_blocks(executed_events), ensure_ascii=False, indent=2),
        ]
        item_blocks = executed_item_event_context_blocks(executed_item_events or [])
        if item_blocks:
            parts.extend(
                [
                    "",
                    "EXECUTED_ITEM_EVENTS_JSON:",
                    json.dumps(item_blocks, ensure_ascii=False, indent=2),
                ]
            )
        attachment_payloads = self._attachment_payloads(attachments)
        if attachment_payloads:
            parts.extend(
                [
                    "",
                    "ATTACHMENTS_JSON:",
                    json.dumps(attachment_payloads, ensure_ascii=False, indent=2),
                ]
            )
        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": "\n".join(parts)},
        ]

    @staticmethod
    def _structured_tool_fallback_text(user_text: str, executed_events: List[ToolEvent]) -> str:
        del user_text
        return structured_tool_fallback_text(executed_events)

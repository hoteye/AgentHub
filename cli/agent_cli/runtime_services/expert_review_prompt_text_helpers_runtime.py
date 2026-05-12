from __future__ import annotations

import json
from collections.abc import Sequence

from cli.agent_cli.runtime_services.expert_review_result_runtime import (
    EXPERT_REVIEW_CONFIDENCE_LEVELS,
    EXPERT_REVIEW_FINDING_CATEGORIES,
    EXPERT_REVIEW_FINDING_SEVERITIES,
    EXPERT_REVIEW_FOCUS_AREAS,
    EXPERT_REVIEW_VERDICTS,
)

_STRICTNESS_GUIDANCE = {
    "low": (
        "Low: report only material, well-supported issues and avoid speculative or stylistic nits."
    ),
    "medium": (
        "Medium: report clear correctness, risk, regression, evidence, completeness, policy, "
        "or code-quality issues that materially affect confidence."
    ),
    "high": (
        "High: apply an adversarial review bar and surface any plausible issue or missing "
        "evidence that could materially change, delay, or block the mainline output."
    ),
}
_POLICY_CONSTRAINT_GUIDANCE = {
    "advisory_only": "Advisory only: the mainline model retains final authority.",
    "read_only_review": (
        "Read-only: do not behave like an executor and do not claim you can edit files, "
        "run commands, or mutate the workspace."
    ),
    "reviewer_read_only": (
        "Read-only: do not behave like an executor and do not claim you can edit files, "
        "run commands, or mutate the workspace."
    ),
    "no_raw_reasoning_requests": (
        "No raw reasoning requests: do not ask for hidden chain-of-thought, commentary, "
        "reasoning items, or encrypted content from the main thread."
    ),
    "no_raw_reasoning": (
        "No raw reasoning requests: do not ask for hidden chain-of-thought, commentary, "
        "reasoning items, or encrypted content from the main thread."
    ),
}


def build_expert_review_system_prompt() -> str:
    lines = [
        "You are AgentHub's external expert reviewer for the expert_review tool.",
        (
            "Provide an advisory, critical, read-only assessment of the mainline candidate "
            "using only the observable review packet."
        ),
        (
            "Do not act as the mainline assistant. Do not claim you can edit files or run "
            "commands. Do not request hidden chain-of-thought, commentary, reasoning items, "
            "or encrypted content from the main thread."
        ),
        (
            "Be skeptical by default: actively look for correctness gaps, missing evidence, "
            "regressions, policy issues, and material risk before accepting."
        ),
        "If the packet lacks evidence, say so explicitly and do not invent missing support.",
        "Return JSON only with keys: verdict, confidence, summary, findings, recommended_action.",
        f"Allowed verdicts: {', '.join(EXPERT_REVIEW_VERDICTS)}.",
        f"Allowed confidence levels: {', '.join(EXPERT_REVIEW_CONFIDENCE_LEVELS)}.",
        "Each finding must contain: severity, category, title, detail, evidence_refs.",
        f"Allowed finding severities: {', '.join(EXPERT_REVIEW_FINDING_SEVERITIES)}.",
        f"Allowed finding categories: {', '.join(EXPERT_REVIEW_FINDING_CATEGORIES)}.",
    ]
    return "\n".join(lines)


def build_expert_review_user_prompt(
    *,
    task: str,
    scope: str,
    focus: Sequence[str],
    strictness: str,
    max_findings: int,
    artifact_paths: Sequence[str],
    user_goal_summary: str,
    candidate_summary: str,
    policy_constraints: Sequence[str],
    additional_instructions: Sequence[str],
    excluded_sources: Sequence[str],
    reasoning_traces_excluded: bool,
    reviewer_packet_json: str,
) -> str:
    lines = [
        "Review request",
        f"task: {task}",
        f"scope: {scope}",
        f"focus: {', '.join(focus)}",
        f"strictness: {strictness}",
        f"max_findings: {max_findings}",
        f"artifact_paths: {', '.join(artifact_paths) if artifact_paths else '(none)'}",
    ]
    if user_goal_summary or candidate_summary:
        lines.extend(
            [
                "",
                "Observable summaries",
                f"user_goal_summary: {user_goal_summary or '-'}",
                f"candidate_summary: {candidate_summary or '-'}",
            ]
        )

    lines.extend(
        [
            "",
            "Review posture",
            (
                "critical_review: actively look for correctness gaps, missing evidence, "
                "regressions, policy issues, and material risks before accepting."
            ),
            f"strictness_guidance: {expert_review_strictness_guidance(strictness)}",
            f"focus_guidance: {_focus_guidance(focus)}",
            f"packet_omissions: {_omissions_guidance(reasoning_traces_excluded, excluded_sources)}",
        ]
    )
    for constraint in policy_constraints:
        lines.append(f"constraint: {_constraint_guidance(constraint)}")
    for instruction in additional_instructions:
        lines.append(f"additional_instruction: {instruction}")

    lines.extend(
        [
            "",
            "Expected JSON response",
            "Return JSON only. Do not include markdown fences or prose outside the JSON object.",
            f"The findings array must contain at most {max_findings} item(s).",
            "```json",
            _expected_output_schema_json(),
            "```",
            "",
            "Observable review packet",
            "```json",
            reviewer_packet_json,
            "```",
        ]
    )
    return "\n".join(lines)


def expert_review_strictness_guidance(strictness: str) -> str:
    return _STRICTNESS_GUIDANCE[strictness]


def _focus_guidance(focus: Sequence[str]) -> str:
    if focus:
        return f"Prioritize these focus areas first: {', '.join(focus)}."
    return (
        "No explicit focus was provided. Review across all core dimensions: "
        + ", ".join(EXPERT_REVIEW_FOCUS_AREAS)
        + "."
    )


def _omissions_guidance(
    reasoning_traces_excluded: bool,
    excluded_sources: Sequence[str],
) -> str:
    omission_summary = (
        "reasoning traces excluded by construction"
        if reasoning_traces_excluded
        else "no explicit reasoning omission flag present"
    )
    if excluded_sources:
        return f"{omission_summary}; excluded_sources={', '.join(excluded_sources)}"
    return omission_summary


def _constraint_guidance(constraint: str) -> str:
    normalized = _normalized_text(constraint).lower()
    if normalized in _POLICY_CONSTRAINT_GUIDANCE:
        return _POLICY_CONSTRAINT_GUIDANCE[normalized]
    return f"Additional constraint: {constraint}."


def _expected_output_schema_json() -> str:
    return json.dumps(
        {
            "verdict": "accept|revise|block|uncertain",
            "confidence": "low|medium|high",
            "summary": "short reviewer summary",
            "findings": [
                {
                    "severity": "low|medium|high|critical",
                    "category": (
                        "correctness|risk|regression|evidence|completeness|policy|"
                        "code_quality|other"
                    ),
                    "title": "brief finding title",
                    "detail": "concise explanation grounded in the packet",
                    "evidence_refs": ["assistant:turn_7"],
                }
            ],
            "recommended_action": "short machine-friendly next step",
        },
        ensure_ascii=False,
        indent=2,
    )


def _normalized_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from cli.agent_cli.runtime_services.expert_review_prompt_normalization_helpers_runtime import (
    normalize_policy,
)
from cli.agent_cli.runtime_services.expert_review_prompt_projection_helpers_runtime import (
    build_reviewer_prompt_metadata,
    serialize_reviewer_packet,
)
from cli.agent_cli.runtime_services.expert_review_prompt_pure_helpers_runtime import (
    build_reviewer_prompt_context,
)
from cli.agent_cli.runtime_services.expert_review_prompt_text_helpers_runtime import (
    build_expert_review_system_prompt,
    build_expert_review_user_prompt,
    expert_review_strictness_guidance,
)
from cli.agent_cli.runtime_services.expert_review_result_runtime import (
    EXPERT_REVIEW_CONFIDENCE_LEVELS,
    EXPERT_REVIEW_FINDING_CATEGORIES,
    EXPERT_REVIEW_FINDING_SEVERITIES,
    EXPERT_REVIEW_FOCUS_AREAS,
    EXPERT_REVIEW_RESULT_CONTRACT_VERSION,
    EXPERT_REVIEW_STRICTNESS_LEVELS,
    EXPERT_REVIEW_TOOL_FAMILY,
    EXPERT_REVIEW_VERDICTS,
)
from cli.agent_cli.runtime_services.expert_review_reviewer_capability_runtime import (
    EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY,
    EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE,
)


EXPERT_REVIEW_PROMPT_CONTRACT_VERSION = "v1"


def build_expert_review_reviewer_prompt(
    packet: Mapping[str, Any] | Any,
    *,
    policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_policy = normalize_policy(policy)
    prompt_context = build_reviewer_prompt_context(
        packet,
        policy=normalized_policy,
        focus_areas=EXPERT_REVIEW_FOCUS_AREAS,
        strictness_levels=EXPERT_REVIEW_STRICTNESS_LEVELS,
    )
    reviewer_packet = dict(prompt_context["reviewer_packet"])
    reviewer_packet_json = serialize_reviewer_packet(reviewer_packet)

    system_prompt = build_expert_review_system_prompt()
    user_prompt = build_expert_review_user_prompt(
        task=str(prompt_context["task"]),
        scope=str(prompt_context["scope"]),
        focus=prompt_context["focus"],
        strictness=str(prompt_context["strictness"]),
        max_findings=int(prompt_context["max_findings"]),
        artifact_paths=prompt_context["artifact_paths"],
        user_goal_summary=str(prompt_context["user_goal_summary"]),
        candidate_summary=str(prompt_context["candidate_summary"]),
        policy_constraints=prompt_context["policy_constraints"],
        additional_instructions=prompt_context["additional_instructions"],
        excluded_sources=prompt_context["excluded_sources"],
        reasoning_traces_excluded=bool(prompt_context["reasoning_traces_excluded"]),
        reviewer_packet_json=reviewer_packet_json,
    )
    metadata = build_reviewer_prompt_metadata(
        prompt_context=prompt_context,
        policy=normalized_policy,
        prompt_contract_version=EXPERT_REVIEW_PROMPT_CONTRACT_VERSION,
        result_contract_version=EXPERT_REVIEW_RESULT_CONTRACT_VERSION,
        tool_family=EXPERT_REVIEW_TOOL_FAMILY,
        reviewer_capability_policy_default=EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY,
        reviewer_capability_source_default=EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE,
        strictness_guidance=expert_review_strictness_guidance(str(prompt_context["strictness"])),
        verdicts=EXPERT_REVIEW_VERDICTS,
        confidence_levels=EXPERT_REVIEW_CONFIDENCE_LEVELS,
        finding_severities=EXPERT_REVIEW_FINDING_SEVERITIES,
        finding_categories=EXPERT_REVIEW_FINDING_CATEGORIES,
    )
    return {
        "contract_version": EXPERT_REVIEW_PROMPT_CONTRACT_VERSION,
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "reviewer_packet": reviewer_packet,
        "reviewer_packet_json": reviewer_packet_json,
        "metadata": metadata,
    }


__all__ = [
    "EXPERT_REVIEW_PROMPT_CONTRACT_VERSION",
    "build_expert_review_reviewer_prompt",
]

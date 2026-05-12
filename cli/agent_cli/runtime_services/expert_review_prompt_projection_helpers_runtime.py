from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from cli.agent_cli.runtime_services.expert_review_prompt_normalization_helpers_runtime import (
    normalized_text,
)


def serialize_reviewer_packet(reviewer_packet: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(reviewer_packet),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def build_reviewer_prompt_metadata(
    *,
    prompt_context: Mapping[str, Any],
    policy: Mapping[str, Any],
    prompt_contract_version: str,
    result_contract_version: str,
    tool_family: str,
    reviewer_capability_policy_default: str,
    reviewer_capability_source_default: str,
    strictness_guidance: str,
    verdicts: Sequence[str],
    confidence_levels: Sequence[str],
    finding_severities: Sequence[str],
    finding_categories: Sequence[str],
) -> dict[str, Any]:
    return {
        "tool_family": tool_family,
        "prompt_contract_version": prompt_contract_version,
        "result_contract_version": result_contract_version,
        "packet_version": normalized_text(prompt_context.get("packet_version")),
        "advisory": True,
        "read_only": True,
        "critical": True,
        "reviewer_capability_policy": normalized_text(policy.get("reviewer_capability_policy"))
        or reviewer_capability_policy_default,
        "reviewer_capability_source": normalized_text(
            policy.get("reviewer_capability_source")
            or policy.get("reviewer_capability_policy_source")
        )
        or reviewer_capability_source_default,
        "reviewer_reasoning_strategy": normalized_text(policy.get("reviewer_reasoning_strategy")),
        "reviewer_reasoning_effort": normalized_text(policy.get("reviewer_reasoning_effort")),
        "reviewer_reasoning_mode": normalized_text(policy.get("reviewer_reasoning_mode")),
        "output_format": "json_object",
        "scope": str(prompt_context["scope"]),
        "scope_source": str(prompt_context["scope_source"]),
        "focus": list(prompt_context["focus"]),
        "focus_source": str(prompt_context["focus_source"]),
        "strictness": str(prompt_context["strictness"]),
        "strictness_source": str(prompt_context["strictness_source"]),
        "strictness_guidance": strictness_guidance,
        "max_findings": int(prompt_context["max_findings"]),
        "max_findings_source": str(prompt_context["max_findings_source"]),
        "artifact_paths": list(prompt_context["artifact_paths"]),
        "policy_constraints": list(prompt_context["policy_constraints"]),
        "additional_instructions": list(prompt_context["additional_instructions"]),
        "sanitized_fields": list(prompt_context["sanitized_fields"]),
        "omissions": {
            "reasoning_traces_excluded": bool(prompt_context["reasoning_traces_excluded"]),
            "excluded_sources": list(prompt_context["excluded_sources"]),
        },
        "expected_output": {
            "verdicts": list(verdicts),
            "confidence_levels": list(confidence_levels),
            "finding_severities": list(finding_severities),
            "finding_categories": list(finding_categories),
        },
    }


__all__ = [
    "build_reviewer_prompt_metadata",
    "serialize_reviewer_packet",
]

from __future__ import annotations

from typing import Any, Dict, Mapping


EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY = "capability_matrix_v1"
EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE = "expert_review_reviewer_capability_matrix_v1"
EXPERT_REVIEW_REASONING_CAPABILITY_VALIDATION = "static_matrix"


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_key(value: Any) -> str:
    return _normalized_text(value).lower()


def _first_present(*values: Any, default: Any = "") -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            if value.strip():
                return value
            continue
        return value
    return default


def expert_review_reviewer_policy_metadata() -> Dict[str, Any]:
    return {
        "reviewer_capability_policy": EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY,
        "reviewer_capability_policy_source": EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE,
        "reasoning_capability_validation": EXPERT_REVIEW_REASONING_CAPABILITY_VALIDATION,
        "reasoning_capability_check_performed": True,
        "reasoning_capability_warning_present": False,
        "reasoning_capability_warning": "",
    }


def resolve_expert_review_reviewer_capability(
    item: Mapping[str, Any] | None = None,
    *,
    provider_name: Any = "",
    config_provider_name: Any = "",
    model: Any = "",
    planner_kind: Any = "",
    wire_api: Any = "",
) -> Dict[str, Any]:
    mapping = dict(item or {})
    provider_public = _normalized_key(
        _first_present(provider_name, mapping.get("provider_name"))
    )
    provider_config = _normalized_key(
        _first_present(config_provider_name, mapping.get("config_provider_name"))
    )
    normalized_model = _normalized_key(
        _first_present(
            model,
            mapping.get("provider_default_model_id"),
            mapping.get("model_id"),
            mapping.get("default_model"),
            mapping.get("model"),
        )
    )
    normalized_planner_kind = _normalized_key(
        _first_present(planner_kind, mapping.get("planner_kind"))
    )
    normalized_wire_api = _normalized_key(_first_present(wire_api, mapping.get("wire_api")))

    family_fingerprint = " ".join(
        part
        for part in (
            provider_public,
            provider_config,
            normalized_model,
        )
        if part
    )
    fingerprint = " ".join(
        part
        for part in (
            family_fingerprint,
            normalized_planner_kind,
            normalized_wire_api,
        )
        if part
    )

    capability = {
        **expert_review_reviewer_policy_metadata(),
        "reviewer_reasoning_strategy": "",
        "reviewer_reasoning_effort": "",
        "reviewer_reasoning_mode": "",
        "reviewer_selection_tier": "unsupported",
        "reviewer_selection_priority": 999,
        "reviewer_eligible": False,
        "reviewer_eligibility_reason": "unsupported_provider_or_model",
    }

    if "openai" in family_fingerprint or provider_public == "openai" or provider_config == "openai":
        capability.update(
            {
                "reviewer_reasoning_strategy": "openai_reasoning_effort",
                "reviewer_reasoning_effort": "xhigh",
                "reviewer_reasoning_mode": "responses.reasoning.effort",
                "reviewer_selection_tier": "openai_xhigh",
                "reviewer_selection_priority": 10,
                "reviewer_eligible": True,
                "reviewer_eligibility_reason": "openai_reasoning_effort_supported",
            }
        )
        return capability

    if (
        "anthropic" in family_fingerprint
        or "claude" in family_fingerprint
        or provider_public == "anthropic"
        or provider_config == "anthropic"
    ):
        if "haiku" in normalized_model:
            capability.update(
                {
                    "reviewer_reasoning_strategy": "anthropic_thinking_excluded",
                    "reviewer_reasoning_mode": "anthropic.thinking",
                    "reviewer_selection_tier": "anthropic_haiku_excluded",
                    "reviewer_selection_priority": 999,
                    "reviewer_eligible": False,
                    "reviewer_eligibility_reason": "anthropic_haiku_not_reviewer_grade",
                }
            )
            return capability
        if "opus" in normalized_model:
            capability.update(
                {
                    "reviewer_reasoning_strategy": "anthropic_reasoning_effort",
                    "reviewer_reasoning_effort": "high",
                    "reviewer_reasoning_mode": "anthropic.thinking",
                    "reviewer_selection_tier": "anthropic_opus_high",
                    "reviewer_selection_priority": 20,
                    "reviewer_eligible": True,
                    "reviewer_eligibility_reason": "anthropic_opus_supported",
                }
            )
            return capability
        capability.update(
            {
                "reviewer_reasoning_strategy": "anthropic_reasoning_effort",
                "reviewer_reasoning_effort": "high",
                "reviewer_reasoning_mode": "anthropic.thinking",
                "reviewer_selection_tier": "anthropic_sonnet_high",
                "reviewer_selection_priority": 21,
                "reviewer_eligible": True,
                "reviewer_eligibility_reason": "anthropic_sonnet_supported",
            }
        )
        return capability

    if (
        "deepseek" in family_fingerprint
        or provider_public == "deepseek"
        or provider_config == "deepseek"
    ):
        if "reasoner" in normalized_model or normalized_planner_kind == "deepseek_reasoner":
            capability.update(
                {
                    "reviewer_reasoning_strategy": "provider_reasoner_model",
                    "reviewer_reasoning_mode": "deepseek.reasoner",
                    "reviewer_selection_tier": "deepseek_reasoner",
                    "reviewer_selection_priority": 30,
                    "reviewer_eligible": True,
                    "reviewer_eligibility_reason": "deepseek_reasoner_supported",
                }
            )
            return capability
        capability.update(
            {
                "reviewer_reasoning_strategy": "best_effort_default_model",
                "reviewer_reasoning_mode": "deepseek.default_model",
                "reviewer_selection_tier": "deepseek_chat_best_effort",
                "reviewer_selection_priority": 39,
                "reviewer_eligible": True,
                "reviewer_eligibility_reason": "deepseek_default_model_best_effort",
            }
        )
        return capability

    if "glm" in family_fingerprint or provider_public == "glm" or provider_config == "glm":
        capability.update(
            {
                "reviewer_reasoning_strategy": "provider_native_reasoning_mode",
                "reviewer_reasoning_mode": "thinking.type",
                "reviewer_selection_tier": "glm_thinking_type",
                "reviewer_selection_priority": 40,
                "reviewer_eligible": True,
                "reviewer_eligibility_reason": "glm_thinking_type_supported",
            }
        )
        return capability

    if "qwen" in family_fingerprint or provider_public == "qwen" or provider_config == "qwen":
        capability.update(
            {
                "reviewer_reasoning_strategy": "provider_native_reasoning_mode",
                "reviewer_reasoning_mode": "enable_thinking",
                "reviewer_selection_tier": "qwen_enable_thinking",
                "reviewer_selection_priority": 50,
                "reviewer_eligible": True,
                "reviewer_eligibility_reason": "qwen_enable_thinking_supported",
            }
        )
        return capability

    return capability


__all__ = [
    "EXPERT_REVIEW_REASONING_CAPABILITY_VALIDATION",
    "EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY",
    "EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE",
    "expert_review_reviewer_policy_metadata",
    "resolve_expert_review_reviewer_capability",
]

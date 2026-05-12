from __future__ import annotations

from cli.agent_cli.runtime_services.expert_review_reviewer_capability_runtime import (
    expert_review_reviewer_policy_metadata,
    resolve_expert_review_reviewer_capability,
)


def test_policy_metadata_uses_static_matrix_contract() -> None:
    metadata = expert_review_reviewer_policy_metadata()

    assert metadata == {
        "reviewer_capability_policy": "capability_matrix_v1",
        "reviewer_capability_policy_source": "expert_review_reviewer_capability_matrix_v1",
        "reasoning_capability_validation": "static_matrix",
        "reasoning_capability_check_performed": True,
        "reasoning_capability_warning_present": False,
        "reasoning_capability_warning": "",
    }


def test_openai_candidate_maps_to_xhigh_reviewer_tier() -> None:
    capability = resolve_expert_review_reviewer_capability(
        {
            "provider_name": "openai",
            "config_provider_name": "openai",
            "provider_default_model_id": "gpt-5.4",
        }
    )

    assert capability["reviewer_eligible"] is True
    assert capability["reviewer_reasoning_strategy"] == "openai_reasoning_effort"
    assert capability["reviewer_reasoning_effort"] == "xhigh"
    assert capability["reviewer_reasoning_mode"] == "responses.reasoning.effort"
    assert capability["reviewer_selection_tier"] == "openai_xhigh"


def test_anthropic_haiku_is_excluded_from_reviewer_candidates() -> None:
    capability = resolve_expert_review_reviewer_capability(
        {
            "provider_name": "anthropic",
            "config_provider_name": "anthropic",
            "provider_default_model_id": "claude-haiku-4-5",
        }
    )

    assert capability["reviewer_eligible"] is False
    assert capability["reviewer_selection_tier"] == "anthropic_haiku_excluded"
    assert capability["reviewer_eligibility_reason"] == "anthropic_haiku_not_reviewer_grade"


def test_glm_uses_provider_native_thinking_mode_without_effort_override() -> None:
    capability = resolve_expert_review_reviewer_capability(
        {
            "provider_name": "glm",
            "config_provider_name": "glm",
            "provider_default_model_id": "glm-4.7",
            "planner_kind": "openai_chat",
        }
    )

    assert capability["reviewer_eligible"] is True
    assert capability["reviewer_reasoning_effort"] == ""
    assert capability["reviewer_reasoning_mode"] == "thinking.type"
    assert capability["reviewer_selection_tier"] == "glm_thinking_type"

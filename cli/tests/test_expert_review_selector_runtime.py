from __future__ import annotations

from types import SimpleNamespace

from cli.agent_cli.runtime_services.expert_review_selector_runtime import (
    select_expert_review_reviewer,
)


def _vendor_for_name(name: str):
    mapping = {
        "openai": "openai",
        "openai_mirror": "openai",
        "anthropic": "anthropic",
        "anthropic_unknown": "anthropic",
        "glm": "glm",
    }
    vendor_name = mapping.get(str(name or "").strip().lower())
    if not vendor_name:
        return None
    return SimpleNamespace(name=vendor_name)


def test_select_expert_review_reviewer_prefers_cross_vendor_available_candidate() -> None:
    result = select_expert_review_reviewer(
        [
            {
                "provider_name": "openai",
                "config_provider_name": "openai",
                "provider_base_eligible": True,
                "availability_status": "available",
            },
            {
                "provider_name": "openai_mirror",
                "config_provider_name": "openai_mirror",
                "provider_base_eligible": True,
                "availability_status": "available",
            },
            {
                "provider_name": "anthropic_unknown",
                "config_provider_name": "anthropic_unknown",
                "provider_base_eligible": True,
                "availability_status": "unknown",
            },
            {
                "provider_name": "anthropic",
                "config_provider_name": "anthropic",
                "provider_base_eligible": True,
                "availability_status": "available",
            },
        ],
        active_provider_name="openai",
        active_provider_public_name="openai",
        vendor_for_name_fn=_vendor_for_name,
    )

    assert result["selected"] is True
    assert result["selection_state"] == "selected"
    assert result["selection_reason"] == "cross_vendor_available"
    assert result["selected_candidate"]["provider_name"] == "anthropic"
    assert result["selected_candidate"]["cross_vendor"] is True
    assert [item["provider_name"] for item in result["ordered_candidates"]] == [
        "anthropic",
        "anthropic_unknown",
        "openai_mirror",
    ]


def test_select_expert_review_reviewer_uses_same_vendor_fallback_with_available_candidates_only() -> None:
    result = select_expert_review_reviewer(
        [
            {
                "provider_name": "openai",
                "config_provider_name": "openai",
                "provider_base_eligible": True,
                "availability_status": "available",
            },
            {
                "provider_name": "openai_mirror",
                "config_provider_name": "openai_mirror",
                "provider_base_eligible": True,
                "availability_status": "available",
            },
            {
                "provider_name": "openai_unknown",
                "config_provider_name": "openai_unknown",
                "provider_base_eligible": True,
                "availability_status": "unknown",
            },
        ],
        active_provider_name="openai",
        active_provider_public_name="openai",
        prefer_cross_vendor=True,
        allow_same_vendor_fallback=True,
        vendor_for_name_fn=lambda name: _vendor_for_name("openai_mirror" if name == "openai_unknown" else name),
    )

    assert result["selected"] is True
    assert result["selection_reason"] == "same_vendor_fallback"
    assert result["same_vendor_fallback_used"] is True
    assert result["selected_candidate"]["provider_name"] == "openai_mirror"
    assert [item["provider_name"] for item in result["ordered_candidates"]] == ["openai_mirror", "openai_unknown"]
    assert [item["selection_bucket"] for item in result["ordered_candidates"]] == [
        "same_vendor_available",
        "same_vendor_unknown",
    ]


def test_select_expert_review_reviewer_uses_unknown_cross_vendor_candidate_when_it_is_the_only_fallback() -> None:
    result = select_expert_review_reviewer(
        [
            {
                "provider_name": "openai",
                "config_provider_name": "openai",
                "provider_base_eligible": True,
                "availability_status": "available",
            },
            {
                "provider_name": "anthropic_unknown",
                "config_provider_name": "anthropic_unknown",
                "provider_base_eligible": True,
                "availability_status": "unknown",
            },
        ],
        active_provider_name="openai",
        active_provider_public_name="openai",
        vendor_for_name_fn=_vendor_for_name,
    )

    assert result["selected"] is True
    assert result["selection_reason"] == "cross_vendor_unknown"
    assert result["selected_candidate"]["provider_name"] == "anthropic_unknown"
    assert result["selected_candidate"]["selection_bucket"] == "cross_vendor_unknown"


def test_select_expert_review_reviewer_prefers_higher_reviewer_tier_within_same_bucket() -> None:
    result = select_expert_review_reviewer(
        [
            {
                "provider_name": "openai",
                "config_provider_name": "openai",
                "provider_base_eligible": True,
                "availability_status": "available",
                "provider_default_model_id": "gpt-5.4",
            },
            {
                "provider_name": "glm",
                "config_provider_name": "glm",
                "provider_base_eligible": True,
                "availability_status": "available",
                "provider_default_model_id": "glm-4.7",
            },
            {
                "provider_name": "anthropic",
                "config_provider_name": "anthropic",
                "provider_base_eligible": True,
                "availability_status": "available",
                "provider_default_model_id": "claude-sonnet-4.6",
            },
        ],
        active_provider_name="openai",
        active_provider_public_name="openai",
        vendor_for_name_fn=_vendor_for_name,
    )

    assert result["selected"] is True
    assert result["selected_candidate"]["provider_name"] == "anthropic"
    assert [item["provider_name"] for item in result["ordered_candidates"]] == [
        "anthropic",
        "glm",
    ]
    assert [item["reviewer_selection_tier"] for item in result["ordered_candidates"]] == [
        "anthropic_sonnet_high",
        "glm_thinking_type",
    ]


def test_select_expert_review_reviewer_respects_disabled_gate() -> None:
    result = select_expert_review_reviewer(
        [
            {
                "provider_name": "openai",
                "config_provider_name": "openai",
                "provider_base_eligible": True,
                "availability_status": "available",
            },
            {
                "provider_name": "anthropic",
                "config_provider_name": "anthropic",
                "provider_base_eligible": True,
                "availability_status": "available",
            },
        ],
        active_provider_name="openai",
        active_provider_public_name="openai",
        review_gate={
            "expert_review_available": False,
            "expert_review_unavailable_reason": "feature_disabled",
            "expert_review_prefer_cross_vendor": True,
            "expert_review_allow_same_vendor_fallback": True,
            "expert_review_reviewer_capability_policy": "capability_matrix_v1",
            "expert_review_reviewer_capability_policy_source": "expert_review_reviewer_capability_matrix_v1",
            "expert_review_reasoning_capability_validation": "static_matrix",
        },
        vendor_for_name_fn=_vendor_for_name,
    )

    assert result["selected"] is False
    assert result["selection_state"] == "unavailable"
    assert result["selection_reason"] == "feature_disabled"
    assert result["selected_candidate"] is None
    assert result["gate"]["expert_review_available"] is False


def test_select_expert_review_reviewer_returns_no_candidate_when_only_primary_provider_is_eligible() -> None:
    result = select_expert_review_reviewer(
        [
            {
                "provider_name": "openai",
                "config_provider_name": "openai",
                "provider_base_eligible": True,
                "availability_status": "available",
            },
            {
                "provider_name": "anthropic",
                "config_provider_name": "anthropic",
                "provider_base_eligible": False,
                "availability_status": "available",
            },
        ],
        active_provider_name="openai",
        active_provider_public_name="openai",
        vendor_for_name_fn=_vendor_for_name,
    )

    assert result["selected"] is False
    assert result["selection_state"] == "unavailable"
    assert result["selection_reason"] == "no_reviewer_candidate"
    assert result["counts"]["reviewer_candidate_count"] == 0
    assert result["ordered_candidates"] == []


def test_select_expert_review_reviewer_exposes_capability_matrix_metadata() -> None:
    result = select_expert_review_reviewer(
        [
            {
                "provider_name": "openai",
                "config_provider_name": "openai",
                "provider_base_eligible": True,
                "availability_status": "available",
            },
            {
                "provider_name": "anthropic",
                "config_provider_name": "anthropic",
                "provider_base_eligible": True,
                "availability_status": "available",
            },
        ],
        active_provider_name="openai",
        active_provider_public_name="openai",
        review_gate={
            "expert_review_available": True,
            "expert_review_unavailable_reason": "-",
            "expert_review_reviewer_capability_policy": "capability_matrix_v1",
            "expert_review_reviewer_capability_policy_source": "expert_review_reviewer_capability_matrix_v1",
            "expert_review_reasoning_capability_validation": "static_matrix",
            "expert_review_prefer_cross_vendor": True,
            "expert_review_allow_same_vendor_fallback": True,
        },
        vendor_for_name_fn=_vendor_for_name,
    )

    assert result["policy"] == {
        "prefer_cross_vendor": True,
        "allow_same_vendor_fallback": True,
        "reviewer_capability_policy": "capability_matrix_v1",
        "reviewer_capability_policy_source": "expert_review_reviewer_capability_matrix_v1",
        "reasoning_capability_validation": "static_matrix",
        "reasoning_capability_check_performed": True,
        "reasoning_capability_warning_present": False,
        "reasoning_capability_warning": "",
    }
    assert result["selected_candidate"]["reviewer_capability_policy"] == "capability_matrix_v1"
    assert result["selected_candidate"]["reviewer_reasoning_strategy"] == "anthropic_reasoning_effort"
    assert result["selected_candidate"]["reviewer_reasoning_effort"] == "high"
    assert result["selected_candidate"]["reviewer_selection_tier"] == "anthropic_sonnet_high"
    assert result["selected_candidate"]["reasoning_capability_validation"] == "static_matrix"
    assert result["selected_candidate"]["reasoning_capability_check_performed"] is True
    assert result["selected_candidate"]["reasoning_capability_warning_present"] is False
    assert result["selected_candidate"]["selection_bucket"] == "cross_vendor_available"

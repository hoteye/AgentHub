from __future__ import annotations

from cli.agent_cli.providers.expert_review_feature_config_runtime import (
    expert_review_feature_settings_from_config,
)


def test_expert_review_feature_settings_defaults() -> None:
    settings = expert_review_feature_settings_from_config({})

    assert settings["enabled"] is True
    assert settings["config_source"] == "default"
    assert settings["min_eligible_providers"] == 2
    assert settings["prefer_cross_vendor"] is True
    assert settings["allow_same_vendor_fallback"] is True
    assert settings["required_reasoning_effort"] == ""
    assert settings["reviewer_capability_policy"] == "capability_matrix_v1"
    assert settings["reviewer_capability_policy_source"] == "expert_review_reviewer_capability_matrix_v1"
    assert settings["reasoning_effort_source"] == "expert_review_reviewer_capability_matrix_v1"
    assert settings["reasoning_capability_validation"] == "static_matrix"


def test_expert_review_feature_settings_reads_workspace_overrides() -> None:
    settings = expert_review_feature_settings_from_config(
        {
            "features": {
                "expert_review": {
                    "enabled": False,
                    "min_eligible_providers": "3",
                    "prefer_cross_vendor": "false",
                    "allow_same_vendor_fallback": "0",
                }
            }
        }
    )

    assert settings["enabled"] is False
    assert settings["config_source"] == "workspace_config"
    assert settings["min_eligible_providers"] == 3
    assert settings["prefer_cross_vendor"] is False
    assert settings["allow_same_vendor_fallback"] is False
    assert settings["required_reasoning_effort"] == ""
    assert settings["reviewer_capability_policy"] == "capability_matrix_v1"


def test_expert_review_feature_settings_accepts_boolean_shorthand() -> None:
    settings = expert_review_feature_settings_from_config(
        {"features": {"expert_review": "off"}}
    )

    assert settings["enabled"] is False
    assert settings["config_source"] == "workspace_config"
    assert settings["min_eligible_providers"] == 2

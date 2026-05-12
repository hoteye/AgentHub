from __future__ import annotations

import pytest

from cli.agent_cli.providers.config_catalog import ProviderConfig
import cli.agent_cli.providers.reference_parity as reference_parity


def _config(model: str) -> ProviderConfig:
    return ProviderConfig(
        model=model,
        api_key="test-key",
        provider_name="openai",
        planner_kind="openai_responses",
        wire_api="openai_responses",
        interaction_profile="codex_openai",
        interaction_profile_source="test",
    )


@pytest.mark.parametrize(
    "model",
    [
        "gpt-5.5",
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.3-codex",
        "gpt-5.2-codex",
        "gpt-5-codex-mini",
        "gpt-oss-20b",
        "gpt-oss-120b",
    ],
)
def test_reference_apply_patch_tool_type_covers_live_codex_ref_freeform_models(model: str) -> None:
    assert reference_parity.reference_apply_patch_tool_type(_config(model)) == "freeform"


@pytest.mark.parametrize(
    ("model", "expected_capable", "expected_detail"),
    [
        ("gpt-5.3-codex", True, "original"),
        ("gpt-5.2-codex", True, None),
        ("gpt-oss-20b", False, None),
        ("gpt-5.4", True, "original"),
        ("gpt-5.5", True, "original"),
        ("gpt-5.4-mini", True, "original"),
    ],
)
def test_reference_view_image_capabilities_follow_frozen_codex_snapshot(
    model: str,
    expected_capable: bool,
    expected_detail: str | None,
) -> None:
    config = _config(model)

    assert reference_parity.reference_view_image_input_capable(config) is expected_capable
    assert reference_parity.reference_view_image_detail(config) == expected_detail


def test_reference_view_image_capabilities_allow_explicit_override() -> None:
    config = ProviderConfig(
        model="gpt-oss-20b",
        api_key="test-key",
        provider_name="openai",
        planner_kind="openai_responses",
        wire_api="openai_responses",
        interaction_profile="codex_openai",
        interaction_profile_source="test",
        raw_provider={"view_image_input_capable": True, "supports_image_detail_original": True},
    )

    assert reference_parity.reference_view_image_input_capable(config) is True
    assert reference_parity.reference_view_image_detail(config) == "original"

from __future__ import annotations

from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.interaction_profile_compat_runtime import (
    legacy_interaction_profile_alias_diagnostics_for_config,
    resolved_interaction_contract_with_fallback,
    resolved_tool_surface_profile_for_config,
)


def _config(
    *,
    planner_kind: str = "openai_responses",
    wire_api: str = "responses",
    interaction_profile: str = "",
    interaction_profile_source: str = "",
    raw_model: dict | None = None,
    raw_provider: dict | None = None,
) -> ProviderConfig:
    return ProviderConfig(
        model="gpt-5.4",
        api_key="sk-test",
        planner_kind=planner_kind,
        wire_api=wire_api,
        interaction_profile=interaction_profile,
        interaction_profile_source=interaction_profile_source,
        raw_model=dict(raw_model or {}),
        raw_provider=dict(raw_provider or {}),
    )


def test_legacy_alias_diagnostics_detects_provider_reference_parity() -> None:
    config = _config(raw_provider={"reference_parity": True})

    diagnostics = legacy_interaction_profile_alias_diagnostics_for_config(config)

    assert diagnostics == {
        "used": True,
        "layer": "provider",
        "field": "reference_parity",
        "source": "provider.reference_parity",
        "effective_profile": "codex_openai",
        "warning": (
            'legacy interaction profile alias `provider.reference_parity` is deprecated; '
            'set `interaction_profile = "codex_openai"` explicitly'
        ),
    }


def test_legacy_alias_diagnostics_ignores_explicit_interaction_profile() -> None:
    config = _config(
        interaction_profile="generic_chat",
        interaction_profile_source="model.interaction_profile",
        raw_provider={"reference_parity": True},
    )

    assert legacy_interaction_profile_alias_diagnostics_for_config(config) == {}


def test_provider_config_public_summary_includes_legacy_alias_diagnostics() -> None:
    config = _config(raw_provider={"codex_parity": True})

    summary = config.public_summary()

    assert summary["interaction_profile_legacy_alias"]["field"] == "codex_parity"
    assert summary["interaction_profile_legacy_alias"]["source"] == "provider.codex_parity"
    assert summary["interaction_profile_legacy_alias"]["effective_profile"] == "codex_openai"


def test_resolved_tool_surface_profile_for_config_legacy_alias_maps_codex_openai() -> None:
    config = _config(raw_provider={"reference_parity": True})

    assert resolved_tool_surface_profile_for_config(config) == "codex_openai"


def test_resolved_interaction_contract_with_fallback_downgrades_incompatible_explicit_profile() -> None:
    config = _config(
        planner_kind="openai_chat",
        wire_api="openai_chat",
        interaction_profile="codex_openai",
        interaction_profile_source="model.interaction_profile",
    )

    contract = resolved_interaction_contract_with_fallback(config)

    assert contract.profile == "generic_chat"
    assert contract.source == "fallback_generic_chat"
    assert "planner_kind `openai_chat`" in contract.conflict_reason

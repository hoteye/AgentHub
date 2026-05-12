from __future__ import annotations

import pytest

from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.interaction_profile_resolution import InteractionProfileCompatibilityError
import cli.agent_cli.providers.interaction_contract_runtime as interaction_contract_runtime


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


def _bundled_specs() -> dict[str, dict[str, object]]:
    return {
        "codex_openai": {
            "profile": "codex_openai",
            "base_prompt_profile": "codex_openai",
            "tool_surface_profile": "codex_openai",
            "context_prelude_policy": "responses_item_first",
            "tool_result_projection_policy": "codex_like",
            "continuation_policy": "responses_native_preferred",
            "turn_protocol_policy": "openai_responses_items",
            "fallback_profile": "generic_chat",
            "allowed_planner_kinds": ["openai_responses"],
            "allowed_wire_apis": ["responses", "openai_responses"],
        },
        "claude_code": {
            "profile": "claude_code",
            "base_prompt_profile": "claude_code",
            "tool_surface_profile": "claude_code",
            "context_prelude_policy": "anthropic_turn",
            "tool_result_projection_policy": "anthropic_like",
            "continuation_policy": "anthropic_native_preferred",
            "turn_protocol_policy": "anthropic_messages_turn",
            "fallback_profile": "generic_chat",
            "allowed_planner_kinds": ["anthropic_messages"],
            "allowed_wire_apis": ["anthropic_messages"],
        },
        "generic_chat": {
            "profile": "generic_chat",
            "base_prompt_profile": "generic_chat",
            "tool_surface_profile": "generic_chat",
            "context_prelude_policy": "generic",
            "tool_result_projection_policy": "generic",
            "continuation_policy": "generic",
            "turn_protocol_policy": "generic",
            "fallback_profile": "none",
            "allowed_planner_kinds": [
                "openai_chat",
                "deepseek_chat",
                "deepseek_reasoner",
            ],
            "allowed_wire_apis": ["openai_chat"],
        },
    }


@pytest.fixture(autouse=True)
def _clear_runtime_cache() -> None:
    interaction_contract_runtime._cached_bundled_interaction_profile_specs.cache_clear()
    interaction_contract_runtime._cached_bundled_specs_by_tool_surface_profile.cache_clear()
    yield
    interaction_contract_runtime._cached_bundled_interaction_profile_specs.cache_clear()
    interaction_contract_runtime._cached_bundled_specs_by_tool_surface_profile.cache_clear()


def test_resolved_interaction_contract_for_config_uses_explicit_profile() -> None:
    contract = interaction_contract_runtime.resolved_interaction_contract_for_config(
        _config(
            interaction_profile="codex_openai",
            interaction_profile_source="model.interaction_profile",
        )
    )

    assert contract.profile == "codex_openai"
    assert contract.source == "model.interaction_profile"
    assert contract.turn_protocol_policy == "openai_responses_items"


def test_resolved_interaction_contract_for_config_falls_back_to_legacy_alias() -> None:
    contract = interaction_contract_runtime.resolved_interaction_contract_for_config(
        _config(
            interaction_profile="",
            interaction_profile_source="",
            raw_provider={"codex_parity": True},
        )
    )

    assert contract.profile == "codex_openai"
    assert contract.source == "provider.codex_parity"


def test_resolved_interaction_contract_for_config_empty_config_defaults_to_generic_chat() -> None:
    contract = interaction_contract_runtime.resolved_interaction_contract_for_config(
        _config(
            planner_kind="openai_chat",
            wire_api="openai_chat",
            interaction_profile="",
            interaction_profile_source="",
        )
    )

    assert contract.profile == "generic_chat"
    assert contract.source == "default"
    assert contract.conflict_reason == ""


def test_resolved_interaction_contract_for_config_incompatible_explicit_profile_is_hard_error() -> None:
    with pytest.raises(InteractionProfileCompatibilityError):
        interaction_contract_runtime.resolved_interaction_contract_for_config(
            _config(
                planner_kind="openai_chat",
                wire_api="openai_chat",
                interaction_profile="codex_openai",
                interaction_profile_source="model.interaction_profile",
            )
        )


def test_resolved_interaction_contract_for_config_caches_bundled_profile_load(monkeypatch: pytest.MonkeyPatch) -> None:
    load_count = {"value": 0}

    def _fake_loader() -> dict[str, dict[str, object]]:
        load_count["value"] += 1
        return _bundled_specs()

    monkeypatch.setattr(interaction_contract_runtime, "load_bundled_interaction_profiles", _fake_loader)

    first = interaction_contract_runtime.resolved_interaction_contract_for_config(
        _config(
            interaction_profile="codex_openai",
            interaction_profile_source="model.interaction_profile",
        )
    )
    second = interaction_contract_runtime.resolved_interaction_contract_for_config(
        _config(
            interaction_profile="codex_openai",
            interaction_profile_source="model.interaction_profile",
        )
    )

    assert first.profile == "codex_openai"
    assert second.profile == "codex_openai"
    assert load_count["value"] == 1


def test_plugin_declaration_contract_metadata_returns_task_a_fields() -> None:
    metadata = interaction_contract_runtime.plugin_declaration_contract_metadata(
        {
            "canonical_family": "command_execution",
            "canonical_family_source": "builtin",
            "canonical_family_owner": "builtin",
            "canonical_family_alias_input": "shell",
            "tool_capability_kind": "local_runtime_tool",
            "tool_runtime_binding": "local_runtime",
            "canonical_family_record": {
                "canonical_family": "command_execution",
                "family_source": "builtin",
                "family_owner": "builtin",
                "canonical_tool_names": ["exec_command", "write_stdin"],
            },
        }
    )

    assert metadata["canonical_family"] == "command_execution"
    assert metadata["canonical_family_source"] == "builtin"
    assert metadata["canonical_family_owner"] == "builtin"
    assert metadata["canonical_family_alias_input"] == "shell"
    assert metadata["tool_capability_kind"] == "local_runtime_tool"
    assert metadata["tool_runtime_binding"] == "local_runtime"
    assert metadata["canonical_family_record"]["canonical_tool_names"] == ["exec_command", "write_stdin"]


def test_interaction_contract_metadata_for_tool_surface_profile_returns_policies() -> None:
    metadata = interaction_contract_runtime.interaction_contract_metadata_for_tool_surface_profile("codex_openai")

    assert metadata["profile"] == "codex_openai"
    assert metadata["tool_surface_profile"] == "codex_openai"
    assert metadata["tool_result_projection_policy"] == "codex_like"
    assert metadata["continuation_policy"] == "responses_native_preferred"
    assert metadata["turn_protocol_policy"] == "openai_responses_items"
    assert metadata["optional_capabilities"]["native_web_search_runtime"] is True


def test_interaction_contract_tool_family_metadata_matches_canonical_family() -> None:
    metadata = interaction_contract_runtime.interaction_contract_tool_family_metadata(
        tool_surface_profile="claude_code",
        canonical_family="command_execution",
    )

    assert metadata["canonical_family"] == "command_execution"
    assert metadata["projection"] == "claude_shell_split"
    assert metadata["projected_primary_tools"] == ["Bash", "PowerShell"]
    assert metadata["projected_continuation_tools"] == ["write_stdin"]


def test_interaction_contract_metadata_uses_cached_tool_surface_profile_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_count = {"value": 0}

    def _fake_loader() -> dict[str, dict[str, object]]:
        load_count["value"] += 1
        return {
            "responses_openai_alias": {
                "profile": "responses_openai_alias",
                "tool_surface_profile": "codex_openai",
                "tool_result_projection_policy": "codex_like",
                "continuation_policy": "responses_native_preferred",
                "turn_protocol_policy": "openai_responses_items",
                "fallback_profile": "generic_chat",
                "optional_capabilities": {"native_web_search_runtime": True},
                "plugin_exposure_policy": {"mode": "allow"},
                "tool_families": {
                    "command_execution": {
                        "name": "shell",
                        "canonical_family": "command_execution",
                        "projection": "codex_shell_unified",
                        "projected_primary_tools": ["exec_command"],
                        "projected_continuation_tools": ["write_stdin"],
                    }
                },
            }
        }

    monkeypatch.setattr(interaction_contract_runtime, "load_bundled_interaction_profiles", _fake_loader)

    metadata = interaction_contract_runtime.interaction_contract_metadata_for_tool_surface_profile("codex_openai")
    family = interaction_contract_runtime.interaction_contract_tool_family_metadata(
        tool_surface_profile="codex_openai",
        canonical_family="command_execution",
    )

    assert metadata["profile"] == "responses_openai_alias"
    assert metadata["tool_surface_profile"] == "codex_openai"
    assert family["canonical_family"] == "command_execution"
    assert family["projection"] == "codex_shell_unified"
    assert load_count["value"] == 1

from __future__ import annotations

import pytest

from cli.agent_cli.providers.interaction_profile_resolution import (
    InteractionProfileCompatibilityError,
    resolve_interaction_contract,
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


def test_resolve_interaction_contract_explicit_happy_path() -> None:
    contract = resolve_interaction_contract(
        configured_profile="codex_openai",
        profile_source="model.interaction_profile",
        bundled_profile_specs=_bundled_specs(),
        planner_kind="openai_responses",
        wire_api="responses",
    )

    assert contract.profile == "codex_openai"
    assert contract.source == "model.interaction_profile"
    assert contract.turn_protocol_policy == "openai_responses_items"
    assert contract.conflict_reason == ""


def test_resolve_interaction_contract_explicit_conflict_hard_error() -> None:
    with pytest.raises(InteractionProfileCompatibilityError) as exc_info:
        resolve_interaction_contract(
            configured_profile="codex_openai",
            profile_source="model.interaction_profile",
            bundled_profile_specs=_bundled_specs(),
            planner_kind="openai_chat",
            wire_api="openai_chat",
        )

    assert "incompatible" in str(exc_info.value)
    assert "planner_kind `openai_chat`" in exc_info.value.conflict_reason


def test_resolve_interaction_contract_inferred_conflict_falls_back_to_generic_chat() -> None:
    contract = resolve_interaction_contract(
        configured_profile="claude_code",
        profile_source="catalog_default",
        bundled_profile_specs=_bundled_specs(),
        planner_kind="openai_chat",
        wire_api="openai_chat",
    )

    assert contract.profile == "generic_chat"
    assert contract.source == "fallback_generic_chat"
    assert contract.conflict_reason
    assert "claude_code" in contract.conflict_reason


def test_resolve_interaction_contract_snapshot_fields() -> None:
    contract = resolve_interaction_contract(
        configured_profile="codex_openai",
        profile_source="model.interaction_profile",
        bundled_profile_specs=_bundled_specs(),
        planner_kind="openai_responses",
        wire_api="responses",
    )

    assert contract.as_dict() == {
        "profile": "codex_openai",
        "source": "model.interaction_profile",
        "base_prompt_profile": "codex_openai",
        "tool_surface_profile": "codex_openai",
        "context_prelude_policy": "responses_item_first",
        "tool_result_projection_policy": "codex_like",
        "continuation_policy": "responses_native_preferred",
        "turn_protocol_policy": "openai_responses_items",
        "fallback_profile": "generic_chat",
        "conflict_reason": "",
    }


def test_resolve_interaction_contract_treats_provider_legacy_alias_source_as_explicit() -> None:
    with pytest.raises(InteractionProfileCompatibilityError):
        resolve_interaction_contract(
            configured_profile="codex_openai",
            profile_source="provider.reference_parity",
            bundled_profile_specs=_bundled_specs(),
            planner_kind="openai_chat",
            wire_api="openai_chat",
        )

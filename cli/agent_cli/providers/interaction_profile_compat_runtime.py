from __future__ import annotations

from typing import Any

from cli.agent_cli.providers.interaction_contract import ResolvedInteractionContract
from cli.agent_cli.providers.interaction_profile_config import (
    LEGACY_CODEX_PROFILE,
    normalize_interaction_profile,
    resolve_configured_interaction_profile,
)
from cli.agent_cli.providers.interaction_profile_loader import load_bundled_interaction_profiles
from cli.agent_cli.providers.interaction_profile_resolution import resolve_interaction_contract

_GENERIC_CHAT_PROFILE = "generic_chat"
_LEGACY_ALIAS_KEYS = frozenset({"codex_parity", "reference_parity"})


def configured_interaction_profile_for_config(config: Any) -> tuple[str, str]:
    explicit_profile = normalize_interaction_profile(getattr(config, "interaction_profile", ""))
    explicit_source = str(getattr(config, "interaction_profile_source", "") or "").strip()
    if explicit_profile:
        return explicit_profile, explicit_source or "explicit"
    return resolve_configured_interaction_profile(
        raw_model=dict(getattr(config, "raw_model", {}) or {}),
        raw_provider=dict(getattr(config, "raw_provider", {}) or {}),
    )


def fallback_generic_interaction_contract(
    *,
    source: str = "fallback_generic_chat",
    conflict_reason: str = "",
) -> ResolvedInteractionContract:
    return ResolvedInteractionContract(
        profile=_GENERIC_CHAT_PROFILE,
        source=source,
        base_prompt_profile=_GENERIC_CHAT_PROFILE,
        tool_surface_profile=_GENERIC_CHAT_PROFILE,
        context_prelude_policy="generic",
        tool_result_projection_policy="generic",
        continuation_policy="generic",
        turn_protocol_policy="generic",
        fallback_profile="none",
        conflict_reason=conflict_reason,
    )


def resolved_interaction_contract_with_fallback(config: Any) -> ResolvedInteractionContract:
    try:
        from cli.agent_cli.providers.interaction_contract_runtime import resolved_interaction_contract_for_config

        return resolved_interaction_contract_for_config(config)
    except Exception as exc:
        configured_profile, profile_source = configured_interaction_profile_for_config(config)
        try:
            return resolve_interaction_contract(
                configured_profile=configured_profile,
                profile_source=str(profile_source or "default"),
                bundled_profile_specs=load_bundled_interaction_profiles(),
                planner_kind=str(getattr(config, "planner_kind", "") or "").strip(),
                wire_api=str(getattr(config, "wire_api", "") or "").strip(),
            )
        except Exception:
            conflict_reason = str(getattr(exc, "conflict_reason", "") or "").strip()
            return fallback_generic_interaction_contract(conflict_reason=conflict_reason)


def resolved_tool_surface_profile_for_config(config: Any) -> str:
    contract = resolved_interaction_contract_with_fallback(config)
    tool_surface_profile = normalize_interaction_profile(getattr(contract, "tool_surface_profile", ""))
    if tool_surface_profile:
        return tool_surface_profile
    return normalize_interaction_profile(getattr(contract, "profile", ""))


def legacy_interaction_profile_alias_diagnostics_for_source(
    source: Any,
    *,
    effective_profile: Any = "",
) -> dict[str, Any]:
    source_text = str(source or "").strip().lower()
    if not source_text or "." not in source_text:
        return {}
    layer, _, field = source_text.partition(".")
    if layer not in {"model", "provider"} or field not in _LEGACY_ALIAS_KEYS:
        return {}
    normalized_profile = normalize_interaction_profile(effective_profile) or LEGACY_CODEX_PROFILE
    return {
        "used": True,
        "layer": layer,
        "field": field,
        "source": f"{layer}.{field}",
        "effective_profile": normalized_profile,
        "warning": (
            f"legacy interaction profile alias `{layer}.{field}` is deprecated; "
            f'set `interaction_profile = "{normalized_profile}"` explicitly'
        ),
    }


def legacy_interaction_profile_alias_diagnostics_for_config(config: Any) -> dict[str, Any]:
    profile, source = configured_interaction_profile_for_config(config)
    return legacy_interaction_profile_alias_diagnostics_for_source(
        source,
        effective_profile=profile,
    )

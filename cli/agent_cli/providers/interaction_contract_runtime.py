from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, Mapping

from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.interaction_contract import ResolvedInteractionContract
from cli.agent_cli.providers.interaction_profile_config import resolve_configured_interaction_profile
from cli.agent_cli.providers.interaction_profile_loader import load_bundled_interaction_profiles
from cli.agent_cli.providers.interaction_profile_resolution import resolve_interaction_contract


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _field_value(payload: Any, key: str) -> Any:
    if isinstance(payload, Mapping):
        return payload.get(key)
    return getattr(payload, key, None)


def _field_text(payload: Any, key: str) -> str:
    return str(_field_value(payload, key) or "").strip()


def _mapping_dict(payload: Any, key: str) -> Dict[str, Any]:
    value = _field_value(payload, key)
    if isinstance(value, Mapping):
        return dict(value)
    return {}


@lru_cache(maxsize=1)
def _cached_bundled_interaction_profile_specs() -> Mapping[str, Any]:
    return load_bundled_interaction_profiles()


@lru_cache(maxsize=1)
def _cached_bundled_specs_by_tool_surface_profile() -> Mapping[str, Any]:
    index: dict[str, Any] = {}
    for spec in _cached_bundled_interaction_profile_specs().values():
        normalized_profile = _normalized_text(_field_text(spec, "tool_surface_profile"))
        if normalized_profile and normalized_profile not in index:
            index[normalized_profile] = spec
    return index


def _bundled_spec_for_tool_surface_profile(tool_surface_profile: str) -> Any:
    normalized_profile = _normalized_text(tool_surface_profile)
    if not normalized_profile:
        return None
    bundled_specs = _cached_bundled_interaction_profile_specs()
    direct_spec = bundled_specs.get(normalized_profile)
    if direct_spec is not None:
        return direct_spec
    return _cached_bundled_specs_by_tool_surface_profile().get(normalized_profile)


def _effective_profile_and_source(config: ProviderConfig) -> tuple[str, str]:
    explicit_profile = _normalized_text(config.interaction_profile)
    explicit_source = str(config.interaction_profile_source or "").strip()
    if explicit_profile:
        return explicit_profile, explicit_source or "explicit"

    fallback_profile, fallback_source = resolve_configured_interaction_profile(
        raw_model=config.raw_model,
        raw_provider=config.raw_provider,
    )
    normalized_fallback_profile = _normalized_text(fallback_profile)
    if normalized_fallback_profile:
        return normalized_fallback_profile, fallback_source
    return "", ""


def resolved_interaction_contract_for_config(config: ProviderConfig) -> ResolvedInteractionContract:
    configured_profile, profile_source = _effective_profile_and_source(config)
    return resolve_interaction_contract(
        configured_profile=configured_profile,
        profile_source=profile_source,
        bundled_profile_specs=_cached_bundled_interaction_profile_specs(),
        planner_kind=str(config.planner_kind or ""),
        wire_api=str(config.wire_api or ""),
    )


def interaction_contract_metadata_for_tool_surface_profile(tool_surface_profile: str) -> Dict[str, Any]:
    normalized_profile = _normalized_text(tool_surface_profile)
    if not normalized_profile:
        return {}
    spec = _bundled_spec_for_tool_surface_profile(normalized_profile)
    if spec is None:
        return {}
    return {
        "profile": _field_text(spec, "profile") or normalized_profile,
        "tool_surface_profile": _field_text(spec, "tool_surface_profile") or normalized_profile,
        "tool_result_projection_policy": _field_text(spec, "tool_result_projection_policy"),
        "continuation_policy": _field_text(spec, "continuation_policy"),
        "turn_protocol_policy": _field_text(spec, "turn_protocol_policy"),
        "fallback_profile": _field_text(spec, "fallback_profile"),
        "optional_capabilities": _mapping_dict(spec, "optional_capabilities"),
        "plugin_exposure_policy": _mapping_dict(spec, "plugin_exposure_policy"),
    }


def interaction_contract_tool_family_metadata(
    *,
    tool_surface_profile: str,
    canonical_family: str,
) -> Dict[str, Any]:
    normalized_profile = _normalized_text(tool_surface_profile)
    normalized_family = _normalized_text(canonical_family)
    if not normalized_profile or not normalized_family:
        return {}
    spec = _bundled_spec_for_tool_surface_profile(normalized_profile)
    if spec is None:
        return {}
    tool_families = _mapping_dict(spec, "tool_families")
    for key, value in tool_families.items():
        family_key = _normalized_text(key)
        family_name = _normalized_text(_field_text(value, "name") or family_key)
        family_canonical = _normalized_text(_field_text(value, "canonical_family") or family_name)
        if normalized_family not in {family_key, family_name, family_canonical}:
            continue
        return {
            "name": _field_text(value, "name") or str(key or "").strip(),
            "canonical_family": _field_text(value, "canonical_family") or str(key or "").strip(),
            "exposure": _field_text(value, "exposure"),
            "projection": _field_text(value, "projection"),
            "fallback_backend": _field_text(value, "fallback_backend"),
            "projection_surface_family": _field_text(value, "projection_surface_family"),
            "projected_primary_tools": list(_field_value(value, "projected_primary_tools") or ()),
            "projected_continuation_tools": list(_field_value(value, "projected_continuation_tools") or ()),
            "compatibility_aliases": list(_field_value(value, "compatibility_aliases") or ()),
            "event_projection_name": _field_text(value, "event_projection_name"),
        }
    return {}


def plugin_declaration_contract_metadata(declaration: Mapping[str, Any]) -> Dict[str, Any]:
    record = declaration.get("canonical_family_record")
    record_mapping = dict(record) if isinstance(record, Mapping) else {}
    canonical_family = str(declaration.get("canonical_family") or record_mapping.get("canonical_family") or "").strip()
    tool_capability_kind = str(
        declaration.get("tool_capability_kind") or record_mapping.get("tool_capability_kind") or ""
    ).strip()
    tool_runtime_binding = str(
        declaration.get("tool_runtime_binding") or record_mapping.get("tool_runtime_binding") or ""
    ).strip()
    return {
        "canonical_family": canonical_family,
        "canonical_family_source": str(
            declaration.get("canonical_family_source") or record_mapping.get("family_source") or ""
        ).strip(),
        "canonical_family_owner": str(
            declaration.get("canonical_family_owner") or record_mapping.get("family_owner") or ""
        ).strip(),
        "canonical_family_alias_input": str(declaration.get("canonical_family_alias_input") or "").strip(),
        "tool_capability_kind": tool_capability_kind,
        "tool_runtime_binding": tool_runtime_binding,
        "canonical_family_record": dict(record_mapping),
    }

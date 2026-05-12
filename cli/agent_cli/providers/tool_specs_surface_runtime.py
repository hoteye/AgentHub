from __future__ import annotations

from typing import Any, Callable, Dict, List, Tuple

from cli.agent_cli.providers import builtin_provider_delegation_specs as builtin_provider_delegation_specs_helpers
from cli.agent_cli.providers import tool_family_mapping_runtime as tool_family_mapping_runtime_helpers
from cli.agent_cli.providers import tool_family_registry
from cli.agent_cli.providers.config_catalog import ProviderConfig, optional_bool
from cli.agent_cli.providers.interaction_profile_compat_runtime import (
    resolved_tool_surface_profile_for_config,
)
from cli.agent_cli.providers.interaction_profile_config import LEGACY_CODEX_PROFILE
from cli.agent_cli.providers.reference_parity import reference_apply_patch_tool_type

FunctionNameFromSpec = Callable[[Any], str]
ResolveNativeWebSearchCapability = Callable[[ProviderConfig], Any]
ResolveToolSurfaceProfile = Callable[[ProviderConfig], str]

_MODEL_HIDDEN_COMPAT_ALIASES_ORDERED: Tuple[str, ...] = tuple(
    getattr(
        tool_family_mapping_runtime_helpers,
        "MODEL_HIDDEN_BUILTIN_COMPAT_ALIASES",
        ("file_search", "file_read", "file_list", "shell", "open", "click", "find"),
    )
)
_MODEL_HIDDEN_COMPAT_ALIASES = frozenset(_MODEL_HIDDEN_COMPAT_ALIASES_ORDERED)
_CODEX_REFERENCE_DEFAULT_MODEL_HIDDEN_TOOLS = frozenset(
    (
        *builtin_provider_delegation_specs_helpers.delegation_tool_spec_order(),
        *builtin_provider_delegation_specs_helpers.visible_delegation_tool_order(
            tool_surface_profile=LEGACY_CODEX_PROFILE
        ),
    )
)


def model_hidden_compat_aliases_ordered() -> Tuple[str, ...]:
    return _MODEL_HIDDEN_COMPAT_ALIASES_ORDERED


def tool_surface_profile(
    config: ProviderConfig,
    *,
    resolved_tool_surface_profile_for_config_fn: ResolveToolSurfaceProfile | None = None,
) -> str:
    resolver = resolved_tool_surface_profile_for_config_fn or resolved_tool_surface_profile_for_config
    return resolver(config) or "generic_chat"


def is_model_hidden_compat_alias(name: str) -> bool:
    normalized = str(name or "").strip()
    if not normalized:
        return False
    if normalized in _MODEL_HIDDEN_COMPAT_ALIASES:
        return True
    metadata = tool_family_registry.builtin_tool_metadata(normalized) or {}
    marker = str(metadata.get("model_default_exposure") or "").strip().lower()
    return marker == "compatibility_alias"


def web_search_hidden_from_model_surface(
    config: ProviderConfig,
    *,
    resolve_native_web_search_capability_fn: ResolveNativeWebSearchCapability,
) -> bool:
    capability = resolve_native_web_search_capability_fn(config)
    return str(getattr(capability, "effective_mode", "") or "").strip().lower() == "disabled"


def expert_review_snapshot_mappings(config: ProviderConfig) -> Tuple[Dict[str, Any], ...]:
    mappings: List[Dict[str, Any]] = []
    for root in (
        getattr(config, "raw_provider", {}) or {},
        getattr(config, "raw_model", {}) or {},
    ):
        if not isinstance(root, dict):
            continue
        mappings.append(dict(root))
        for key in ("provider_status", "expert_review_gate_snapshot", "expert_review_gate"):
            nested = root.get(key)
            if isinstance(nested, dict):
                mappings.append(dict(nested))
    return tuple(mappings)


def expert_review_visible_in_model_surface(
    config: ProviderConfig,
    *,
    resolved_tool_surface_profile_for_config_fn: ResolveToolSurfaceProfile | None = None,
) -> bool:
    if tool_surface_profile(
        config,
        resolved_tool_surface_profile_for_config_fn=resolved_tool_surface_profile_for_config_fn,
    ) == LEGACY_CODEX_PROFILE:
        return False
    for mapping in expert_review_snapshot_mappings(config):
        if "expert_review_available" not in mapping:
            continue
        return optional_bool(mapping.get("expert_review_available"), False)
    return False


def is_model_hidden_builtin(
    name: str,
    *,
    config: ProviderConfig,
    resolve_native_web_search_capability_fn: ResolveNativeWebSearchCapability,
    resolved_tool_surface_profile_for_config_fn: ResolveToolSurfaceProfile | None = None,
) -> bool:
    normalized = str(name or "").strip()
    if not normalized:
        return False
    tool_surface = tool_surface_profile(
        config,
        resolved_tool_surface_profile_for_config_fn=resolved_tool_surface_profile_for_config_fn,
    )
    if tool_surface == LEGACY_CODEX_PROFILE and normalized in _CODEX_REFERENCE_DEFAULT_MODEL_HIDDEN_TOOLS:
        return True
    metadata = tool_family_registry.builtin_tool_metadata(normalized) or {}
    marker = str(metadata.get("model_default_exposure") or "").strip().lower()
    if marker == "internal_only":
        return True
    if is_model_hidden_compat_alias(normalized):
        return True
    if normalized == "apply_patch" and tool_surface == LEGACY_CODEX_PROFILE:
        return reference_apply_patch_tool_type(config) is None
    if normalized == "web_search":
        return web_search_hidden_from_model_surface(
            config,
            resolve_native_web_search_capability_fn=resolve_native_web_search_capability_fn,
        )
    if normalized == "expert_review":
        return not expert_review_visible_in_model_surface(
            config,
            resolved_tool_surface_profile_for_config_fn=resolved_tool_surface_profile_for_config_fn,
        )
    return False


def filter_model_facing_provider_specs(
    specs: List[Dict[str, Any]],
    *,
    config: ProviderConfig,
    function_name_from_spec: FunctionNameFromSpec,
    resolve_native_web_search_capability_fn: ResolveNativeWebSearchCapability,
    resolved_tool_surface_profile_for_config_fn: ResolveToolSurfaceProfile | None = None,
) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for item in list(specs or []):
        if not isinstance(item, dict):
            continue
        function_name = function_name_from_spec(item)
        if function_name and is_model_hidden_builtin(
            function_name,
            config=config,
            resolve_native_web_search_capability_fn=resolve_native_web_search_capability_fn,
            resolved_tool_surface_profile_for_config_fn=resolved_tool_surface_profile_for_config_fn,
        ):
            continue
        filtered.append(dict(item))
    return filtered

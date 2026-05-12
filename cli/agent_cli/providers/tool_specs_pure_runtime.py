from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Pattern, Tuple

from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.providers import provider_tool_registry as provider_tool_registry_helpers
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.interaction_profile_config import LEGACY_CODEX_PROFILE
from cli.agent_cli.providers.reference_parity_tool_specs import reference_parity_responses_minimal_tool_specs

PluginManagerFactory = Callable[[], Optional[PluginManager]]
ResolveNativeWebSearchCapability = Callable[[ProviderConfig], Any]
ToolSurfaceProfile = Callable[[ProviderConfig], str]
FunctionNameFromSpec = Callable[[Any], str]
IsModelHiddenBuiltin = Callable[..., bool]
ProjectModelFacingProviderNames = Callable[..., List[str]]
BuiltinProviderToolSpecs = Callable[..., List[Dict[str, Any]]]
FilterModelFacingProviderSpecs = Callable[..., List[Dict[str, Any]]]
ProjectModelFacingProviderSpecs = Callable[..., List[Dict[str, Any]]]


def supports_glm_native_web_search(
    config: ProviderConfig,
    *,
    resolve_native_web_search_capability_fn: ResolveNativeWebSearchCapability,
) -> bool:
    capability = resolve_native_web_search_capability_fn(config)
    return capability.main_loop_spec_kind == "glm_native"


def supports_openai_responses_native_web_search(
    config: ProviderConfig,
    *,
    resolve_native_web_search_capability_fn: ResolveNativeWebSearchCapability,
) -> bool:
    capability = resolve_native_web_search_capability_fn(config)
    return capability.supports_runtime_native and capability.selected_backend == "provider_native_openai_responses_web_search"


def supports_native_web_search_mixed_tools(
    config: ProviderConfig,
    *,
    resolve_native_web_search_capability_fn: ResolveNativeWebSearchCapability,
) -> bool:
    return bool(resolve_native_web_search_capability_fn(config).supports_mixed_tools_native)


def supports_openai_responses_native_web_search_mixed_tools(
    config: ProviderConfig,
    *,
    resolve_native_web_search_capability_fn: ResolveNativeWebSearchCapability,
) -> bool:
    capability = resolve_native_web_search_capability_fn(config)
    return capability.main_loop_spec_kind == "openai_responses_native"


def supports_anthropic_native_web_search(
    config: ProviderConfig,
    *,
    resolve_native_web_search_capability_fn: ResolveNativeWebSearchCapability,
) -> bool:
    capability = resolve_native_web_search_capability_fn(config)
    return capability.supports_runtime_native and capability.selected_backend == "provider_native_anthropic_web_search"


def supports_anthropic_native_web_search_mixed_tools(
    config: ProviderConfig,
    *,
    resolve_native_web_search_capability_fn: ResolveNativeWebSearchCapability,
) -> bool:
    capability = resolve_native_web_search_capability_fn(config)
    return capability.main_loop_spec_kind == "anthropic_native"


def provider_tool_names(
    config: ProviderConfig,
    host_platform: HostPlatform,
    *,
    plugin_manager_factory: PluginManagerFactory | None = None,
    model_facing_builtin_tool_order: Tuple[str, ...],
    tool_surface_profile_fn: ToolSurfaceProfile,
    function_name_from_spec: FunctionNameFromSpec,
    is_model_hidden_builtin_fn: IsModelHiddenBuiltin,
    project_model_facing_provider_names_fn: ProjectModelFacingProviderNames,
) -> List[str]:
    tool_surface_profile = tool_surface_profile_fn(config)
    names = provider_tool_registry_helpers.provider_tool_names(
        builtin_tool_order=model_facing_builtin_tool_order,
        tool_surface_profile=tool_surface_profile,
        plugin_manager_factory=plugin_manager_factory,
        function_name_from_spec=function_name_from_spec,
    )
    visible_names = [name for name in names if not is_model_hidden_builtin_fn(name, config=config)]
    for plugin_name in provider_tool_registry_helpers.plugin_visible_provider_tool_names(
        tool_surface_profile=tool_surface_profile,
        plugin_manager_factory=plugin_manager_factory,
        function_name_from_spec=function_name_from_spec,
    ):
        if plugin_name not in visible_names:
            visible_names.append(plugin_name)
    return project_model_facing_provider_names_fn(
        visible_names,
        config=config,
        host_platform=host_platform,
    )


def _legacy_codex_responses_minimal_tool_names(config: ProviderConfig) -> List[str]:
    names: List[str] = []
    for item in reference_parity_responses_minimal_tool_specs(config):
        name = str(item.get("name") or "").strip()
        if name:
            names.append(name)
    return names


def responses_minimal_provider_tool_names(
    config: ProviderConfig,
    host_platform: HostPlatform,
    *,
    responses_minimal_tool_order: Tuple[str, ...],
    tool_surface_profile_fn: ToolSurfaceProfile,
    is_model_hidden_builtin_fn: IsModelHiddenBuiltin,
    project_model_facing_provider_names_fn: ProjectModelFacingProviderNames,
) -> List[str]:
    if tool_surface_profile_fn(config) == LEGACY_CODEX_PROFILE:
        return _legacy_codex_responses_minimal_tool_names(config)
    visible_names = [
        name for name in responses_minimal_tool_order if not is_model_hidden_builtin_fn(name, config=config)
    ]
    return project_model_facing_provider_names_fn(
        visible_names,
        config=config,
        host_platform=host_platform,
    )


def command_text_patterns(
    config: ProviderConfig,
    host_platform: HostPlatform,
    *,
    plugin_manager_factory: PluginManagerFactory | None = None,
    provider_tool_names_fn: Callable[..., List[str]],
    model_hidden_compat_aliases_ordered: Tuple[str, ...],
) -> Tuple[Pattern[str], Pattern[str]]:
    names = provider_tool_names_fn(
        config,
        host_platform,
        plugin_manager_factory=plugin_manager_factory,
    )
    for alias in model_hidden_compat_aliases_ordered:
        if alias and alias not in names:
            names.append(alias)
    escaped = "|".join(sorted((re.escape(name) for name in names if name), key=len, reverse=True))
    if not escaped:
        escaped = "shell"
    return (
        re.compile(rf"(?m)(/(?:{escaped})\b[^\r\n`]*)"),
        re.compile(rf"\s+/(?:{escaped})\b"),
    )


def merged_provider_tool_specs(
    config: ProviderConfig,
    host_platform: HostPlatform,
    *,
    plugin_manager_factory: PluginManagerFactory | None = None,
    tool_surface_profile_fn: ToolSurfaceProfile,
    builtin_provider_tool_specs_fn: BuiltinProviderToolSpecs,
    filter_model_facing_provider_specs_fn: FilterModelFacingProviderSpecs,
    function_name_from_spec: FunctionNameFromSpec,
    project_model_facing_provider_specs_fn: ProjectModelFacingProviderSpecs,
) -> List[Dict[str, Any]]:
    tool_surface_profile = tool_surface_profile_fn(config)
    builtin_specs = builtin_provider_tool_specs_fn(
        config=config,
        host_platform=host_platform,
    )
    merged = provider_tool_registry_helpers.merged_provider_tool_specs(
        builtin_provider_specs=filter_model_facing_provider_specs_fn(
            builtin_specs,
            config=config,
        ),
        tool_surface_profile=tool_surface_profile,
        plugin_manager_factory=plugin_manager_factory,
        function_name_from_spec=function_name_from_spec,
    )
    return project_model_facing_provider_specs_fn(
        merged,
        config=config,
        host_platform=host_platform,
    )

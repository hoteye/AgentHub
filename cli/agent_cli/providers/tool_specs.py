from __future__ import annotations

from functools import WRAPPER_ASSIGNMENTS, update_wrapper
from typing import Any, Callable, Dict, List, Optional, ParamSpec, Pattern, Tuple, TypeVar

from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.providers import builtin_provider_tool_specs as builtin_provider_tool_specs_helpers
from cli.agent_cli.providers import responses_tool_specs as responses_tool_specs_helpers
from cli.agent_cli.providers import tool_family_mapping_runtime as tool_family_mapping_runtime_helpers
from cli.agent_cli.providers import tool_family_registry
from cli.agent_cli.providers import tool_specs_normalization_runtime as tool_specs_normalization_runtime_helpers
from cli.agent_cli.providers import tool_specs_projection_runtime as tool_specs_projection_runtime_helpers
from cli.agent_cli.providers import tool_specs_pure_runtime as tool_specs_pure_runtime_helpers
from cli.agent_cli.providers import tool_specs_surface_runtime as tool_specs_surface_runtime_helpers
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.interaction_profile_compat_runtime import (
    resolved_tool_surface_profile_for_config,
)

P = ParamSpec("P")
R = TypeVar("R")
_ASSIGNED_EXPORT_ATTRIBUTES = tuple(
    attribute for attribute in WRAPPER_ASSIGNMENTS if attribute != "__module__"
)


def _export(fn: Callable[P, R]) -> Callable[P, R]:
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return fn(*args, **kwargs)

    return update_wrapper(wrapper, fn, assigned=_ASSIGNED_EXPORT_ATTRIBUTES)


PluginManagerFactory = Callable[[], Optional[PluginManager]]
_MODEL_FACING_BUILTIN_TOOL_ORDER = tuple(
    getattr(
        tool_family_mapping_runtime_helpers,
        "MODEL_FACING_BUILTIN_TOOL_ORDER",
        tool_family_registry.BUILTIN_TOOL_ORDER,
    )
)
_MODEL_HIDDEN_COMPAT_ALIASES_ORDERED = tool_specs_surface_runtime_helpers.model_hidden_compat_aliases_ordered()
_RESPONSES_MINIMAL_TOOL_ORDER = tool_family_registry.RESPONSES_MINIMAL_TOOL_ORDER
_BROWSER_PROVIDER_ACTIONS = tool_family_registry.BROWSER_PROVIDER_ACTIONS

_normalize_base_capability_spec = _export(tool_specs_normalization_runtime_helpers.normalize_base_capability_spec)
_normalized_actions = _export(tool_specs_normalization_runtime_helpers.normalized_actions)
_build_canonical_registry_entry = _export(tool_specs_normalization_runtime_helpers.build_canonical_registry_entry)
_canonical_registry_entry = _export(tool_specs_normalization_runtime_helpers.canonical_registry_entry)
_clone_canonical_registry_entry = _export(tool_specs_normalization_runtime_helpers.clone_canonical_registry_entry)
canonical_tool_registry = _export(tool_family_registry.canonical_tool_registry)
canonical_tool_metadata = _export(tool_family_registry.canonical_tool_metadata)
base_capability_specs = _export(tool_family_registry.base_capability_specs)
builtin_tool_metadata = _export(tool_family_registry.builtin_tool_metadata)
command_usage_text = _export(tool_family_registry.command_usage_text)
command_action_names = _export(tool_family_registry.command_action_names)
provider_action_names = _export(tool_family_registry.provider_action_names)
merged_capability_specs = _export(tool_family_registry.merged_capability_specs)
_is_model_hidden_compat_alias = _export(tool_specs_surface_runtime_helpers.is_model_hidden_compat_alias)
_expert_review_snapshot_mappings = _export(tool_specs_surface_runtime_helpers.expert_review_snapshot_mappings)
_claude_code_powershell_visible = _export(tool_specs_projection_runtime_helpers.claude_code_powershell_visible)
_append_unique_names = _export(tool_specs_projection_runtime_helpers.append_unique_names)
_rename_spec = _export(tool_specs_projection_runtime_helpers.rename_spec)
_function_name_from_spec = _export(responses_tool_specs_helpers.function_name_from_spec)
_function_fields_from_spec = _export(responses_tool_specs_helpers.function_fields_from_spec)
_normalize_capability_spec = _export(tool_specs_normalization_runtime_helpers.normalize_capability_spec)
_provider_description = _export(tool_specs_normalization_runtime_helpers.provider_description)
_function_tool = _export(builtin_provider_tool_specs_helpers.function_tool)


def supports_glm_native_web_search(config: ProviderConfig) -> bool:
    return tool_specs_pure_runtime_helpers.supports_glm_native_web_search(
        config,
        resolve_native_web_search_capability_fn=resolve_native_web_search_capability,
    )


def supports_openai_responses_native_web_search(config: ProviderConfig) -> bool:
    return tool_specs_pure_runtime_helpers.supports_openai_responses_native_web_search(
        config,
        resolve_native_web_search_capability_fn=resolve_native_web_search_capability,
    )


def _supports_native_web_search_mixed_tools(config: ProviderConfig) -> bool:
    return tool_specs_pure_runtime_helpers.supports_native_web_search_mixed_tools(
        config,
        resolve_native_web_search_capability_fn=resolve_native_web_search_capability,
    )


def supports_openai_responses_native_web_search_mixed_tools(config: ProviderConfig) -> bool:
    return tool_specs_pure_runtime_helpers.supports_openai_responses_native_web_search_mixed_tools(
        config,
        resolve_native_web_search_capability_fn=resolve_native_web_search_capability,
    )


def supports_anthropic_native_web_search(config: ProviderConfig) -> bool:
    return tool_specs_pure_runtime_helpers.supports_anthropic_native_web_search(
        config,
        resolve_native_web_search_capability_fn=resolve_native_web_search_capability,
    )


def supports_anthropic_native_web_search_mixed_tools(config: ProviderConfig) -> bool:
    return tool_specs_pure_runtime_helpers.supports_anthropic_native_web_search_mixed_tools(
        config,
        resolve_native_web_search_capability_fn=resolve_native_web_search_capability,
    )


def resolve_native_web_search_capability(config: ProviderConfig) -> Any:
    from cli.agent_cli.tools_core.tool_capability_resolver import (
        resolve_native_web_search_capability as resolve_native_web_search_capability_impl,
    )

    return resolve_native_web_search_capability_impl(config)


def _web_search_hidden_from_model_surface(config: ProviderConfig) -> bool:
    return tool_specs_surface_runtime_helpers.web_search_hidden_from_model_surface(
        config,
        resolve_native_web_search_capability_fn=resolve_native_web_search_capability,
    )


def _expert_review_visible_in_model_surface(config: ProviderConfig) -> bool:
    return tool_specs_surface_runtime_helpers.expert_review_visible_in_model_surface(
        config,
        resolved_tool_surface_profile_for_config_fn=resolved_tool_surface_profile_for_config,
    )


def _is_model_hidden_builtin(name: str, *, config: ProviderConfig) -> bool:
    return tool_specs_surface_runtime_helpers.is_model_hidden_builtin(
        name,
        config=config,
        resolve_native_web_search_capability_fn=resolve_native_web_search_capability,
        resolved_tool_surface_profile_for_config_fn=resolved_tool_surface_profile_for_config,
    )


def _filter_model_facing_provider_specs(
    specs: List[Dict[str, Any]],
    *,
    config: ProviderConfig,
) -> List[Dict[str, Any]]:
    return tool_specs_surface_runtime_helpers.filter_model_facing_provider_specs(
        specs,
        config=config,
        function_name_from_spec=_function_name_from_spec,
        resolve_native_web_search_capability_fn=resolve_native_web_search_capability,
        resolved_tool_surface_profile_for_config_fn=resolved_tool_surface_profile_for_config,
    )


def _tool_surface_profile(config: ProviderConfig) -> str:
    return tool_specs_surface_runtime_helpers.tool_surface_profile(
        config,
        resolved_tool_surface_profile_for_config_fn=resolved_tool_surface_profile_for_config,
    )


def _project_command_tool_names(
    name: str,
    *,
    config: ProviderConfig,
    host_platform: HostPlatform,
) -> Tuple[str, ...]:
    return tool_specs_projection_runtime_helpers.project_command_tool_names(
        name,
        config=config,
        host_platform=host_platform,
        tool_surface_profile_fn=_tool_surface_profile,
    )


def _project_model_facing_provider_names(
    names: List[str],
    *,
    config: ProviderConfig,
    host_platform: HostPlatform,
) -> List[str]:
    return tool_specs_projection_runtime_helpers.project_model_facing_provider_names(
        names,
        config=config,
        host_platform=host_platform,
        tool_surface_profile_fn=_tool_surface_profile,
    )


def _claude_code_command_specs(host_platform: HostPlatform) -> List[Dict[str, Any]]:
    return tool_specs_projection_runtime_helpers.claude_code_command_specs(
        host_platform,
        function_tool=_function_tool,
        provider_description=_provider_description,
    )


def _claude_code_write_spec() -> Dict[str, Any]:
    return tool_specs_projection_runtime_helpers.claude_code_write_spec(
        function_tool=_function_tool,
        provider_description=_provider_description,
    )


def _claude_code_edit_spec() -> Dict[str, Any]:
    return tool_specs_projection_runtime_helpers.claude_code_edit_spec(
        function_tool=_function_tool,
        provider_description=_provider_description,
    )


def _claude_code_glob_spec() -> Dict[str, Any]:
    return tool_specs_projection_runtime_helpers.claude_code_glob_spec(
        function_tool=_function_tool,
    )


def _claude_code_grep_spec() -> Dict[str, Any]:
    return tool_specs_projection_runtime_helpers.claude_code_grep_spec(
        function_tool=_function_tool,
    )


def _claude_code_read_spec() -> Dict[str, Any]:
    return tool_specs_projection_runtime_helpers.claude_code_read_spec(
        function_tool=_function_tool,
    )


def _claude_code_web_search_spec() -> Dict[str, Any]:
    return tool_specs_projection_runtime_helpers.claude_code_web_search_spec(
        function_tool=_function_tool,
    )


def _claude_code_web_fetch_spec() -> Dict[str, Any]:
    return tool_specs_projection_runtime_helpers.claude_code_web_fetch_spec(
        function_tool=_function_tool,
    )


def _project_model_facing_provider_specs(
    specs: List[Dict[str, Any]],
    *,
    config: ProviderConfig,
    host_platform: HostPlatform,
) -> List[Dict[str, Any]]:
    return tool_specs_projection_runtime_helpers.project_model_facing_provider_specs(
        specs,
        config=config,
        host_platform=host_platform,
        function_name_from_spec=_function_name_from_spec,
        function_tool=_function_tool,
        provider_description=_provider_description,
        tool_surface_profile_fn=_tool_surface_profile,
    )


def provider_tool_names(
    config: ProviderConfig,
    host_platform: HostPlatform,
    *,
    plugin_manager_factory: PluginManagerFactory | None = None,
) -> List[str]:
    return tool_specs_pure_runtime_helpers.provider_tool_names(
        config,
        host_platform,
        plugin_manager_factory=plugin_manager_factory,
        model_facing_builtin_tool_order=_MODEL_FACING_BUILTIN_TOOL_ORDER,
        tool_surface_profile_fn=_tool_surface_profile,
        function_name_from_spec=_function_name_from_spec,
        is_model_hidden_builtin_fn=_is_model_hidden_builtin,
        project_model_facing_provider_names_fn=_project_model_facing_provider_names,
    )


def responses_minimal_provider_tool_names(
    config: ProviderConfig,
    host_platform: HostPlatform,
    *,
    plugin_manager_factory: PluginManagerFactory | None = None,
) -> List[str]:
    del plugin_manager_factory
    return tool_specs_pure_runtime_helpers.responses_minimal_provider_tool_names(
        config,
        host_platform,
        responses_minimal_tool_order=_RESPONSES_MINIMAL_TOOL_ORDER,
        tool_surface_profile_fn=_tool_surface_profile,
        is_model_hidden_builtin_fn=_is_model_hidden_builtin,
        project_model_facing_provider_names_fn=_project_model_facing_provider_names,
    )


def command_text_patterns(
    config: ProviderConfig,
    host_platform: HostPlatform,
    *,
    plugin_manager_factory: PluginManagerFactory | None = None,
) -> Tuple[Pattern[str], Pattern[str]]:
    return tool_specs_pure_runtime_helpers.command_text_patterns(
        config,
        host_platform,
        plugin_manager_factory=plugin_manager_factory,
        provider_tool_names_fn=provider_tool_names,
        model_hidden_compat_aliases_ordered=_MODEL_HIDDEN_COMPAT_ALIASES_ORDERED,
    )


def merged_provider_tool_specs(
    config: ProviderConfig,
    host_platform: HostPlatform,
    *,
    plugin_manager_factory: PluginManagerFactory | None = None,
) -> List[Dict[str, Any]]:
    return tool_specs_pure_runtime_helpers.merged_provider_tool_specs(
        config,
        host_platform,
        plugin_manager_factory=plugin_manager_factory,
        tool_surface_profile_fn=_tool_surface_profile,
        builtin_provider_tool_specs_fn=_builtin_provider_tool_specs,
        filter_model_facing_provider_specs_fn=_filter_model_facing_provider_specs,
        function_name_from_spec=_function_name_from_spec,
        project_model_facing_provider_specs_fn=_project_model_facing_provider_specs,
    )


def responses_provider_tool_specs(
    config: ProviderConfig,
    host_platform: HostPlatform,
    *,
    plugin_manager_factory: PluginManagerFactory | None = None,
) -> List[Dict[str, Any]]:
    return responses_tool_specs_helpers.responses_provider_tool_specs(
        config,
        host_platform,
        plugin_manager_factory=plugin_manager_factory,
        merged_provider_tool_specs_fn=merged_provider_tool_specs,
    )


def responses_minimal_provider_tool_specs(
    config: ProviderConfig,
    host_platform: HostPlatform,
    *,
    plugin_manager_factory: PluginManagerFactory | None = None,
) -> List[Dict[str, Any]]:
    return responses_tool_specs_helpers.responses_minimal_provider_tool_specs(
        config,
        host_platform,
        plugin_manager_factory=plugin_manager_factory,
        responses_provider_tool_specs_fn=responses_provider_tool_specs,
        responses_minimal_tool_order=_RESPONSES_MINIMAL_TOOL_ORDER,
    )


def _builtin_provider_tool_specs(
    config: ProviderConfig,
    host_platform: HostPlatform,
) -> List[Dict[str, Any]]:
    return builtin_provider_tool_specs_helpers.builtin_provider_tool_specs(
        config=config,
        host_platform=host_platform,
        provider_description=_provider_description,
        provider_action_names=provider_action_names,
        resolve_native_web_search_capability_fn=resolve_native_web_search_capability,
        browser_provider_actions=_BROWSER_PROVIDER_ACTIONS,
    )

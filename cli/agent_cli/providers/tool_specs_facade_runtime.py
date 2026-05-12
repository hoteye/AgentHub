from __future__ import annotations

from cli.agent_cli.providers import tool_specs as _tool_specs


PluginManagerFactory = _tool_specs.PluginManagerFactory


def model_facing_builtin_tool_order() -> tuple[str, ...]:
    return _tool_specs._MODEL_FACING_BUILTIN_TOOL_ORDER


def model_hidden_compat_aliases_ordered() -> tuple[str, ...]:
    return _tool_specs._MODEL_HIDDEN_COMPAT_ALIASES_ORDERED


def responses_minimal_tool_order() -> tuple[str, ...]:
    return _tool_specs._RESPONSES_MINIMAL_TOOL_ORDER


def browser_provider_actions() -> tuple[str, ...]:
    return _tool_specs._BROWSER_PROVIDER_ACTIONS


_REEXPORT_ATTRS = {
    "normalize_base_capability_spec": "_normalize_base_capability_spec",
    "normalized_actions": "_normalized_actions",
    "build_canonical_registry_entry": "_build_canonical_registry_entry",
    "canonical_registry_entry": "_canonical_registry_entry",
    "clone_canonical_registry_entry": "_clone_canonical_registry_entry",
    "canonical_tool_registry": "canonical_tool_registry",
    "canonical_tool_metadata": "canonical_tool_metadata",
    "supports_glm_native_web_search": "supports_glm_native_web_search",
    "supports_openai_responses_native_web_search": "supports_openai_responses_native_web_search",
    "supports_native_web_search_mixed_tools": "_supports_native_web_search_mixed_tools",
    "supports_openai_responses_native_web_search_mixed_tools": "supports_openai_responses_native_web_search_mixed_tools",
    "supports_anthropic_native_web_search": "supports_anthropic_native_web_search",
    "supports_anthropic_native_web_search_mixed_tools": "supports_anthropic_native_web_search_mixed_tools",
    "base_capability_specs": "base_capability_specs",
    "builtin_tool_metadata": "builtin_tool_metadata",
    "command_usage_text": "command_usage_text",
    "command_action_names": "command_action_names",
    "provider_action_names": "provider_action_names",
    "merged_capability_specs": "merged_capability_specs",
    "is_model_hidden_compat_alias": "_is_model_hidden_compat_alias",
    "web_search_hidden_from_model_surface": "_web_search_hidden_from_model_surface",
    "expert_review_snapshot_mappings": "_expert_review_snapshot_mappings",
    "expert_review_visible_in_model_surface": "_expert_review_visible_in_model_surface",
    "is_model_hidden_builtin": "_is_model_hidden_builtin",
    "filter_model_facing_provider_specs": "_filter_model_facing_provider_specs",
    "tool_surface_profile": "_tool_surface_profile",
    "claude_code_powershell_visible": "_claude_code_powershell_visible",
    "append_unique_names": "_append_unique_names",
    "project_command_tool_names": "_project_command_tool_names",
    "project_model_facing_provider_names": "_project_model_facing_provider_names",
    "rename_spec": "_rename_spec",
    "claude_code_command_specs": "_claude_code_command_specs",
    "claude_code_write_spec": "_claude_code_write_spec",
    "claude_code_edit_spec": "_claude_code_edit_spec",
    "claude_code_glob_spec": "_claude_code_glob_spec",
    "claude_code_grep_spec": "_claude_code_grep_spec",
    "claude_code_read_spec": "_claude_code_read_spec",
    "claude_code_web_search_spec": "_claude_code_web_search_spec",
    "claude_code_web_fetch_spec": "_claude_code_web_fetch_spec",
    "project_model_facing_provider_specs": "_project_model_facing_provider_specs",
    "provider_tool_names": "provider_tool_names",
    "responses_minimal_provider_tool_names": "responses_minimal_provider_tool_names",
    "command_text_patterns": "command_text_patterns",
    "merged_provider_tool_specs": "merged_provider_tool_specs",
    "responses_provider_tool_specs": "responses_provider_tool_specs",
    "responses_minimal_provider_tool_specs": "responses_minimal_provider_tool_specs",
    "function_name_from_spec": "_function_name_from_spec",
    "function_fields_from_spec": "_function_fields_from_spec",
    "normalize_capability_spec": "_normalize_capability_spec",
    "provider_description": "_provider_description",
    "function_tool": "_function_tool",
    "builtin_provider_tool_specs": "_builtin_provider_tool_specs",
}

globals().update({name: getattr(_tool_specs, attr) for name, attr in _REEXPORT_ATTRS.items()})

__all__ = [
    "PluginManagerFactory",
    "model_facing_builtin_tool_order",
    "model_hidden_compat_aliases_ordered",
    "responses_minimal_tool_order",
    "browser_provider_actions",
    *tuple(_REEXPORT_ATTRS.keys()),
]

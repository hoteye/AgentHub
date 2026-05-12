from __future__ import annotations

from typing import Any, Callable, Dict, List

from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.providers import builtin_provider_tool_specs_catalog_schema_runtime as builtin_provider_tool_specs_catalog_schema_runtime_helpers
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.tool_specs_projection_spec_helpers_runtime import (
    claude_code_command_specs,
    claude_code_edit_spec,
    claude_code_glob_spec,
    claude_code_grep_spec,
    claude_code_read_spec,
    claude_code_web_fetch_spec,
    claude_code_web_search_spec,
    claude_code_write_spec,
)

FunctionNameFromSpec = Callable[[Any], str]
FunctionTool = Callable[..., Dict[str, Any]]
ProviderDescription = Callable[[str], str]
ResolveToolSurfaceProfile = Callable[[ProviderConfig], str]

_CLAUDE_CODE_PROFILE = "claude_code"


def project_model_facing_provider_specs(
    specs: List[Dict[str, Any]],
    *,
    config: ProviderConfig,
    host_platform: HostPlatform,
    function_name_from_spec: FunctionNameFromSpec,
    function_tool: FunctionTool,
    provider_description: ProviderDescription,
    tool_surface_profile_fn: ResolveToolSurfaceProfile,
) -> List[Dict[str, Any]]:
    if tool_surface_profile_fn(config) != _CLAUDE_CODE_PROFILE:
        return [dict(item) for item in specs if isinstance(item, dict)]
    projected: List[Dict[str, Any]] = []
    for item in list(specs or []):
        if not isinstance(item, dict):
            continue
        function_name = function_name_from_spec(item)
        if function_name == "exec_command":
            projected.extend(
                claude_code_command_specs(
                    host_platform,
                    function_tool=function_tool,
                    provider_description=provider_description,
                )
            )
            continue
        if function_name == "apply_patch":
            projected.append(
                claude_code_write_spec(
                    function_tool=function_tool,
                    provider_description=provider_description,
                )
            )
            projected.append(
                claude_code_edit_spec(
                    function_tool=function_tool,
                    provider_description=provider_description,
                )
            )
            continue
        if function_name == "request_user_input":
            projected.append(
                builtin_provider_tool_specs_catalog_schema_runtime_helpers.ask_user_question_spec(
                    function_tool=function_tool,
                    provider_description=provider_description,
                )
            )
            continue
        if function_name == "grep_files":
            projected.append(claude_code_grep_spec(function_tool=function_tool))
            continue
        if function_name == "read_file":
            projected.append(claude_code_read_spec(function_tool=function_tool))
            continue
        if function_name == "list_dir":
            projected.append(claude_code_glob_spec(function_tool=function_tool))
            continue
        if function_name == "web_search":
            projected.append(claude_code_web_search_spec(function_tool=function_tool))
            continue
        if function_name == "web_fetch":
            projected.append(claude_code_web_fetch_spec(function_tool=function_tool))
            continue
        projected.append(dict(item))
    return projected

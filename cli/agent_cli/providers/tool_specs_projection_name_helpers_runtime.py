from __future__ import annotations

from typing import Any, Callable, Dict, List, Tuple

from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.providers import builtin_provider_delegation_specs as builtin_provider_delegation_specs_helpers
from cli.agent_cli.providers.config_catalog import ProviderConfig

ResolveToolSurfaceProfile = Callable[[ProviderConfig], str]

_CLAUDE_CODE_PROFILE = "claude_code"
_BASH_TOOL_NAME = "Bash"
_POWERSHELL_TOOL_NAME = "PowerShell"
_ASK_USER_QUESTION_TOOL_NAME = "AskUserQuestion"
_GLOB_TOOL_NAME = "Glob"
_GREP_TOOL_NAME = "Grep"
_READ_TOOL_NAME = "Read"
_WEB_SEARCH_TOOL_NAME = "WebSearch"
_WEB_FETCH_TOOL_NAME = "WebFetch"


def claude_code_powershell_visible(host_platform: HostPlatform) -> bool:
    return str(host_platform.family or "").strip().lower() == "windows"


def append_unique_names(values: List[str], additions: Tuple[str, ...]) -> None:
    seen = set(values)
    for item in additions:
        normalized = str(item or "").strip()
        if not normalized or normalized in seen:
            continue
        values.append(normalized)
        seen.add(normalized)


def project_command_tool_names(
    name: str,
    *,
    config: ProviderConfig,
    host_platform: HostPlatform,
    tool_surface_profile_fn: ResolveToolSurfaceProfile,
) -> Tuple[str, ...]:
    if tool_surface_profile_fn(config) != _CLAUDE_CODE_PROFILE:
        return (name,)
    if name == "exec_command":
        projected = [_BASH_TOOL_NAME]
        if claude_code_powershell_visible(host_platform):
            projected.append(_POWERSHELL_TOOL_NAME)
        return tuple(projected)
    if name == "request_user_input":
        return (_ASK_USER_QUESTION_TOOL_NAME,)
    if name == "write_stdin":
        return ("write_stdin",)
    if name == "apply_patch":
        return ("Write", "Edit")
    if name == "grep_files":
        return (_GREP_TOOL_NAME,)
    if name == "read_file":
        return (_READ_TOOL_NAME,)
    if name == "list_dir":
        return (_GLOB_TOOL_NAME,)
    if name == "web_search":
        return (_WEB_SEARCH_TOOL_NAME,)
    if name == "web_fetch":
        return (_WEB_FETCH_TOOL_NAME,)
    return (name,)


def project_model_facing_provider_names(
    names: List[str],
    *,
    config: ProviderConfig,
    host_platform: HostPlatform,
    tool_surface_profile_fn: ResolveToolSurfaceProfile,
) -> List[str]:
    projected: List[str] = []
    tool_surface_profile = tool_surface_profile_fn(config)
    for name in names:
        visible_name = builtin_provider_delegation_specs_helpers.visible_delegation_tool_name(
            name,
            tool_surface_profile=tool_surface_profile,
        )
        if not visible_name:
            continue
        append_unique_names(
            projected,
            project_command_tool_names(
                visible_name,
                config=config,
                host_platform=host_platform,
                tool_surface_profile_fn=tool_surface_profile_fn,
            ),
        )
    return projected


def rename_spec(spec: Dict[str, Any], new_name: str) -> Dict[str, Any]:
    result = dict(spec)
    function_block = result.get("function")
    if isinstance(function_block, dict):
        result["function"] = dict(function_block)
        result["function"]["name"] = new_name
    elif str(result.get("type") or "").strip() == "function":
        result["name"] = new_name
    return result

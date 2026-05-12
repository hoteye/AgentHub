from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli.providers import builtin_provider_delegation_specs_pure_runtime as pure_runtime
from cli.agent_cli.providers.builtin_provider_delegation_surface_helpers import (
    delegation_tool_projection_override_kind,
    visible_delegation_tool_name_pairs,
    visible_delegation_tool_order,
)

FunctionTool = pure_runtime.FunctionTool
ProviderDescription = pure_runtime.ProviderDescription


def _projected_delegation_spec(
    canonical_name: str,
    canonical_specs: Dict[str, Dict[str, Any]],
    *,
    function_tool: FunctionTool,
    provider_description: ProviderDescription,
    tool_surface_profile: str = "",
) -> Dict[str, Any]:
    override_kind = delegation_tool_projection_override_kind(
        canonical_name,
        tool_surface_profile=tool_surface_profile,
    )
    if override_kind == "codex_wait":
        return pure_runtime.codex_wait_spec(
            function_tool=function_tool,
            provider_description=provider_description,
        )
    if override_kind == "claude_agent":
        return pure_runtime.claude_agent_spec(
            function_tool=function_tool,
            provider_description=provider_description,
        )
    if override_kind == "claude_send_message":
        return pure_runtime.claude_send_message_spec(
            function_tool=function_tool,
            provider_description=provider_description,
        )
    return dict(canonical_specs[canonical_name])


def delegation_tool_specs_by_name(
    *,
    function_tool: FunctionTool,
    provider_description: ProviderDescription,
    tool_surface_profile: str = "",
) -> Dict[str, Dict[str, Any]]:
    canonical_specs = pure_runtime.canonical_delegation_specs_by_name(
        function_tool=function_tool,
        provider_description=provider_description,
    )
    if not str(tool_surface_profile or "").strip():
        return canonical_specs

    projected: Dict[str, Dict[str, Any]] = {}
    for canonical_name, visible_name in visible_delegation_tool_name_pairs(
        tool_surface_profile=tool_surface_profile,
    ):
        projected[visible_name] = _projected_delegation_spec(
            canonical_name,
            canonical_specs,
            function_tool=function_tool,
            provider_description=provider_description,
            tool_surface_profile=tool_surface_profile,
        )
    return projected


def delegation_tool_specs(
    *,
    function_tool: FunctionTool,
    provider_description: ProviderDescription,
    tool_surface_profile: str = "",
) -> List[Dict[str, Any]]:
    by_name = delegation_tool_specs_by_name(
        function_tool=function_tool,
        provider_description=provider_description,
        tool_surface_profile=tool_surface_profile,
    )
    return [
        dict(by_name[name])
        for name in visible_delegation_tool_order(tool_surface_profile=tool_surface_profile)
        if isinstance(by_name.get(name), dict)
    ]

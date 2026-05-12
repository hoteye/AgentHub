from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.providers import builtin_provider_delegation_specs as delegation_specs_helpers
from cli.agent_cli.providers import (
    builtin_provider_tool_specs_runtime as builtin_provider_tool_specs_runtime,
)
from cli.agent_cli.providers.config_catalog import ProviderConfig
from cli.agent_cli.providers.interaction_profile_compat_runtime import (
    resolved_tool_surface_profile_for_config,
)

_BUILTIN_PROVIDER_SPEC_ORDER: tuple[str, ...] = (
    "exec_command",
    "write_stdin",
    "spawn_agent",
    "request_orchestration",
    "spawn_child_tab",
    "send_child_tab",
    "wait_child_tasks",
    "send_input",
    "resume_agent",
    "wait_agent",
    "web_search",
    "agent_workflow",
    "recover_agent",
    "close_agent",
    "update_plan",
    "request_user_input",
    "shell",
    "apply_patch",
    "grep_files",
    "read_file",
    "list_dir",
    "file_search",
    "file_read",
    "file_list",
    "office_skills",
    "office_run",
    "view_image",
    "expert_review",
    "web_fetch",
    "browser",
    "open",
    "click",
    "find",
    "policy_doc_import",
    "policy_doc_list",
    "policy_doc_search",
    "policy_doc_read",
)


def function_tool(
    *,
    name: str,
    description: str,
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
) -> dict[str, Any]:
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": dict(properties or {}),
        "additionalProperties": False,
    }
    if required:
        parameters["required"] = list(required)
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }


def builtin_provider_tool_specs(
    config: ProviderConfig,
    host_platform: HostPlatform,
    *,
    provider_description: Callable[[str], str],
    provider_action_names: Callable[[str], tuple[str, ...]],
    resolve_native_web_search_capability_fn: Callable[[ProviderConfig], Any],
    browser_provider_actions: tuple[str, ...],
) -> list[dict[str, Any]]:
    tool_surface_profile = resolved_tool_surface_profile_for_config(config) or "generic_chat"
    base_specs_by_name = builtin_provider_tool_specs_runtime.base_function_specs_by_name(
        function_tool=function_tool,
        provider_description=provider_description,
        provider_action_names=provider_action_names,
        browser_provider_actions=browser_provider_actions,
        host_platform=host_platform,
    )
    delegation_by_name = delegation_specs_helpers.delegation_tool_specs_by_name(
        function_tool=function_tool,
        provider_description=provider_description,
        tool_surface_profile=tool_surface_profile,
    )
    all_specs_by_name: dict[str, dict[str, Any]] = {}
    all_specs_by_name.update(base_specs_by_name)
    all_specs_by_name.update(delegation_by_name)
    all_specs_by_name["web_search"] = builtin_provider_tool_specs_runtime.web_search_provider_spec(
        config=config,
        function_tool=function_tool,
        provider_description=provider_description,
        resolve_native_web_search_capability_fn=resolve_native_web_search_capability_fn,
    )
    ordered_names: list[str] = []
    for name in _BUILTIN_PROVIDER_SPEC_ORDER:
        if name not in set(delegation_specs_helpers.delegation_tool_spec_order()):
            ordered_names.append(name)
            continue
        visible_name = delegation_specs_helpers.visible_delegation_tool_name(
            name,
            tool_surface_profile=tool_surface_profile,
        )
        if visible_name:
            ordered_names.append(visible_name)
    return [
        dict(all_specs_by_name[name])
        for name in ordered_names
        if isinstance(all_specs_by_name.get(name), dict)
    ]

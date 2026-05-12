from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.providers.config_catalog import ProviderConfig, optional_bool
from cli.agent_cli.providers.interaction_profile_compat_runtime import (
    resolved_tool_surface_profile_for_config,
)
from cli.agent_cli.providers.reference_parity_tool_specs import reference_parity_responses_minimal_tool_specs


_CODEX_OPENAI_PROFILE = "codex_openai"
_MINIMAL_ORDER_EQUIVALENTS = {
    "Bash": "exec_command",
    "PowerShell": "exec_command",
    "AskUserQuestion": "request_user_input",
    "Glob": "list_dir",
    "Grep": "grep_files",
    "Read": "read_file",
    "WebSearch": "web_search",
    "WebFetch": "web_fetch",
}


def function_fields_from_spec(spec: Any) -> Tuple[str, str, Optional[Dict[str, Any]]]:
    if not isinstance(spec, dict):
        return "", "", None
    function_block = spec.get("function")
    if isinstance(function_block, dict):
        return (
            str(function_block.get("name") or "").strip(),
            str(function_block.get("description") or "").strip(),
            function_block.get("parameters") if isinstance(function_block.get("parameters"), dict) else None,
        )
    if str(spec.get("type") or "").strip() == "function":
        return (
            str(spec.get("name") or "").strip(),
            str(spec.get("description") or "").strip(),
            spec.get("parameters") if isinstance(spec.get("parameters"), dict) else None,
        )
    return "", "", None


def function_name_from_spec(spec: Any) -> str:
    function_name, _, _ = function_fields_from_spec(spec)
    return function_name


def _responses_function_tool_spec_from_provider_spec(item: Dict[str, Any]) -> Dict[str, Any] | None:
    if str(item.get("type") or "").strip() != "function":
        return dict(item)
    function_name, description, parameters = function_fields_from_spec(item)
    if not function_name:
        return None
    normalized_parameters = (
        parameters
        if isinstance(parameters, dict)
        else {"type": "object", "properties": {}, "additionalProperties": False}
    )
    spec: Dict[str, Any] = {
        "type": "function",
        "name": function_name,
        "description": description,
        "parameters": normalized_parameters,
    }
    if "strict" in item:
        spec["strict"] = optional_bool(item.get("strict"), False)
    return spec


def responses_provider_tool_specs(
    config: ProviderConfig,
    host_platform: HostPlatform,
    *,
    plugin_manager_factory: Any,
    merged_provider_tool_specs_fn: Callable[..., List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    if resolved_tool_surface_profile_for_config(config) == _CODEX_OPENAI_PROFILE:
        specs = [dict(item) for item in reference_parity_responses_minimal_tool_specs(config)]
        seen_names = {function_name_from_spec(item) for item in specs}
        for item in merged_provider_tool_specs_fn(
            config,
            host_platform,
            plugin_manager_factory=plugin_manager_factory,
        ):
            if not isinstance(item, dict):
                continue
            function_name = function_name_from_spec(item)
            if not function_name or function_name in seen_names:
                continue
            projected = _responses_function_tool_spec_from_provider_spec(item)
            if projected is None:
                continue
            specs.append(projected)
            seen_names.add(function_name)
        return specs
    specs: List[Dict[str, Any]] = []
    for item in merged_provider_tool_specs_fn(
        config,
        host_platform,
        plugin_manager_factory=plugin_manager_factory,
    ):
        if not isinstance(item, dict):
            continue
        spec = _responses_function_tool_spec_from_provider_spec(item)
        if spec is not None:
            specs.append(spec)
    return specs


def responses_minimal_provider_tool_specs(
    config: ProviderConfig,
    host_platform: HostPlatform,
    *,
    plugin_manager_factory: Any,
    responses_provider_tool_specs_fn: Callable[..., List[Dict[str, Any]]],
    responses_minimal_tool_order: Tuple[str, ...],
) -> List[Dict[str, Any]]:
    if resolved_tool_surface_profile_for_config(config) == _CODEX_OPENAI_PROFILE:
        return reference_parity_responses_minimal_tool_specs(config)
    allowed = set(responses_minimal_tool_order)
    order = {name: index for index, name in enumerate(responses_minimal_tool_order)}
    specs: List[Dict[str, Any]] = []
    for item in responses_provider_tool_specs_fn(
        config,
        host_platform,
        plugin_manager_factory=plugin_manager_factory,
    ):
        if not isinstance(item, dict):
            continue
        function_name = function_name_from_spec(item)
        comparable_name = _MINIMAL_ORDER_EQUIVALENTS.get(function_name, function_name)
        if comparable_name and comparable_name not in allowed:
            continue
        specs.append(dict(item))
    specs.sort(
        key=lambda item: order.get(
            _MINIMAL_ORDER_EQUIVALENTS.get(function_name_from_spec(item), function_name_from_spec(item)),
            len(order),
        )
    )
    return specs

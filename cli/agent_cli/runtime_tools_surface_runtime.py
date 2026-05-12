from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli.host_platform import HostPlatform, current_host_platform

_CLAUDE_CODE_PROFILE = "claude_code"


def _resolved_tool_surface_profile_for_config(config: Any) -> str:
    # Lazy import avoids a circular import on app-server startup:
    # runtime_tools_surface_runtime -> providers.__init__ -> runtime_core.tool_commands
    # -> runtime_tools_surface_runtime.
    from cli.agent_cli.providers.interaction_profile_compat_runtime import (
        resolved_tool_surface_profile_for_config,
    )

    return str(resolved_tool_surface_profile_for_config(config) or "").strip().lower()


def _function_fields_from_spec(spec: Any) -> tuple[str, str, dict[str, Any] | None]:
    from cli.agent_cli.providers.responses_tool_specs import function_fields_from_spec

    return function_fields_from_spec(spec)


def _merged_provider_tool_specs(
    config: Any,
    host_platform: HostPlatform,
    *,
    plugin_manager_factory: Any | None,
) -> list[dict[str, Any]]:
    from cli.agent_cli.providers.tool_specs import merged_provider_tool_specs

    return merged_provider_tool_specs(
        config,
        host_platform,
        plugin_manager_factory=plugin_manager_factory,
    )


def _command_execution_tool_names() -> tuple[set[str], set[str]]:
    from cli.agent_cli.providers.tool_family_mapping_runtime import (
        COMMAND_EXECUTION_PRIMARY_TOOLS,
        COMMAND_EXECUTION_TOOL_COMPAT_ALIASES,
    )

    return set(COMMAND_EXECUTION_PRIMARY_TOOLS), set(COMMAND_EXECUTION_TOOL_COMPAT_ALIASES)


def runtime_provider_config(runtime: Any) -> Any | None:
    agent = getattr(runtime, "agent", None)
    planner = getattr(agent, "_planner", None)
    return getattr(planner, "config", None)


def _payload_tool_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("tools") or []
    if not isinstance(rows, list):
        return []
    return [dict(item) for item in rows if isinstance(item, dict)]


def _description_map_from_specs(
    config: Any,
    *,
    host_platform: HostPlatform,
    plugin_manager: Any | None,
) -> dict[str, str]:
    plugin_manager_factory = (lambda: plugin_manager) if plugin_manager is not None else None
    descriptions: dict[str, str] = {}
    for item in _merged_provider_tool_specs(
        config,
        host_platform,
        plugin_manager_factory=plugin_manager_factory,
    ):
        if not isinstance(item, dict):
            continue
        name, description, _parameters = _function_fields_from_spec(item)
        if not name:
            name = str(item.get("name") or "").strip()
            description = str(item.get("description") or item.get("label") or "").strip()
        if name and name not in descriptions:
            descriptions[name] = description
    return descriptions


def _projected_tool_names(
    name: str,
    *,
    tool_surface_profile: str,
    host_platform: HostPlatform,
) -> list[str]:
    normalized = str(name or "").strip()
    if not normalized:
        return []
    primary_names, alias_names = _command_execution_tool_names()
    if normalized in primary_names or normalized in alias_names:
        if tool_surface_profile == _CLAUDE_CODE_PROFILE:
            projected = ["Bash"]
            if str(host_platform.family or "").strip().lower() == "windows":
                projected.append("PowerShell")
            return projected
        return ["exec_command"]
    if normalized == "request_user_input" and tool_surface_profile == _CLAUDE_CODE_PROFILE:
        return ["AskUserQuestion"]
    if normalized == "apply_patch" and tool_surface_profile == _CLAUDE_CODE_PROFILE:
        return ["Write", "Edit"]
    return [normalized]


def runtime_tools_capabilities(runtime: Any) -> Dict[str, Any]:
    tools = getattr(runtime, "tools", None)
    getter = getattr(tools, "capabilities", None)
    if not callable(getter):
        return {}
    payload = getter()
    if not isinstance(payload, dict):
        return {}

    config = runtime_provider_config(runtime)
    if config is None:
        return dict(payload)

    host_platform = current_host_platform()
    tool_surface_profile = _resolved_tool_surface_profile_for_config(config)
    payload_rows = _payload_tool_rows(payload)
    if not payload_rows:
        return dict(payload)

    plugin_manager = getattr(tools, "_plugin_manager", None)
    projected_descriptions = _description_map_from_specs(
        config,
        host_platform=host_platform,
        plugin_manager=plugin_manager,
    )
    original_descriptions = {
        str(item.get("name") or "").strip(): (
            str(item.get("description") or item.get("label") or "").strip()
        )
        for item in payload_rows
        if str(item.get("name") or "").strip()
    }

    projected_rows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in payload_rows:
        source_name = str(item.get("name") or "").strip()
        if not source_name:
            continue
        for projected_name in _projected_tool_names(
            source_name,
            tool_surface_profile=tool_surface_profile,
            host_platform=host_platform,
        ):
            if projected_name in seen:
                continue
            description = (
                projected_descriptions.get(projected_name)
                or original_descriptions.get(projected_name)
                or original_descriptions.get(source_name)
            )
            projected_rows.append(
                {
                    "name": projected_name,
                    "description": description or "",
                }
            )
            seen.add(projected_name)

    normalized_payload = dict(payload)
    normalized_payload["tools"] = projected_rows
    normalized_payload["count"] = len(projected_rows)
    return normalized_payload

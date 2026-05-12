from __future__ import annotations

import copy
from typing import Any

from cli.agent_cli.providers import builtin_provider_delegation_specs
from cli.agent_cli.providers.tool_family_registry import provider_description

AGENTHUB_CODEX_DYNAMIC_TOOL_NAMESPACE = "agenthub"
CODEX_DYNAMIC_TOOL_CALL_METHOD = "item/tool/call"

VISIBLE_CHILD_DYNAMIC_TOOL_NAMES: tuple[str, ...] = (
    "spawn_child_tab",
    "send_child_tab",
    "wait_child_tasks",
)

_INTERNAL_COMMAND_BY_TOOL: dict[str, str] = {
    "spawn_child_tab": "__spawn_child_tab",
    "send_child_tab": "__send_child_tab",
    "wait_child_tasks": "__wait_child_tasks",
}


def _function_tool(
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


def _delegation_spec(name: str) -> dict[str, Any]:
    specs = builtin_provider_delegation_specs.delegation_tool_specs_by_name(
        function_tool=_function_tool,
        provider_description=provider_description,
        tool_surface_profile="generic_chat",
    )
    spec = specs.get(name)
    return dict(spec) if isinstance(spec, dict) else {}


def _codex_dynamic_tool_spec(name: str) -> dict[str, Any]:
    spec = _delegation_spec(name)
    function = spec.get("function") if isinstance(spec.get("function"), dict) else {}
    tool_name = str(function.get("name") or name).strip()
    description = str(function.get("description") or "").strip()
    input_schema = function.get("parameters")
    if not isinstance(input_schema, dict):
        input_schema = {"type": "object", "properties": {}, "additionalProperties": False}
    return {
        "namespace": AGENTHUB_CODEX_DYNAMIC_TOOL_NAMESPACE,
        "name": tool_name,
        "description": description,
        "inputSchema": copy.deepcopy(input_schema),
        "deferLoading": False,
    }


def codex_visible_child_dynamic_tools() -> list[dict[str, Any]]:
    return [_codex_dynamic_tool_spec(name) for name in VISIBLE_CHILD_DYNAMIC_TOOL_NAMES]


def codex_visible_child_dynamic_tool_metadata() -> dict[str, Any]:
    return {
        "codex_dynamic_tools": codex_visible_child_dynamic_tools(),
        "codex_dynamic_tools_enabled": True,
        "codex_dynamic_tool_namespace": AGENTHUB_CODEX_DYNAMIC_TOOL_NAMESPACE,
    }


def internal_command_for_dynamic_tool(
    *,
    namespace: str,
    tool: str,
) -> str:
    normalized_namespace = str(namespace or "").strip()
    normalized_tool = str(tool or "").strip()
    if normalized_namespace != AGENTHUB_CODEX_DYNAMIC_TOOL_NAMESPACE:
        return ""
    return _INTERNAL_COMMAND_BY_TOOL.get(normalized_tool, "")

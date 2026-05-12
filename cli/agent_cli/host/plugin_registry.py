from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple


def command_specs(commands: Mapping[str, Any]) -> List[Dict[str, str]]:
    return [
        {
            "name": item.name,
            "usage": item.usage,
            "description": item.description,
            "plugin_name": item.plugin_name,
        }
        for item in commands.values()
    ]


def execute_command(
    commands: Mapping[str, Any],
    *,
    name: str,
    arg_text: str,
    runtime: Any,
) -> Optional[Tuple[str, List[Any]]]:
    item = commands.get(str(name or "").strip().lower())
    if item is None:
        return None
    return item.handler(str(arg_text or ""), runtime)


def tool_specs(tools: Mapping[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "name": item.name,
            "label": item.label or item.name,
            "description": item.description,
            "mutates_ui": item.mutates_ui,
            "requires_confirmation": item.requires_confirmation,
            "plugin_name": item.plugin_name,
        }
        for item in tools.values()
    ]


def registrations(values: Mapping[str, Any]) -> List[Any]:
    return list(values.values())


def registrations_for_plugin(values: Mapping[str, Any], *, plugin_name: str) -> List[Any]:
    requested = str(plugin_name or "").strip()
    if not requested:
        return []
    return [item for item in values.values() if item.plugin_name == requested]


def workflow_handler_registrations(workflow_handlers: Mapping[Tuple[str, str], Any]) -> List[Any]:
    return list(workflow_handlers.values())


def workflow_handler_registrations_for_plugin(
    workflow_handlers: Mapping[Tuple[str, str], Any],
    *,
    plugin_name: str,
) -> List[Any]:
    requested = str(plugin_name or "").strip()
    if not requested:
        return []
    return [item for item in workflow_handlers.values() if item.plugin_name == requested]


def get_workflow_handler(
    workflow_handlers: Mapping[Tuple[str, str], Any],
    *,
    plugin_name: str,
    workflow_name: str,
) -> Any | None:
    key = (str(plugin_name or "").strip(), str(workflow_name or "").strip())
    return workflow_handlers.get(key)


def invoke_tool(tools: Mapping[str, Any], *, name: str, args: Tuple[Any, ...], kwargs: Dict[str, Any]) -> Any:
    item = tools.get(str(name or "").strip())
    if item is None:
        raise KeyError(name)
    return item.handler(*args, **kwargs)

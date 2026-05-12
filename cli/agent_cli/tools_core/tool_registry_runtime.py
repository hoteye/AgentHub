from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from cli.agent_cli.models import (
    CommandExecutionResult,
    ToolEvent,
    generic_tool_call_item_events,
    tool_events_to_turn_events,
)


def workspace_root(registry: Any) -> Path:
    value = getattr(registry, "WORKSPACE_ROOT", None) or getattr(registry, "PROJECT_ROOT", None) or Path.cwd()
    return Path(str(value)).resolve()


def file_workspace_root(registry: Any) -> Path:
    value = getattr(registry, "PROJECT_ROOT", None) or getattr(registry, "WORKSPACE_ROOT", None) or Path.cwd()
    return Path(str(value)).resolve()


def resolve_shell_cwd(registry: Any, cwd: str | None) -> str:
    raw = str(cwd or "").strip()
    if not raw:
        return str(workspace_root(registry))
    path = Path(raw)
    if path.is_absolute():
        return str(path.resolve())
    return str((workspace_root(registry) / path).resolve())


def set_workspace_root(registry: Any, path: str | Path) -> Path:
    resolved = Path(path).resolve()
    registry.WORKSPACE_ROOT = str(resolved)
    registry.PROJECT_ROOT = str(resolved)
    if hasattr(registry, "_file_read_state"):
        registry._file_read_state = {}
    setter = getattr(registry._plugin_manager, "set_cwd", None)
    if callable(setter):
        setter(resolved)
    return resolved


def _normalized_file_read_guard_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _normalized_file_read_guard_path(path_value: Any, *, workspace: Path | None) -> str:
    text = str(path_value or "").strip()
    if not text:
        return ""
    try:
        resolved = Path(text).expanduser().resolve(strict=False)
    except OSError:
        return ""
    if workspace is not None:
        try:
            common = os.path.commonpath([str(workspace), str(resolved)])
        except ValueError:
            return ""
        if common != str(workspace):
            return ""
    return str(resolved)


def normalized_file_read_guard_state_snapshot(registry: Any) -> Dict[str, Dict[str, int]]:
    if registry is None:
        return {}
    workspace = file_workspace_root(registry) if getattr(registry, "WORKSPACE_ROOT", None) or getattr(registry, "PROJECT_ROOT", None) else None
    normalized: Dict[str, Dict[str, int]] = {}
    for raw_path, raw_state in dict(getattr(registry, "_file_read_state", {}) or {}).items():
        if not isinstance(raw_state, dict):
            continue
        path_text = _normalized_file_read_guard_path(raw_path, workspace=workspace)
        if not path_text:
            continue
        normalized[path_text] = {
            "mtime_ns": _normalized_file_read_guard_int(raw_state.get("mtime_ns")),
            "size": _normalized_file_read_guard_int(raw_state.get("size")),
        }
    return normalized


def restore_file_read_guard_state(registry: Any, state: Dict[str, Any] | None) -> Dict[str, Dict[str, int]]:
    if registry is None:
        return {}
    payload = {}
    if isinstance(state, dict):
        payload = dict(state.get("file_read_guard_state") or {})
    workspace = file_workspace_root(registry) if getattr(registry, "WORKSPACE_ROOT", None) or getattr(registry, "PROJECT_ROOT", None) else None
    normalized: Dict[str, Dict[str, int]] = {}
    for raw_path, raw_state in payload.items():
        if not isinstance(raw_state, dict):
            continue
        path_text = _normalized_file_read_guard_path(raw_path, workspace=workspace)
        if not path_text:
            continue
        normalized[path_text] = {
            "mtime_ns": _normalized_file_read_guard_int(raw_state.get("mtime_ns")),
            "size": _normalized_file_read_guard_int(raw_state.get("size")),
        }
    setattr(registry, "_file_read_state", normalized)
    return normalized


def event(name: str, ok: bool, summary: str, payload: Dict[str, Any]) -> ToolEvent:
    return ToolEvent(name=name, ok=bool(ok), summary=summary, payload=payload)


def compact_arguments(arguments: Dict[str, Any] | None) -> Dict[str, Any]:
    compact: Dict[str, Any] = {}
    for key, value in dict(arguments or {}).items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        compact[key] = value
    return compact


def result_from_event(
    registry: Any,
    assistant_text: str,
    event_item: ToolEvent,
    *,
    tool_name: str | None = None,
    arguments: Dict[str, Any] | None = None,
) -> CommandExecutionResult:
    normalized_arguments = compact_arguments(arguments)
    item_events = generic_tool_call_item_events(
        tool_name=str(tool_name or event_item.name or "").strip(),
        arguments=normalized_arguments or None,
        ok=bool(event_item.ok),
        summary=str(event_item.summary or ""),
        structured_content=dict(event_item.payload or {}),
    )
    return CommandExecutionResult(
        assistant_text=str(assistant_text or ""),
        tool_events=[event_item],
        item_events=item_events,
    )


def call_structured_helper(
    target: Any,
    method_name: str,
    *args: Any,
    **kwargs: Any,
) -> CommandExecutionResult | None:
    method = getattr(target, method_name, None)
    if not callable(method):
        return None
    try:
        result = method(*args, **kwargs)
    except TypeError:
        return None
    return result if isinstance(result, CommandExecutionResult) else None


def legacy_capabilities(registry: Any) -> Dict[str, Any]:
    return registry.capabilities()


def capabilities(registry: Any, *, build_capabilities_payload_fn: Any) -> Dict[str, Any]:
    return build_capabilities_payload_fn(plugin_manager_factory=lambda: registry._plugin_manager)


def list_plugins(registry: Any) -> ToolEvent:
    return registry._plugin_bridge.list_plugins()


def list_plugins_result(registry: Any) -> CommandExecutionResult:
    return result_from_event(registry, "List plugins.", list_plugins(registry), tool_name="plugins")


def enable_plugin(registry: Any, plugin_name: str) -> ToolEvent:
    return registry._plugin_bridge.enable_plugin(plugin_name)


def enable_plugin_result(registry: Any, plugin_name: str) -> CommandExecutionResult:
    return result_from_event(
        registry,
        "Enable plugin.",
        enable_plugin(registry, plugin_name),
        tool_name="plugin_enable",
        arguments={"plugin_name": plugin_name},
    )


def disable_plugin(registry: Any, plugin_name: str) -> ToolEvent:
    return registry._plugin_bridge.disable_plugin(plugin_name)


def disable_plugin_result(registry: Any, plugin_name: str) -> CommandExecutionResult:
    return result_from_event(
        registry,
        "Disable plugin.",
        disable_plugin(registry, plugin_name),
        tool_name="plugin_disable",
        arguments={"plugin_name": plugin_name},
    )


def disable_all_plugins(registry: Any) -> ToolEvent:
    return registry._plugin_bridge.disable_all_plugins()


def disable_all_plugins_result(registry: Any) -> CommandExecutionResult:
    return result_from_event(
        registry,
        "Disable all plugins.",
        disable_all_plugins(registry),
        tool_name="plugin_disable",
        arguments={"all": True},
    )


def reload_plugins(registry: Any) -> ToolEvent:
    return registry._plugin_bridge.reload_plugins()


def reload_plugins_result(registry: Any) -> CommandExecutionResult:
    return result_from_event(registry, "Reload plugins.", reload_plugins(registry), tool_name="plugin_reload")


def install_plugin(registry: Any, path: str, *, replace: bool = False, scope: str = "user") -> ToolEvent:
    return registry._plugin_bridge.install_plugin(path, replace=replace, scope=scope)


def install_plugin_result(
    registry: Any,
    path: str,
    *,
    replace: bool = False,
    scope: str = "user",
) -> CommandExecutionResult:
    return result_from_event(
        registry,
        "Install plugin.",
        install_plugin(registry, path, replace=replace, scope=scope),
        tool_name="plugin_install",
        arguments={"path": path, "replace": bool(replace), "scope": scope},
    )


def remove_plugin(registry: Any, plugin_name: str) -> ToolEvent:
    return registry._plugin_bridge.remove_plugin(plugin_name)


def remove_plugin_result(registry: Any, plugin_name: str) -> CommandExecutionResult:
    return result_from_event(
        registry,
        "Remove plugin.",
        remove_plugin(registry, plugin_name),
        tool_name="plugin_remove",
        arguments={"plugin_name": plugin_name},
    )


def plugin_command_specs(registry: Any) -> list[Dict[str, str]]:
    return registry._plugin_bridge.command_specs()


def run_plugin_command(
    registry: Any,
    name: str,
    arg_text: str,
    runtime: Any,
) -> tuple[str, list[ToolEvent]] | None:
    result = registry._plugin_bridge.execute_command(name, arg_text, runtime)
    if result is None:
        return None
    return result


def run_plugin_command_result(
    registry: Any,
    name: str,
    arg_text: str,
    runtime: Any,
) -> CommandExecutionResult | None:
    result_getter = getattr(registry._plugin_bridge, "execute_command_result", None)
    if callable(result_getter):
        result = result_getter(name, arg_text, runtime)
        if result is not None:
            return result
    raw_result = run_plugin_command(registry, name, arg_text, runtime)
    if raw_result is None:
        return None
    if isinstance(raw_result, CommandExecutionResult):
        return raw_result
    assistant_text, events = raw_result
    item_events, _ = tool_events_to_turn_events(list(events or []), start_index=0)
    return CommandExecutionResult(
        assistant_text=str(assistant_text or ""),
        tool_events=list(events or []),
        item_events=item_events,
    )


def invoke_plugin_tool(registry: Any, name: str, *args: Any, **kwargs: Any) -> ToolEvent:
    return registry._plugin_bridge.invoke_tool(name, *args, **kwargs)


def invoke_plugin_tool_result(
    registry: Any,
    name: str,
    *args: Any,
    **kwargs: Any,
) -> CommandExecutionResult:
    return registry._plugin_bridge.invoke_tool_result(name, *args, **kwargs)

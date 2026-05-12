from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from cli.agent_cli.host_platform import HostPlatform
from cli.agent_cli.host.plugin_manager import PluginManager
from cli.agent_cli.models import ToolEvent
from cli.agent_cli.providers.tool_call_browser import browser_tool_call_command
from cli.agent_cli.providers.tool_call_content import content_tool_call_command
from cli.agent_cli.providers.tool_call_runtime import runtime_tool_call_command


def plugin_system_prompt_addendum(
    *,
    plugin_manager_factory: Optional[Callable[[], Optional[PluginManager]]] = None,
) -> str:
    manager = plugin_manager_factory() if plugin_manager_factory is not None else PluginManager()
    if manager is None:
        return ""
    fragments = [str(item or "").strip() for item in manager.provider_system_prompt_fragments() if str(item or "").strip()]
    hints = [str(item or "").strip() for item in manager.provider_routing_hints() if str(item or "").strip()]
    parts: List[str] = []
    if fragments:
        parts.append(" ".join(fragments))
    if hints:
        parts.append(" ".join(hints))
    return " ".join(parts).strip()


def plugin_tool_call_command(
    name: str,
    arguments: Dict[str, Any],
    *,
    quote_arg_fn: Callable[[Any], str],
    plugin_manager_factory: Optional[Callable[[], Optional[PluginManager]]] = None,
) -> Optional[str]:
    command_name = str(name or "").strip()
    if not command_name:
        return None
    manager = plugin_manager_factory() if plugin_manager_factory is not None else PluginManager()
    if manager is None:
        return None
    known_commands = {
        str(item.get("name") or "").strip()
        for item in manager.command_specs()
        if str(item.get("name") or "").strip()
    }
    if command_name not in known_commands:
        return None
    command = f"/{command_name}"
    for key, value in arguments.items():
        option = str(key or "").strip().replace("_", "-")
        if not option or value is None:
            continue
        if isinstance(value, bool):
            if value:
                command += f" --{option}"
            continue
        if isinstance(value, (list, tuple)):
            for item in value:
                text = str(item or "").strip()
                if text:
                    command += f" --{option} {quote_arg_fn(text)}"
            continue
        text = str(value).strip()
        if text:
            command += f" --{option} {quote_arg_fn(text)}"
    return command
def command_for_tool_call(
    name: str,
    arguments: Dict[str, Any],
    host_platform: HostPlatform,
    *,
    optional_bool_fn: Callable[[Any, bool], bool],
    quote_arg_fn: Callable[[Any], str],
    plugin_manager_factory: Optional[Callable[[], Optional[PluginManager]]] = None,
) -> Optional[str]:
    del optional_bool_fn
    runtime_command = runtime_tool_call_command(
        name,
        arguments,
        host_platform,
        quote_arg_fn=quote_arg_fn,
    )
    if runtime_command is not None:
        return runtime_command

    content_command = content_tool_call_command(
        name,
        arguments,
        host_platform,
        quote_arg_fn=quote_arg_fn,
    )
    if content_command is not None:
        return content_command

    if name == "browser":
        return browser_tool_call_command(arguments, quote_arg_fn=quote_arg_fn)

    return plugin_tool_call_command(
        name,
        arguments,
        quote_arg_fn=quote_arg_fn,
        plugin_manager_factory=plugin_manager_factory,
    )


def tool_result_payload(command_text: Optional[str], assistant_text: str, events: List[ToolEvent]) -> Dict[str, Any]:
    def _trim(value: Any, *, text_limit: int = 1200) -> Any:
        if isinstance(value, str):
            return value[:text_limit]
        if isinstance(value, dict):
            return {str(key): _trim(item, text_limit=text_limit) for key, item in list(value.items())[:20]}
        if isinstance(value, list):
            return [_trim(item, text_limit=text_limit) for item in value[:20]]
        return value

    def _trim_event_payload(event: ToolEvent) -> Dict[str, Any]:
        payload = dict(event.payload or {})
        if event.name not in {"file_read", "spawn_agent", "wait_agent", "wait"}:
            return _trim(payload)
        trimmed = _trim(payload)
        text = str(payload.get("text") or "")
        if text:
            # file_read / spawn_agent / wait already have a meaningful bounded body payload.
            trimmed["text"] = text[:12000]
        return trimmed

    summary_items = [
        {
            "name": event.name,
            "ok": bool(event.ok),
            "summary": event.summary,
            "payload": _trim_event_payload(event),
        }
        for event in events[-4:]
    ]
    last_event = events[-1] if events else None
    normalized_command = str(command_text or "").strip().lower()
    legacy_file_alias_used = normalized_command.startswith("/file_search") or normalized_command.startswith("/file_list")
    legacy_replacement = ""
    if normalized_command.startswith("/file_search"):
        legacy_replacement = "grep_files + read_file/file_read"
    elif normalized_command.startswith("/file_list"):
        legacy_replacement = "list_dir"
    return {
        "ok": bool(last_event.ok) if last_event is not None else bool(command_text),
        "command_text": command_text,
        "assistant_text": assistant_text[:400],
        "events": summary_items,
        "legacy_file_alias_used": legacy_file_alias_used,
        "legacy_file_alias_replacement": legacy_replacement,
    }

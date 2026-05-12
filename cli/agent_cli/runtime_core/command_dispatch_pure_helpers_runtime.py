from __future__ import annotations

from typing import Any

_TOOL_TURN_ITEM_TYPES = {
    "command_execution",
    "mcp_tool_call",
    "function_call",
    "function_call_output",
    "custom_tool_call",
    "custom_tool_call_output",
    "shell_call",
    "shell_call_output",
    "local_shell_call",
    "local_shell_call_output",
}


def failed_tool_output_text(payload: dict[str, Any], *, summary: str = "") -> str:
    for key in ("error", "stderr", "aggregated_output", "output_text", "stdout"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    function_call_output = str(payload.get("function_call_output") or "").strip()
    if function_call_output:
        return function_call_output
    return str(summary or "").strip()


def successful_command_tool_output_text(payload: dict[str, Any], *, summary: str = "") -> str:
    for key in ("stdout", "aggregated_output", "output_text", "text"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    function_call_output = str(payload.get("function_call_output") or "").strip()
    if function_call_output:
        return function_call_output
    return str(summary or "").strip()


def final_agent_message_text(turn_events: list[dict[str, Any]]) -> str:
    for event in reversed(list(turn_events or [])):
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() != "agent_message":
            continue
        text = str(item.get("text") or "").strip()
        if text:
            return text
    return ""


def merge_commentary_text(existing: str, addition: str) -> str:
    existing_text = str(existing or "").strip()
    addition_text = str(addition or "").strip()
    if not existing_text:
        return addition_text
    if not addition_text or addition_text == existing_text:
        return existing_text
    return f"{existing_text}\n\n{addition_text}"


def turn_events_include_tool_items(turn_events: list[dict[str, Any]]) -> bool:
    for event in list(turn_events or []):
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip()
        if item_type in _TOOL_TURN_ITEM_TYPES:
            return True
    return False


def unknown_command_assistant_text(command_name: str) -> str:
    return f"未知命令: /{command_name}\n输入 /help 查看可用命令。"

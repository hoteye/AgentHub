from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli.web_search_argument_projection_runtime import (
    normalized_web_search_mcp_call_arguments as _normalized_web_search_mcp_call_arguments_shared,
)

_TEXT_FIRST_TOOLS = {"apply_patch", "grep_files", "read_file", "list_dir", "file_search", "file_read", "file_list"}
_TOOL_CALL_INPUT_ITEM_TYPES = {
    "function_call",
    "custom_tool_call",
    "shell_call",
    "local_shell_call",
}
_TOOL_CALL_OUTPUT_ITEM_TYPES = {
    "function_call_output",
    "custom_tool_call_output",
    "shell_call_output",
    "local_shell_call_output",
}
_TURN_EVENT_TOOL_HISTORY_ITEM_TYPES = {"command_execution", "mcp_tool_call", "todo_list"}
_COMMAND_FAMILY_FUNCTION_NAMES = {"exec_command", "write_stdin"}


def is_text_first_tool(tool_name: str) -> bool:
    return str(tool_name or "").strip() in _TEXT_FIRST_TOOLS


def is_turn_event_tool_history_item_type(item_type: str) -> bool:
    return item_type in _TURN_EVENT_TOOL_HISTORY_ITEM_TYPES


def is_command_family_function_name(function_name: str) -> bool:
    return str(function_name or "").strip() in _COMMAND_FAMILY_FUNCTION_NAMES


def is_synthetic_tool_item_id(item_id: str) -> bool:
    normalized = str(item_id or "").strip().lower()
    return normalized == "item" or normalized.startswith(("item_", "item-", "item.", "stream_item_"))


def sanitize_tool_input_item(item: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(item or {})
    item_type = str(normalized.get("type") or "").strip().lower()
    if item_type not in _TOOL_CALL_INPUT_ITEM_TYPES:
        return normalized
    item_id = str(normalized.get("id") or "").strip()
    if is_synthetic_tool_item_id(item_id):
        normalized.pop("id", None)
    return normalized


def is_tool_call_input_item_type(item_type: str) -> bool:
    return item_type in _TOOL_CALL_INPUT_ITEM_TYPES


def is_tool_call_output_item_type(item_type: str) -> bool:
    return item_type in _TOOL_CALL_OUTPUT_ITEM_TYPES


def normalized_mcp_call_arguments(item: dict[str, Any]) -> Any:
    return _normalized_web_search_mcp_call_arguments_shared(item)


def turn_event_tool_history_available(turn_events: List[Dict[str, Any]]) -> bool:
    for raw_event in list(turn_events or []):
        if not isinstance(raw_event, dict):
            continue
        item = raw_event.get("item")
        if not isinstance(item, dict):
            continue
        if is_turn_event_tool_history_item_type(str(item.get("type") or "").strip().lower()):
            return True
    return False

from __future__ import annotations

from typing import Any

from cli.agent_cli.models import (
    ResponseInputItem,
    _reference_wrapped_shell_command,
    compose_turn_events_from_response_items,
    response_items_to_text,
    todo_list_turn_event_from_plan_payload,
)
from cli.agent_cli.runtime_core.command_parsing import parse_args


def _provisional_started_item_event(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    command_text: str | None,
    item_id: str,
    call_id: str = "",
    shell_metadata: dict[str, Any] | None = None,
    active_todo_list_id: str | None = None,
) -> dict[str, Any]:
    normalized_tool_name = _effective_tool_item_name(
        tool_name=tool_name,
        command_text=command_text,
    )
    normalized_call_id = str(call_id or "").strip()
    resolved_item_id = normalized_call_id or str(item_id or "")
    if normalized_tool_name == "update_plan":
        event = todo_list_turn_event_from_plan_payload(
            dict(arguments or {}),
            item_id=str(active_todo_list_id or resolved_item_id),
            event_type="item.updated" if active_todo_list_id else "item.started",
        )
        item = event.get("item")
        if normalized_call_id and isinstance(item, dict):
            item["call_id"] = normalized_call_id
        return event
    if normalized_tool_name in {"shell", "exec_command", "write_stdin"}:
        item = {
            "type": "item.started",
            "item": {
                "id": resolved_item_id,
                "type": "command_execution",
                "command": _provisional_wrapped_command_text(
                    command_text,
                    arguments=arguments,
                    shell_metadata=shell_metadata,
                ),
                "aggregated_output": "",
                "exit_code": None,
                "status": "in_progress",
            },
        }
        if normalized_call_id:
            item["item"]["call_id"] = normalized_call_id
        if normalized_tool_name in {"exec_command", "write_stdin"}:
            item["item"]["function_call_name"] = normalized_tool_name
            item["item"]["function_call_arguments"] = dict(arguments or {})
        return item
    event = {
        "type": "item.started",
        "item": {
            "id": resolved_item_id,
            "type": "mcp_tool_call",
            "server": "local",
            "tool": normalized_tool_name,
            "arguments": dict(arguments or {}),
            "result": None,
            "error": None,
            "status": "in_progress",
        },
    }
    if normalized_call_id:
        event["item"]["call_id"] = normalized_call_id
    return event


def _effective_tool_item_name(*, tool_name: str, command_text: str | None) -> str:
    normalized_tool_name = str(tool_name or "").strip()
    normalized_command = str(command_text or "").strip()
    if not normalized_command.startswith("/"):
        return normalized_tool_name
    command_name = normalized_command[1:].split(None, 1)[0].strip()
    return command_name or normalized_tool_name


def _provisional_command_text(command_text: str | None) -> str:
    normalized_command = str(command_text or "").strip()
    if not normalized_command.startswith("/exec_command"):
        return normalized_command
    arg_text = normalized_command[len("/exec_command") :].strip()
    try:
        positionals, options = parse_args(arg_text)
    except ValueError:
        return normalized_command
    return str(options.get("cmd") or " ".join(positionals)).strip() or normalized_command


def _provisional_wrapped_command_text(
    command_text: str | None,
    *,
    arguments: dict[str, Any],
    shell_metadata: dict[str, Any] | None = None,
) -> str:
    command = _provisional_command_text(command_text)
    payload = {
        key: value
        for key, value in dict(arguments or {}).items()
        if key in {"shell", "resolved_shell", "login"}
    }
    payload.update(
        {
            key: value
            for key, value in dict(shell_metadata or {}).items()
            if key in {"shell", "resolved_shell", "login"}
        }
    )
    return _reference_wrapped_shell_command(payload, command)


def _started_item_matches_provisional(
    provisional_started: dict[str, Any],
    candidate: dict[str, Any],
) -> bool:
    if str(provisional_started.get("type") or "") not in {"item.started", "item.updated"}:
        return False
    if str(candidate.get("type") or "") != str(provisional_started.get("type") or ""):
        return False
    provisional_item = provisional_started.get("item")
    candidate_item = candidate.get("item")
    if not isinstance(provisional_item, dict) or not isinstance(candidate_item, dict):
        return False
    if str(provisional_item.get("type") or "") != str(candidate_item.get("type") or ""):
        return False
    provisional_status = str(provisional_item.get("status") or "")
    candidate_status = str(candidate_item.get("status") or "")
    if provisional_status or candidate_status:
        return provisional_status == candidate_status
    return True


def _response_item_events(response_items: list[ResponseInputItem]) -> list[dict[str, Any]]:
    if not response_items:
        return []
    composed = compose_turn_events_from_response_items(
        assistant_text=response_items_to_text(list(response_items or [])),
        response_items=list(response_items or []),
        executed_item_events=[],
    )
    return [
        dict(event)
        for event in list(composed or [])
        if isinstance(event, dict) and str(event.get("type") or "").strip() == "item.completed"
    ]


def _tool_item_events_from_turn_events(turn_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tool_item_types = {
        "command_execution",
        "mcp_tool_call",
        "todo_list",
        "function_call",
        "function_call_output",
        "custom_tool_call",
        "custom_tool_call_output",
        "shell_call",
        "shell_call_output",
        "local_shell_call",
        "local_shell_call_output",
    }
    item_events: list[dict[str, Any]] = []
    for raw_event in list(turn_events or []):
        if not isinstance(raw_event, dict):
            continue
        item = raw_event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() not in tool_item_types:
            continue
        item_events.append(dict(raw_event))
    return item_events


def _next_item_index(events: list[dict[str, Any]]) -> int:
    highest = -1
    for event in list(events or []):
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "").strip()
        if not item_id.startswith("item_"):
            continue
        try:
            highest = max(highest, int(item_id.split("_", 1)[1]))
        except (TypeError, ValueError):
            continue
    return highest + 1


def _item_event_id(event: dict[str, Any] | None) -> str:
    if not isinstance(event, dict):
        return ""
    item = event.get("item")
    if not isinstance(item, dict):
        return ""
    return str(item.get("id") or "").strip()


def _rebase_item_events(events: list[dict[str, Any]], *, start_index: int) -> list[dict[str, Any]]:
    mapping: dict[str, str] = {}
    used_ids: set[str] = set()
    next_index = int(start_index)
    rebased: list[dict[str, Any]] = []
    for event in list(events or []):
        if not isinstance(event, dict):
            continue
        copied = dict(event)
        item = copied.get("item")
        if not isinstance(item, dict):
            rebased.append(copied)
            continue
        item_copy = dict(item)
        original_id = str(item_copy.get("id") or "").strip()
        if original_id:
            replacement = mapping.get(original_id)
            if replacement is None:
                replacement = original_id
                original_index: int | None = None
                if replacement.startswith("item_"):
                    try:
                        original_index = int(replacement.split("_", 1)[1])
                    except (TypeError, ValueError):
                        original_index = None
                if replacement in used_ids or (
                    original_index is not None and original_index < start_index
                ):
                    while f"item_{next_index}" in used_ids:
                        next_index += 1
                    replacement = f"item_{next_index}"
                    next_index += 1
                elif replacement.startswith("item_"):
                    try:
                        next_index = max(next_index, int(replacement.split("_", 1)[1]) + 1)
                    except (TypeError, ValueError):
                        pass
                mapping[original_id] = replacement
                used_ids.add(replacement)
            item_copy["id"] = replacement
        copied["item"] = item_copy
        rebased.append(copied)
    return rebased

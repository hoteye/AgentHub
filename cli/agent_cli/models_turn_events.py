from __future__ import annotations

import json
from typing import Any

from cli.agent_cli import models_turn_events_helpers as models_turn_events_helpers_service
from cli.agent_cli import models_turn_events_runtime as models_turn_events_runtime_service
from cli.agent_cli.models import (
    ResponseInputItem,
    ToolEvent,
    _reference_wrapped_shell_command,
    tool_event_is_soft_failure,
    tool_event_result_text,
)


def tool_events_to_turn_events(
    events: list[ToolEvent],
    *,
    start_index: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    turn_events: list[dict[str, Any]] = []
    next_index = int(start_index)
    for tool_event in list(events or []):
        item_events, next_index = _tool_event_to_turn_items(tool_event, start_index=next_index)
        turn_events.extend(item_events)
    return turn_events, next_index


def normalized_plan_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    return models_turn_events_runtime_service.normalized_plan_payload(payload)


def plan_payload_from_todo_list_item(item: dict[str, Any] | None) -> dict[str, Any]:
    return models_turn_events_runtime_service.plan_payload_from_todo_list_item(item)


def todo_list_items_from_plan_payload(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    return models_turn_events_runtime_service.todo_list_items_from_plan_payload(payload)


def todo_list_turn_item_from_plan_payload(
    payload: dict[str, Any] | None,
    *,
    item_id: str,
) -> dict[str, Any]:
    return models_turn_events_runtime_service.todo_list_turn_item_from_plan_payload(
        payload, item_id=item_id
    )


def todo_list_turn_event_from_plan_payload(
    payload: dict[str, Any] | None,
    *,
    item_id: str,
    event_type: str,
) -> dict[str, Any]:
    return models_turn_events_runtime_service.todo_list_turn_event_from_plan_payload(
        payload,
        item_id=item_id,
        event_type=event_type,
    )


latest_open_todo_list_item = models_turn_events_helpers_service.latest_open_todo_list_item


completed_todo_list_turn_events = models_turn_events_helpers_service.completed_todo_list_turn_events


reasoning_explicit_text_from_turn_event_item = (
    models_turn_events_helpers_service.reasoning_explicit_text_from_turn_event_item
)


reasoning_replay_projection_from_turn_event_item = (
    models_turn_events_helpers_service.reasoning_replay_projection_from_turn_event_item
)


def generic_tool_call_item_events(
    *,
    tool_name: str,
    arguments: Any = None,
    ok: bool,
    summary: str = "",
    structured_content: dict[str, Any] | None = None,
    error_message: str = "",
    item_id: str = "item_0",
    server: str = "local",
) -> list[dict[str, Any]]:
    return models_turn_events_runtime_service.generic_tool_call_item_events(
        tool_name=tool_name,
        arguments=arguments,
        ok=ok,
        summary=summary,
        structured_content=structured_content,
        error_message=error_message,
        item_id=item_id,
        server=server,
    )


def shell_tool_call_item_events(
    tool_event: ToolEvent,
    *,
    item_id: str = "item_0",
    command: str | None = None,
) -> list[dict[str, Any]]:
    payload = dict(tool_event.payload or {})
    if command is not None and str(command).strip():
        payload["command"] = str(command).strip()
    normalized_event = ToolEvent(
        name=str(tool_event.name or ""),
        ok=bool(tool_event.ok),
        summary=str(tool_event.summary or ""),
        payload=payload,
    )
    return _shell_tool_event_to_turn_items(normalized_event, item_id=item_id)


def _response_item_to_turn_item(item: ResponseInputItem, *, item_id: str) -> dict[str, Any] | None:
    return models_turn_events_runtime_service.response_item_to_turn_item(
        item,
        item_id=item_id,
        turn_event_content_text_fn=_turn_event_content_text,
        turn_event_content_types_fn=_turn_event_content_types,
    )


def canonical_command_execution_item_from_provider_shell_payload(
    payload: dict[str, Any] | None,
    *,
    item_id: str,
) -> dict[str, Any] | None:
    return models_turn_events_runtime_service.canonical_command_execution_item_from_provider_shell_payload(
        payload,
        item_id=item_id,
    )


def _tool_event_to_turn_items(
    tool_event: ToolEvent, *, start_index: int
) -> tuple[list[dict[str, Any]], int]:
    item_id = f"item_{start_index}"
    if str(tool_event.name or "").strip() == "update_plan":
        return [
            todo_list_turn_event_from_plan_payload(
                dict(tool_event.payload or {}),
                item_id=item_id,
                event_type="item.started",
            )
        ], start_index + 1
    if _tool_event_is_shell(tool_event):
        return _shell_tool_event_to_turn_items(tool_event, item_id=item_id), start_index + 1
    return _generic_tool_event_to_turn_items(tool_event, item_id=item_id), start_index + 1


def _tool_event_is_shell(tool_event: ToolEvent) -> bool:
    normalized = str(tool_event.name or "").strip().lower()
    return normalized.startswith("shell") or normalized in {"exec_command", "write_stdin"}


def _shell_tool_event_to_turn_items(tool_event: ToolEvent, *, item_id: str) -> list[dict[str, Any]]:
    return models_turn_events_runtime_service.shell_tool_event_to_turn_items(
        tool_event=tool_event,
        item_id=item_id,
        reference_wrapped_shell_command_fn=_reference_wrapped_shell_command,
        shell_aggregated_output_fn=_shell_aggregated_output,
        shell_exit_code_fn=_shell_exit_code,
        shell_status_fn=_shell_status,
    )


def _generic_tool_event_to_turn_items(
    tool_event: ToolEvent, *, item_id: str
) -> list[dict[str, Any]]:
    return models_turn_events_runtime_service.generic_tool_event_to_turn_items(
        tool_event=tool_event,
        item_id=item_id,
        tool_event_is_soft_failure_fn=tool_event_is_soft_failure,
        tool_event_result_text_fn=tool_event_result_text,
        generic_tool_error_message_fn=_generic_tool_error_message,
    )


def _generic_tool_error_message(tool_event: ToolEvent) -> str:
    payload = dict(tool_event.payload or {})
    for key in ("error", "stderr", "message"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    return str(tool_event.summary or tool_event.name or "tool failed").strip()


def _response_item_tool_key(item: dict[str, Any]) -> tuple[str, str]:
    return (
        str(item.get("type") or "").strip().lower(),
        str(item.get("call_id") or item.get("tool_call_id") or item.get("id") or "").strip(),
    )


def _reasoning_text_from_turn_event_item(item: dict[str, Any]) -> str:
    return models_turn_events_helpers_service.reasoning_text_from_turn_event_item(item)


def _reasoning_turn_event_key(item: dict[str, Any]) -> tuple[str, str, str]:
    text = _reasoning_text_from_turn_event_item(item)
    summary = item.get("summary")
    try:
        summary_key = json.dumps(summary, ensure_ascii=False, sort_keys=True)
    except TypeError:
        summary_key = str(summary)
    encrypted_content = str(item.get("encrypted_content") or "").strip()
    return (text, summary_key, encrypted_content)


def reasoning_input_item_from_turn_event_item(item: dict[str, Any]) -> dict[str, Any] | None:
    return models_turn_events_helpers_service.reasoning_input_item_from_turn_event_item(item)


def _reasoning_content_has_text(content: Any) -> bool:
    return models_turn_events_helpers_service.reasoning_content_has_text(content)


def reasoning_replay_input_item_from_turn_event_item(item: dict[str, Any]) -> dict[str, Any] | None:
    projection = reasoning_replay_projection_from_turn_event_item(item)
    projected = projection.get("input_item")
    return dict(projected) if isinstance(projected, dict) else None


def _rebase_turn_item_events(
    events: list[dict[str, Any]],
    *,
    start_index: int,
) -> tuple[list[dict[str, Any]], int]:
    mapping: dict[str, str] = {}
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
                replacement = f"item_{next_index}"
                mapping[original_id] = replacement
                next_index += 1
            item_copy["id"] = replacement
        copied["item"] = item_copy
        rebased.append(copied)
    return rebased, next_index


def _shell_aggregated_output(payload: dict[str, Any]) -> str:
    chunks: list[str] = []
    stdout = str(payload.get("stdout") or payload.get("output_text") or "")
    stderr = str(payload.get("stderr") or "")
    if stdout:
        chunks.append(stdout)
    if stderr and stderr != stdout:
        chunks.append(stderr)
    if not chunks:
        return ""
    return "".join(
        chunk if index == 0 or chunks[index - 1].endswith("\n") else "\n" + chunk
        for index, chunk in enumerate(chunks)
    )


def _shell_exit_code(payload: dict[str, Any]) -> int | None:
    value = payload.get("returncode")
    if value is None:
        value = payload.get("exit_code")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _shell_status(tool_event: ToolEvent) -> str:
    normalized_name = str(tool_event.name or "").strip().lower()
    if normalized_name == "shell_approval_requested":
        return "declined"
    payload = dict(tool_event.payload or {})
    if normalized_name == "exec_command" and _shell_exit_code(payload) is None:
        live_status = str(payload.get("status") or "").strip().lower()
        if str(payload.get("session_id") or "").strip() or live_status in {
            "written",
            "noop",
            "running",
            "started",
            "subscribed",
            "written_partial",
        }:
            return "in_progress"
    return "completed" if tool_event.ok else "failed"


def _turn_event_content_types(content: Any) -> set[str]:
    if not isinstance(content, list):
        return set()
    return {
        str(entry.get("type") or "").strip().lower() for entry in content if isinstance(entry, dict)
    }


def _turn_event_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return str(content.get("text") or "")
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for entry in content:
        if not isinstance(entry, dict):
            continue
        block_type = str(entry.get("type") or "").strip().lower()
        if block_type in {"output_text", "input_text", "text", "reasoning"}:
            text = str(entry.get("text") or "")
            if text:
                parts.append(text)
    return "".join(parts)


def _turn_event_usage_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

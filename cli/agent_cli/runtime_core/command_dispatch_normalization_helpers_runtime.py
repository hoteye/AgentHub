from __future__ import annotations

from typing import Any

from cli.agent_cli.models import CommandExecutionResult, ToolEvent


def command_result_turn_events(
    *,
    assistant_text: str,
    commentary_text: str,
    item_events: list[dict[str, Any]],
    compose_turn_events_from_response_items_fn: Any,
    default_response_items_fn: Any,
) -> list[dict[str, Any]]:
    return compose_turn_events_from_response_items_fn(
        assistant_text=assistant_text,
        response_items=default_response_items_fn(
            commentary_text=commentary_text,
            assistant_text=assistant_text,
        ),
        executed_item_events=[
            dict(item)
            for item in list(item_events or [])
            if isinstance(item, dict)
        ],
    )


def command_turn_events_with_display_text(
    turn_events: list[dict[str, Any]],
    command_display_text: str,
) -> list[dict[str, Any]]:
    display_text = str(command_display_text or "").strip()
    normalized_turn_events = [
        dict(item)
        for item in list(turn_events or [])
        if isinstance(item, dict)
    ]
    if not display_text:
        return normalized_turn_events

    last_agent_message_index = -1
    for index, event in enumerate(normalized_turn_events):
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        if str(item.get("type") or "").strip() == "agent_message":
            last_agent_message_index = index

    if last_agent_message_index < 0:
        return normalized_turn_events

    projected_events = [dict(item) for item in normalized_turn_events]
    projected_event = dict(projected_events[last_agent_message_index])
    projected_item = dict(projected_event.get("item") or {})
    projected_item["text"] = display_text
    projected_event["item"] = projected_item
    projected_events[last_agent_message_index] = projected_event
    return projected_events


def command_result_from_values(
    *,
    assistant_text: Any,
    command_display_text: Any = "",
    tool_events: list[ToolEvent],
    item_events: list[dict[str, Any]],
    turn_events: list[dict[str, Any]],
    commentary_text: str,
    command_result_turn_events_fn: Any,
) -> CommandExecutionResult:
    normalized_item_events = [
        dict(item)
        for item in list(item_events or [])
        if isinstance(item, dict)
    ]
    normalized_turn_events = [
        dict(item)
        for item in list(turn_events or [])
        if isinstance(item, dict)
    ]
    if not normalized_turn_events:
        normalized_turn_events = command_result_turn_events_fn(
            assistant_text=str(command_display_text or "").strip() or assistant_text,
            commentary_text=commentary_text,
            item_events=normalized_item_events,
        )
    else:
        normalized_turn_events = command_turn_events_with_display_text(
            normalized_turn_events,
            str(command_display_text or ""),
        )
    return CommandExecutionResult(
        assistant_text=assistant_text,
        command_display_text=str(command_display_text or ""),
        tool_events=list(tool_events or []),
        item_events=normalized_item_events,
        turn_events=normalized_turn_events,
    )


def normalize_command_result(
    result: Any,
    *,
    tool_events_to_turn_events_fn: Any,
    command_result_turn_events_fn: Any,
) -> CommandExecutionResult:
    if isinstance(result, CommandExecutionResult):
        assistant_text = str(result.assistant_text or "")
        command_display_text = str(result.command_display_text or "")
        events = list(result.tool_events or [])
        item_events = [
            dict(item)
            for item in list(result.item_events or [])
            if isinstance(item, dict)
        ]
        turn_events = [
            dict(item)
            for item in list(result.turn_events or [])
            if isinstance(item, dict)
        ]
        if not item_events and events:
            item_events, _ = tool_events_to_turn_events_fn(list(events or []), start_index=0)
        return command_result_from_values(
            assistant_text=assistant_text,
            command_display_text=command_display_text,
            tool_events=events,
            item_events=item_events,
            turn_events=turn_events,
            commentary_text="",
            command_result_turn_events_fn=command_result_turn_events_fn,
        )

    assistant_text, events = result
    item_events, _ = tool_events_to_turn_events_fn(list(events or []), start_index=0)
    return command_result_from_values(
        assistant_text=assistant_text,
        command_display_text="",
        tool_events=list(events or []),
        item_events=item_events,
        turn_events=[],
        commentary_text="",
        command_result_turn_events_fn=command_result_turn_events_fn,
    )


def command_parse_error_result(
    *,
    text: str,
    exc: ValueError,
    tool_events_to_turn_events_fn: Any,
    command_result_turn_events_fn: Any,
) -> CommandExecutionResult:
    event = ToolEvent(
        name="command_parse",
        ok=False,
        summary="command parse failed",
        payload={
            "ok": False,
            "command": str(text or "").strip(),
            "error": str(exc),
        },
    )
    assistant_text = f"命令解析失败: {exc}"
    item_events, _ = tool_events_to_turn_events_fn([event], start_index=0)
    return command_result_from_values(
        assistant_text=assistant_text,
        command_display_text=assistant_text,
        tool_events=[event],
        item_events=item_events,
        turn_events=[],
        commentary_text="",
        command_result_turn_events_fn=command_result_turn_events_fn,
    )

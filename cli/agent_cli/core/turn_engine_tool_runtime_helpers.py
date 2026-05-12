from __future__ import annotations

from typing import Any

from cli.agent_cli.core.turn_engine_item_events import (
    _item_event_id,
    _rebase_item_events,
    _started_item_matches_provisional,
    _tool_item_events_from_turn_events,
)
from cli.agent_cli.debug_timeline import log_timeline, timeline_debug_enabled
from cli.agent_cli.models import (
    CommandExecutionResult,
    ToolEvent,
    todo_list_turn_event_from_plan_payload,
    tool_events_to_turn_events,
)
from cli.agent_cli.runtime_core.tool_call_context_runtime import (
    active_provider_tool_call_id,
)


def run_tool_executor_structured(
    engine: Any, *, call: Any, command_text: str
) -> CommandExecutionResult:
    provider_call_id = str(getattr(call, "call_id", "") or "").strip() or None
    structured_runner = getattr(engine.tool_executor, "run_structured", None)
    if callable(structured_runner):
        if timeline_debug_enabled():
            log_timeline(
                "turn_engine.tool.execute.begin",
                call_id=getattr(call, "call_id", None),
                tool_name=str(call.name or ""),
                command_text=command_text,
                mode="structured",
            )
        with active_provider_tool_call_id(provider_call_id):
            return structured_runner(command_text)

    if timeline_debug_enabled():
        log_timeline(
            "turn_engine.tool.execute.begin",
            call_id=getattr(call, "call_id", None),
            tool_name=str(call.name or ""),
            command_text=command_text,
            mode="compat",
        )
    with active_provider_tool_call_id(provider_call_id):
        raw_result = engine.tool_executor(command_text)
    if isinstance(raw_result, CommandExecutionResult):
        return raw_result

    assistant_text, events = raw_result
    item_events, _ = tool_events_to_turn_events(list(events or []), start_index=0)
    return CommandExecutionResult(
        assistant_text=assistant_text,
        tool_events=list(events or []),
        item_events=item_events,
    )


def raw_item_events_for_structured_result(
    structured_result: CommandExecutionResult,
) -> list[dict[str, Any]]:
    raw_item_events = [
        dict(item) for item in list(structured_result.item_events or []) if isinstance(item, dict)
    ]
    if raw_item_events or not structured_result.turn_events:
        return raw_item_events
    return _tool_item_events_from_turn_events(
        [dict(item) for item in list(structured_result.turn_events or []) if isinstance(item, dict)]
    )


def annotate_raw_item_events_with_provider_call(
    *,
    raw_item_events: list[dict[str, Any]],
    provider_call_id: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> list[dict[str, Any]]:
    normalized_provider_call_id = str(provider_call_id or "").strip()
    normalized_tool_name = str(tool_name or "").strip()
    annotated: list[dict[str, Any]] = []
    for raw_event in list(raw_item_events or []):
        if not isinstance(raw_event, dict):
            continue
        event = dict(raw_event)
        item = event.get("item")
        if not isinstance(item, dict):
            annotated.append(event)
            continue
        if str(item.get("type") or "").strip().lower() != "command_execution":
            annotated.append(event)
            continue
        item_copy = dict(item)
        previous_call_id = str(item_copy.get("call_id") or "").strip()
        previous_id = str(item_copy.get("id") or "").strip()
        if normalized_provider_call_id:
            item_copy["call_id"] = normalized_provider_call_id
            if not previous_id or previous_id == previous_call_id:
                item_copy["id"] = normalized_provider_call_id
        if normalized_tool_name:
            item_copy["function_call_name"] = normalized_tool_name
        item_copy["function_call_arguments"] = dict(arguments or {})
        event["item"] = item_copy
        annotated.append(event)
    return annotated


def rebase_item_events_for_call(
    *,
    call_arguments: dict[str, Any],
    normalized_tool_name: str,
    active_todo_list_id: str,
    next_item_index: int,
    raw_item_events: list[dict[str, Any]],
    annotated_tool_events: list[ToolEvent],
) -> list[dict[str, Any]]:
    if normalized_tool_name != "update_plan":
        return _rebase_item_events(raw_item_events, start_index=next_item_index)

    todo_payload = dict(call_arguments or {})
    latest_tool_payload = (
        dict(annotated_tool_events[-1].payload or {}) if annotated_tool_events else {}
    )
    if isinstance(latest_tool_payload.get("plan"), list):
        todo_payload = latest_tool_payload
    return [
        todo_list_turn_event_from_plan_payload(
            todo_payload,
            item_id=active_todo_list_id or f"item_{next_item_index}",
            event_type="item.updated" if active_todo_list_id else "item.started",
        )
    ]


def merge_provisional_started_event(
    provisional_started: dict[str, Any],
    rebased_item_events: list[dict[str, Any]],
    raw_item_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not rebased_item_events:
        return rebased_item_events
    first_event = rebased_item_events[0]
    first_raw_event = raw_item_events[0] if raw_item_events else None
    preserved_live_item_id = bool(_item_event_id(first_raw_event)) and _item_event_id(
        first_raw_event
    ) == _item_event_id(first_event)
    if _started_item_matches_provisional(provisional_started, first_event):
        return _coalesced_lifecycle_events(provisional_started, rebased_item_events)
    if _started_item_call_id(provisional_started) and _started_item_call_id(
        provisional_started
    ) == _started_item_call_id(first_event):
        return _coalesced_lifecycle_events(provisional_started, rebased_item_events)
    if preserved_live_item_id:
        return rebased_item_events
    if _started_item_command(provisional_started) and _started_item_command(
        provisional_started
    ) == _started_item_command(first_event):
        return _coalesced_lifecycle_events(provisional_started, rebased_item_events)
    return rebased_item_events


def _coalesced_lifecycle_events(
    provisional_started: dict[str, Any],
    rebased_item_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    first_event = rebased_item_events[0] if rebased_item_events else {}
    provisional_item = provisional_started.get("item")
    first_item = first_event.get("item") if isinstance(first_event, dict) else None
    if not isinstance(provisional_item, dict) or not isinstance(first_item, dict):
        return [provisional_started, *rebased_item_events[1:]]
    replacement_id = str(provisional_item.get("id") or "").strip()
    source_id = str(first_item.get("id") or "").strip()
    replacement_call_id = str(provisional_item.get("call_id") or "").strip()
    if not replacement_id:
        return [provisional_started, *rebased_item_events[1:]]

    coalesced: list[dict[str, Any]] = [provisional_started]
    for raw_event in list(rebased_item_events[1:] or []):
        event = dict(raw_event)
        item = event.get("item")
        if not isinstance(item, dict):
            coalesced.append(event)
            continue
        item_copy = dict(item)
        item_id = str(item_copy.get("id") or "").strip()
        item_call_id = str(item_copy.get("call_id") or "").strip()
        if (source_id and item_id == source_id) or (
            replacement_call_id and item_call_id == replacement_call_id
        ):
            item_copy["id"] = replacement_id
        event["item"] = item_copy
        coalesced.append(event)
    return coalesced


def _started_item_call_id(event: dict[str, Any]) -> str:
    if str(event.get("type") or "").strip() != "item.started":
        return ""
    item = event.get("item")
    if not isinstance(item, dict):
        return ""
    return str(item.get("call_id") or "").strip()


def _started_item_command(event: dict[str, Any]) -> str:
    if str(event.get("type") or "").strip() != "item.started":
        return ""
    item = event.get("item")
    if not isinstance(item, dict):
        return ""
    if str(item.get("type") or "").strip().lower() != "command_execution":
        return ""
    return str(item.get("command") or "").strip()

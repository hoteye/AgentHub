from __future__ import annotations

import json
from typing import Any, Callable

from cli.agent_cli.models import ToolEvent


def shell_turn_events_from_tool_events(
    tool_events: list[ToolEvent],
    *,
    shell_item_events_from_payload_fn: Callable[[dict[str, Any]], list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    payload_to_events = shell_item_events_from_payload_fn or shell_item_events_from_payload
    for tool_event in reversed(list(tool_events or [])):
        if not isinstance(tool_event, ToolEvent):
            continue
        if str(tool_event.name or "").strip() != "shell":
            continue
        payload = dict(tool_event.payload or {})
        item_events = payload_to_events(payload)
        if not item_events:
            continue
        return [
            {"type": "turn.started"},
            *item_events,
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 0,
                    "cached_input_tokens": 0,
                    "output_tokens": 0,
                },
            },
        ]
    return []


def shell_item_events_from_payload(
    payload: dict[str, Any],
    *,
    shell_activity_to_turn_event_fn: Callable[[dict[str, Any]], dict[str, Any] | None] | None = None,
) -> list[dict[str, Any]]:
    activity_to_turn_event = shell_activity_to_turn_event_fn or shell_activity_to_turn_event
    history = payload.get("_event_history")
    if isinstance(history, list):
        item_events: list[dict[str, Any]] = []
        for raw_event in history:
            if not isinstance(raw_event, dict):
                continue
            turn_event = activity_to_turn_event(raw_event)
            if isinstance(turn_event, dict):
                item_events.append(dict(turn_event))
        if item_events:
            return item_events
    turn_event = activity_to_turn_event(payload)
    if isinstance(turn_event, dict):
        return [turn_event]
    return []


def shell_activity_to_turn_event(
    payload: dict[str, Any],
    *,
    shell_phase_fn: Callable[[dict[str, Any] | None], str] | None = None,
    shell_turn_item_fn: Callable[[dict[str, Any] | None], dict[str, Any]] | None = None,
    shell_status_fn: Callable[[dict[str, Any] | None], str] | None = None,
    shell_interaction_input_fn: Callable[[dict[str, Any] | None], str | None] | None = None,
    shell_output_text_fn: Callable[[dict[str, Any] | None], str | None] | None = None,
) -> dict[str, Any] | None:
    phase_fn = shell_phase_fn or shell_phase
    turn_item_fn = shell_turn_item_fn or shell_turn_item
    status_fn = shell_status_fn or shell_status
    input_fn = shell_interaction_input_fn or shell_interaction_input
    output_fn = shell_output_text_fn or shell_output_text
    phase = phase_fn(payload)
    if phase not in {"started", "input", "output", "completed"}:
        return None
    item = turn_item_fn(payload)
    if phase == "started":
        return {"type": "item.started", "item": item}
    if phase in {"input", "output"}:
        updated: dict[str, Any] = {"phase": phase, "status": status_fn(payload)}
        text = input_fn(payload) if phase == "input" else output_fn(payload)
        if text:
            updated["text"] = text
        return {"type": "item.updated", "item": item, "updated": updated}
    return {
        "type": "item.completed",
        "item": item,
        "result": {
            "status": status_fn(payload),
            "stdout": str(payload.get("stdout") or ""),
            "stderr": str(payload.get("stderr") or ""),
        },
    }


def shell_phase(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return ""
    phase = str(payload.get("phase") or "").strip().lower()
    if phase:
        return phase
    lifecycle = payload.get("lifecycle")
    if isinstance(lifecycle, dict):
        return str(lifecycle.get("phase") or "").strip().lower()
    return ""


def shell_status(
    payload: dict[str, Any] | None,
    *,
    shell_phase_fn: Callable[[dict[str, Any] | None], str] | None = None,
) -> str:
    if not isinstance(payload, dict):
        return ""
    status = str(payload.get("status") or "").strip().lower()
    if status:
        return status
    phase = (shell_phase_fn or shell_phase)(payload)
    if phase == "started":
        return "started"
    if phase in {"input", "output"}:
        return "running"
    if phase == "completed":
        return "ok" if bool(payload.get("ok", True)) else "error"
    return ""


def shell_interaction_input(
    payload: dict[str, Any] | None,
    *,
    shell_phase_fn: Callable[[dict[str, Any] | None], str] | None = None,
) -> str | None:
    if (shell_phase_fn or shell_phase)(payload) != "input":
        return None
    if not isinstance(payload, dict):
        return None
    text = payload.get("stdin")
    if text is None:
        text = payload.get("chars")
    if text is None:
        return None
    return str(text)


def shell_output_text(
    payload: dict[str, Any] | None,
    *,
    shell_phase_fn: Callable[[dict[str, Any] | None], str] | None = None,
) -> str | None:
    if (shell_phase_fn or shell_phase)(payload) != "output":
        return None
    if not isinstance(payload, dict):
        return None
    text = payload.get("text")
    if text is None:
        text = payload.get("output_text")
    if text is None:
        return None
    return str(text)


def shell_turn_item(
    payload: dict[str, Any] | None,
    *,
    shell_call_id_fn: Callable[[dict[str, Any] | None], str] | None = None,
) -> dict[str, Any]:
    raw = dict(payload or {})
    call_id = (shell_call_id_fn or shell_call_id)(raw)
    session_id = str(raw.get("session_id") or "").strip()
    item_id = call_id or session_id or "item_shell"
    arguments: dict[str, Any] = {"command": str(raw.get("command") or "")}
    if session_id:
        arguments["session_id"] = session_id
    return {
        "type": "function_call",
        "id": item_id,
        "call_id": call_id or None,
        "name": "shell",
        "arguments": json.dumps(arguments, ensure_ascii=False),
    }


def shell_call_id(payload: dict[str, Any] | None) -> str:
    raw = dict(payload or {})
    call_id = str(raw.get("call_id") or "").strip()
    if call_id:
        return call_id
    lifecycle = raw.get("lifecycle")
    if isinstance(lifecycle, dict):
        return str(lifecycle.get("call_id") or "").strip()
    return ""

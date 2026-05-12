from __future__ import annotations

import json
from typing import Any

from cli.agent_cli import app_server_protocol_projection_helpers_runtime as projection_helpers
from cli.agent_cli import app_server_protocol_pure_helpers_runtime as pure_helpers
from cli.agent_cli.app_server_payloads import reference_thread_item_payload


def emit_turn_item_delta_notification(
    server: Any,
    *,
    thread_id: str,
    turn_id: str,
    event: dict[str, Any],
    item: dict[str, Any],
    item_text_state: dict[str, str],
) -> None:
    item_id = str(item.get("id") or "").strip()
    if not item_id:
        return
    item_type = str(item.get("type") or "").strip()
    current_text = pure_helpers.turn_stream_item_text(event, item)
    if not current_text:
        return
    previous_text = str(item_text_state.get(item_id) or "")
    delta = pure_helpers.text_delta(previous_text, current_text)
    item_text_state[item_id] = current_text
    if not delta:
        return
    if item_type == "commandExecution":
        server._emit_notification(
            "item/commandExecution/outputDelta",
            {
                "threadId": thread_id,
                "turnId": turn_id,
                "itemId": item_id,
                "delta": delta,
            },
        )
        return
    if item_type == "agentMessage":
        server._emit_notification(
            "item/agentMessage/delta",
            {
                "threadId": thread_id,
                "turnId": turn_id,
                "itemId": item_id,
                "delta": delta,
            },
        )
        return
    if item_type == "plan":
        server._emit_notification(
            "item/plan/delta",
            {
                "threadId": thread_id,
                "turnId": turn_id,
                "itemId": item_id,
                "delta": delta,
            },
        )
        return
    if item_type == "reasoning":
        server._emit_notification(
            "item/reasoning/textDelta",
            {
                "threadId": thread_id,
                "turnId": turn_id,
                "itemId": item_id,
                "delta": delta,
                "contentIndex": 0,
            },
        )


def emit_turn_plan_updated_notification(
    server: Any,
    *,
    thread_id: str,
    turn_id: str,
    item: dict[str, Any],
    plan_state: dict[str, str],
) -> None:
    payload = projection_helpers.reference_turn_plan_payload(
        thread_id=thread_id,
        turn_id=turn_id,
        item=item,
    )
    if payload is None:
        return
    try:
        signature = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except TypeError:
        signature = repr(payload)
    if plan_state.get("latest") == signature:
        return
    plan_state["latest"] = signature
    server._emit_notification("turn/plan/updated", payload)


def emit_turn_stream_event(
    server: Any,
    *,
    thread_id: str,
    turn_id: str,
    event: dict[str, Any],
    item_text_state: dict[str, str],
    plan_state: dict[str, str],
) -> None:
    event_type = str(event.get("type") or "").strip()
    if event_type in {"turn.started", "turn.completed"}:
        return
    raw_item = event.get("item")
    if not isinstance(raw_item, dict):
        return
    item = reference_thread_item_payload(raw_item)
    item_id = str(item.get("id") or "").strip()
    if event_type == "item.started":
        server._emit_notification(
            "item/started",
            {
                "threadId": thread_id,
                "turnId": turn_id,
                "item": item,
            },
        )
        if item_id:
            if str(item.get("type") or "").strip() == "plan":
                emit_turn_item_delta_notification(
                    server,
                    thread_id=thread_id,
                    turn_id=turn_id,
                    event=event,
                    item=item,
                    item_text_state=item_text_state,
                )
            else:
                text = pure_helpers.turn_stream_item_text(event, item)
                if text:
                    item_text_state[item_id] = text
        emit_turn_plan_updated_notification(
            server,
            thread_id=thread_id,
            turn_id=turn_id,
            item=item,
            plan_state=plan_state,
        )
        return
    if event_type == "item.updated":
        emit_turn_item_delta_notification(
            server,
            thread_id=thread_id,
            turn_id=turn_id,
            event=event,
            item=item,
            item_text_state=item_text_state,
        )
        emit_turn_plan_updated_notification(
            server,
            thread_id=thread_id,
            turn_id=turn_id,
            item=item,
            plan_state=plan_state,
        )
        return
    if event_type != "item.completed":
        return
    if item_id and str(item.get("type") or "").strip() == "plan":
        emit_turn_item_delta_notification(
            server,
            thread_id=thread_id,
            turn_id=turn_id,
            event=event,
            item=item,
            item_text_state=item_text_state,
        )
    elif item_id:
        text = pure_helpers.turn_stream_item_text(event, item)
        if text:
            item_text_state[item_id] = text
    server._emit_notification(
        "item/completed",
        {
            "threadId": thread_id,
            "turnId": turn_id,
            "item": item,
        },
    )
    emit_turn_plan_updated_notification(
        server,
        thread_id=thread_id,
        turn_id=turn_id,
        item=item,
        plan_state=plan_state,
    )


def emit_raw_response_item_completed_notifications(
    server: Any,
    *,
    thread_id: str,
    turn_id: str,
    response: Any,
) -> None:
    for raw_item in list(getattr(response, "response_items", []) or []):
        item_payload = pure_helpers.raw_response_item_payload(raw_item)
        if item_payload is None:
            continue
        server._emit_notification(
            "rawResponseItem/completed",
            {
                "threadId": thread_id,
                "turnId": turn_id,
                "item": item_payload,
            },
        )


__all__ = [
    "emit_raw_response_item_completed_notifications",
    "emit_turn_item_delta_notification",
    "emit_turn_plan_updated_notification",
    "emit_turn_stream_event",
]

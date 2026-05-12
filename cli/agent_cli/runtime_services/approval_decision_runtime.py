from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli.models import generic_tool_call_item_events


def gateway_item_payload(item: Any) -> Dict[str, Any]:
    if item is None:
        return {}
    to_dict = getattr(item, "to_dict", None)
    if callable(to_dict):
        value = to_dict()
        return dict(value) if isinstance(value, dict) else {}
    if isinstance(item, dict):
        return dict(item)
    return {}


def approval_decision_turn_events(
    approval_ticket: Any,
    action_request: Any,
    action_result: Any,
    *,
    item_index_start: int = 0,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    approval_payload = gateway_item_payload(approval_ticket)
    action_request_payload = gateway_item_payload(action_request)
    action_result_payload = gateway_item_payload(action_result)
    approval_id = str(approval_payload.get("approval_id") or "").strip()
    action_type = str(action_request_payload.get("action_type") or "").strip()
    decision_status = str(approval_payload.get("status") or "").strip().lower()
    decision_ok = decision_status in {"approved", "rejected"}

    item_events: List[Dict[str, Any]] = []
    next_index = int(item_index_start)
    decision_item_events = generic_tool_call_item_events(
        tool_name="approval_decision",
        arguments={
            "approval_id": approval_id,
            "decision": decision_status,
            "decision_type": str(approval_payload.get("decision_type") or "").strip() or None,
            "action_type": action_type or None,
        },
        ok=decision_ok,
        summary=f"{decision_status or 'decided'} {approval_id}".strip(),
        structured_content={
            "approval_ticket": approval_payload,
            "action_request": action_request_payload,
            "action_result": action_result_payload or None,
        },
        item_id=f"item_{next_index}",
    )
    item_events.extend(decision_item_events)
    next_index += 1

    action_ok = bool(action_result_payload.get("ok")) if action_result_payload else False
    action_summary = str(action_result_payload.get("summary") or action_type or "gateway action").strip()
    if action_result_payload:
        execution_item_events = generic_tool_call_item_events(
            tool_name="gateway_action_execute",
            arguments={
                "approval_id": approval_id or None,
                "action_id": str(action_request_payload.get("action_id") or "").strip() or None,
                "action_type": action_type or None,
            },
            ok=action_ok,
            summary=action_summary,
            structured_content={
                "approval_ticket": approval_payload,
                "action_request": action_request_payload,
                "action_result": action_result_payload,
            },
            item_id=f"item_{next_index}",
        )
        item_events.extend(execution_item_events)

    turn_events: List[Dict[str, Any]] = [
        {"type": "turn.started"},
        *[dict(item) for item in item_events],
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "output_tokens": 0,
            },
        },
    ]
    return turn_events, item_events

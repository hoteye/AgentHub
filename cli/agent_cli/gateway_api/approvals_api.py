from __future__ import annotations

from typing import Any, Dict

from cli.agent_cli.approval_continuation_projection_runtime import (
    camel_case_continuation_fields,
    continuation_fields,
)
from cli.agent_cli.gateway_core import ApprovalTicket


def _gateway_item_to_dict(item: Any) -> Dict[str, Any]:
    if item is None:
        return {}
    to_dict = getattr(item, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        return dict(payload) if isinstance(payload, dict) else {}
    if isinstance(item, dict):
        return dict(item)
    if all(hasattr(item, name) for name in ("name", "ok", "summary", "payload")):
        return {
            "name": str(getattr(item, "name", "") or ""),
            "ok": bool(getattr(item, "ok", False)),
            "summary": str(getattr(item, "summary", "") or ""),
            "payload": dict(getattr(item, "payload", {}) or {}),
        }
    if hasattr(item, "__dict__"):
        value = dict(getattr(item, "__dict__", {}) or {})
        return value if isinstance(value, dict) else {}
    return {}


def approval_ticket_to_response(ticket: ApprovalTicket) -> Dict[str, Any]:
    return {
        "approval_id": ticket.approval_id,
        "action_id": ticket.action_id,
        "status": ticket.status,
        "summary": ticket.summary,
        "reason": ticket.reason,
        "requested_at": ticket.requested_at,
        "requested_by": ticket.requested_by,
        "decision_at": ticket.decision_at,
        "decision_by": ticket.decision_by,
        "decision_note": ticket.decision_note,
        "available_decisions": [dict(item) for item in list(ticket.available_decisions or []) if isinstance(item, dict)],
        "session_cache_keys": list(ticket.session_cache_keys or []),
        "proposed_rule": dict(ticket.proposed_rule or {}) if isinstance(ticket.proposed_rule, dict) else None,
        "grant_root": ticket.grant_root,
        "decision_type": ticket.decision_type,
        "decision_payload": dict(ticket.decision_payload or {}),
    }


def approval_decision_result_to_snake_case(result: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(result or {})
    approval_ticket = _gateway_item_to_dict(payload.get("approval_ticket"))
    action_request = _gateway_item_to_dict(payload.get("action_request"))
    action_result = _gateway_item_to_dict(payload.get("action_result"))
    tool_events = [_gateway_item_to_dict(item) for item in list(payload.get("tool_events") or [])]
    tool_events = [item for item in tool_events if isinstance(item, dict) and (item or {}).get("name")]
    if not tool_events:
        synthesized = _synth_approval_tool_event(
            approval_ticket=approval_ticket,
            action_request=action_request,
            action_result=action_result,
        )
        if synthesized is not None:
            tool_events = [synthesized]

    item_events = [dict(item) for item in list(payload.get("item_events") or []) if isinstance(item, dict)]
    if not item_events and tool_events:
        item_events = _synth_item_events_from_tool_event(tool_events[0])

    turn_events = [dict(item) for item in list(payload.get("turn_events") or []) if isinstance(item, dict)]
    if not turn_events and item_events:
        turn_events = _synth_turn_events(item_events)

    continuation = continuation_fields(
        continuation=payload.get("continuation"),
        tool_events=tool_events,
    )
    return {
        "approval_ticket": approval_ticket,
        "action_request": action_request,
        "action_result": action_result,
        "audit_records": [_gateway_item_to_dict(item) for item in list(payload.get("audit_records") or [])],
        "tool_events": tool_events,
        "item_events": item_events,
        "turn_events": turn_events,
        **continuation,
    }


def approval_decision_result_to_camel_case(result: Dict[str, Any]) -> Dict[str, Any]:
    payload = approval_decision_result_to_snake_case(result)
    continuation = camel_case_continuation_fields(
        {
            "continuation": payload.get("continuation"),
            "continuation_attempted": payload.get("continuation_attempted"),
            "continuation_status": payload.get("continuation_status"),
        }
    )
    return {
        "approvalTicket": dict(payload.get("approval_ticket") or {}),
        "actionRequest": dict(payload.get("action_request") or {}),
        "actionResult": dict(payload.get("action_result") or {}),
        "auditRecords": [dict(item) for item in list(payload.get("audit_records") or []) if isinstance(item, dict)],
        "toolEvents": [dict(item) for item in list(payload.get("tool_events") or []) if isinstance(item, dict)],
        "itemEvents": [dict(item) for item in list(payload.get("item_events") or []) if isinstance(item, dict)],
        "turnEvents": [dict(item) for item in list(payload.get("turn_events") or []) if isinstance(item, dict)],
        **continuation,
    }


def _synth_approval_tool_event(
    *,
    approval_ticket: Dict[str, Any],
    action_request: Dict[str, Any],
    action_result: Dict[str, Any],
) -> Dict[str, Any] | None:
    approval_id = str(approval_ticket.get("approval_id") or "").strip()
    status = str(approval_ticket.get("status") or "").strip().lower()
    action_type = str(action_request.get("action_type") or "").strip()
    if not approval_id and not status and not action_type:
        return None
    ok = status in {"approved", "rejected"}
    return {
        "name": "approval_decision",
        "ok": ok,
        "summary": f"{status or 'decided'} {approval_id}".strip(),
        "payload": {
            "ok": ok,
            "approval_id": approval_id or None,
            "status": status or None,
            "decision_type": approval_ticket.get("decision_type"),
            "decision_payload": dict(approval_ticket.get("decision_payload") or {}),
            "action_type": action_type or None,
            "approval_ticket": dict(approval_ticket or {}),
            "action_request": dict(action_request or {}),
            "action_result": dict(action_result or {}),
        },
    }


def _synth_item_events_from_tool_event(tool_event: Dict[str, Any]) -> list[Dict[str, Any]]:
    event = dict(tool_event or {})
    tool_name = str(event.get("name") or "").strip() or "approval_decision"
    payload = dict(event.get("payload") or {})
    item = {
        "id": "item_0",
        "type": "mcp_tool_call",
        "status": "completed",
        "tool": tool_name,
        "arguments": {
            "approval_id": str(payload.get("approval_id") or "").strip() or None,
            "status": str(payload.get("status") or "").strip() or None,
            "action_type": str(payload.get("action_type") or "").strip() or None,
        },
        "structured_content": payload,
        "result": {
            "ok": bool(event.get("ok", False)),
            "summary": str(event.get("summary") or ""),
        },
    }
    return [
        {"type": "item.started", "item": {**dict(item), "status": "in_progress"}},
        {"type": "item.completed", "item": item},
    ]


def _synth_turn_events(item_events: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    return [
        {"type": "turn.started"},
        *[dict(item) for item in list(item_events or []) if isinstance(item, dict)],
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "output_tokens": 0,
            },
        },
    ]

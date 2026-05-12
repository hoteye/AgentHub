from __future__ import annotations

from typing import Any, Dict

from cli.agent_cli import approval_contract_runtime
from cli.agent_cli.models import ToolEvent
from cli.agent_cli.runtime_services import approval_decision_runtime


def approval_decision_event(
    approval_ticket: Any,
    action_request: Any,
    *,
    payload_updates: Dict[str, Any] | None = None,
) -> ToolEvent:
    payload = {
        "ok": True,
        "approval_id": approval_ticket.approval_id,
        "status": approval_ticket.status,
        "decision_type": str(getattr(approval_ticket, "decision_type", "") or "").strip() or None,
        "decision_payload": dict(getattr(approval_ticket, "decision_payload", {}) or {}),
        "action_type": action_request.action_type,
        "decision_by": approval_ticket.decision_by,
        "decision_note": approval_ticket.decision_note,
    }
    if payload_updates:
        payload.update(payload_updates)
    return ToolEvent(
        name="approval_decision",
        ok=True,
        summary=(
            f"{approval_ticket.status} "
            f"{approval_contract_runtime.normalize_approval_decision(getattr(approval_ticket, 'decision_type', '') or 'accept').get('type')}"
            f" {approval_ticket.approval_id}"
            if str(getattr(approval_ticket, "decision_type", "") or "").strip()
            else f"{approval_ticket.status} {approval_ticket.approval_id}"
        ),
        payload=payload,
    )


def approval_resolution_response(
    approval_ticket: Any,
    action_request: Any,
    action_result: Any,
    audit_records: list[Any],
    *,
    tool_events: list[ToolEvent] | None = None,
) -> Dict[str, Any]:
    turn_events, item_events = approval_decision_runtime.approval_decision_turn_events(
        approval_ticket,
        action_request,
        action_result,
    )
    response: Dict[str, Any] = {
        "approval_ticket": approval_ticket,
        "action_request": action_request,
        "action_result": action_result,
        "audit_records": audit_records,
        "item_events": item_events,
        "turn_events": turn_events,
    }
    if tool_events is not None:
        response["tool_events"] = tool_events
    return response

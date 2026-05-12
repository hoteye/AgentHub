from __future__ import annotations

from typing import Any, Dict

from cli.agent_cli.gateway_core import create_audit_record


def approval_decision_details(
    approval_ticket: Any,
    *,
    extra_details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    details: Dict[str, Any] = {
        "decided_by": approval_ticket.decision_by,
        "decision_note": approval_ticket.decision_note,
        "decision_type": getattr(approval_ticket, "decision_type", None),
        "decision_payload": dict(getattr(approval_ticket, "decision_payload", {}) or {}),
    }
    if extra_details:
        details.update(extra_details)
    return details


def approval_decision_audit_record(
    approval_ticket: Any,
    action_request: Any,
    *,
    summary: str,
    extra_details: Dict[str, Any] | None = None,
) -> Any:
    return create_audit_record(
        trace_id=approval_ticket.trace_id,
        stage="approval",
        status=approval_ticket.status,
        summary=summary,
        event_id=getattr(action_request, "event_id", None),
        workflow_run_id=getattr(action_request, "workflow_run_id", None),
        action_id=action_request.action_id,
        approval_id=approval_ticket.approval_id,
        details=approval_decision_details(approval_ticket, extra_details=extra_details),
    )


def tool_event_action_result(tool_event: Any, *, action: str) -> Dict[str, Any]:
    return {
        "ok": bool(tool_event.ok),
        "action": action,
        "summary": tool_event.summary,
        "output": dict(tool_event.payload or {}),
    }


def tool_event_execution_audit_record(
    approval_ticket: Any,
    action_request: Any,
    tool_event: Any,
) -> Any:
    return create_audit_record(
        trace_id=approval_ticket.trace_id,
        stage="action_execute",
        status="ok" if tool_event.ok else "failed",
        summary=tool_event.summary,
        event_id=getattr(action_request, "event_id", None),
        workflow_run_id=getattr(action_request, "workflow_run_id", None),
        action_id=action_request.action_id,
        approval_id=approval_ticket.approval_id,
        details={"tool_event": dict(tool_event.payload or {})},
    )

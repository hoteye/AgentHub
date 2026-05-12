from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

from cli.agent_cli.gateway_core import ApprovalTicket
from cli.agent_cli.runtime_services import approval_projection_runtime
from cli.agent_cli.runtime_services import approval_ticket_runtime


def pending_approval_context(runtime: Any, approval_id: str) -> tuple[Any, Any]:
    approval_ticket = runtime.gateway_state_store.get_approval_ticket(approval_id)
    if approval_ticket is None:
        raise ValueError(f"unknown approval_id: {approval_id}")
    if str(approval_ticket.status or "").strip().lower() != "pending":
        raise ValueError(f"approval already decided: {approval_ticket.approval_id}")
    action_request = runtime.gateway_state_store.get_action_request(approval_ticket.action_id)
    if action_request is None:
        raise ValueError(f"missing action_request for approval_id: {approval_id}")
    return approval_ticket, action_request


def decided_approval_ticket(
    approval_ticket: Any,
    *,
    decision: Any,
    decided_by: str,
    decision_note: str,
) -> ApprovalTicket:
    return approval_ticket_runtime.decided_approval_ticket(
        approval_ticket,
        decision=decision,
        decided_by=decided_by,
        decision_note=decision_note,
        decision_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    )


def append_audit_records(runtime: Any, audit_records: Iterable[Any]) -> None:
    for item in audit_records:
        runtime.append_gateway_audit_record(item)


def decision_tool_events(
    updated_ticket: Any,
    action_request: Any,
    *,
    payload_updates: Dict[str, Any] | None = None,
    extra_events: Iterable[Any] | None = None,
) -> List[Any]:
    tool_events = [
        approval_projection_runtime.approval_decision_event(
            updated_ticket,
            action_request,
            payload_updates=payload_updates,
        )
    ]
    for item in list(extra_events or []):
        if item is not None:
            tool_events.append(item)
    return tool_events


def approval_resolution_response(
    updated_ticket: Any,
    action_request: Any,
    action_result: Dict[str, Any] | None,
    audit_records: List[Any],
    *,
    payload_updates: Dict[str, Any] | None = None,
    extra_events: Iterable[Any] | None = None,
) -> Dict[str, Any]:
    tool_events = decision_tool_events(
        updated_ticket,
        action_request,
        payload_updates=payload_updates,
        extra_events=extra_events,
    )
    return approval_projection_runtime.approval_resolution_response(
        updated_ticket,
        action_request,
        action_result,
        audit_records,
        tool_events=tool_events,
    )


def background_teammate_audit_details(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "task": str(payload.get("task") or "").strip(),
        "provider": str(payload.get("provider") or "").strip() or None,
        "model": str(payload.get("model") or "").strip() or None,
        "sandbox_mode": str(payload.get("sandbox_mode") or "").strip() or None,
        "timeout_seconds": payload.get("timeout_seconds"),
    }


def background_teammate_enqueue_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "task": str(payload.get("task") or "").strip(),
        "provider": str(payload.get("provider") or "").strip(),
        "model": str(payload.get("model") or "").strip(),
        "reasoning_effort": str(payload.get("reasoning_effort") or "").strip(),
        "cwd": str(payload.get("cwd") or "").strip(),
        "approval_policy": str(payload.get("approval_policy") or "never").strip() or "never",
        "sandbox_mode": str(payload.get("sandbox_mode") or "read-only").strip() or "read-only",
        "allowed_paths": list(payload.get("allowed_paths") or []),
        "blocked_paths": list(payload.get("blocked_paths") or []),
        "timeout_seconds": payload.get("timeout_seconds"),
    }


def background_teammate_enqueue_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "reason": "slash_command",
        "provider_name": str(payload.get("provider") or "").strip(),
        "model": str(payload.get("model") or "").strip(),
        "extra": {"reasoning_effort": str(payload.get("reasoning_effort") or "").strip()},
    }


def shell_payload_updates(runtime: Any, action_request: Any) -> Dict[str, Any]:
    return {
        "command": str((action_request.payload or {}).get("command") or "").strip() or None,
        "exec_mode": runtime._normalize_shell_exec_mode(
            str((action_request.payload or {}).get("exec_mode") or "exec_once")
        )
    }


def background_teammate_payload_updates(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"sandbox_mode": str(payload.get("sandbox_mode") or "").strip() or None}

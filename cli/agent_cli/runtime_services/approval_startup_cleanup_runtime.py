from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from cli.agent_cli.gateway_core import create_audit_record
from cli.agent_cli.runtime_services import approval_ticket_runtime


DEFAULT_STALE_PENDING_APPROVAL_SECONDS = 30 * 60
STALE_PENDING_APPROVAL_DECISION_NOTE = (
    "auto-declined stale pending approval on startup; action was not executed"
)


def _parse_iso_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _now_utc(now: datetime | None = None) -> datetime:
    candidate = now or datetime.now(timezone.utc)
    if candidate.tzinfo is None:
        return candidate.replace(tzinfo=timezone.utc)
    return candidate.astimezone(timezone.utc)


def _is_stale_pending_approval(ticket: Any, *, now: datetime, stale_after_seconds: int) -> bool:
    if str(getattr(ticket, "status", "") or "").strip().lower() != "pending":
        return False
    requested_at = _parse_iso_datetime(getattr(ticket, "requested_at", None))
    if requested_at is None:
        return False
    return (now - requested_at).total_seconds() >= max(0, int(stale_after_seconds))


def _approval_cleanup_audit_record(ticket: Any, action_request: Any | None) -> Any:
    return create_audit_record(
        trace_id=str(getattr(ticket, "trace_id", "") or "").strip(),
        stage="approval",
        status="rejected",
        summary="rejected stale pending approval on startup",
        event_id=getattr(action_request, "event_id", None) if action_request is not None else None,
        workflow_run_id=getattr(action_request, "workflow_run_id", None) if action_request is not None else None,
        action_id=str(getattr(ticket, "action_id", "") or "").strip() or None,
        approval_id=str(getattr(ticket, "approval_id", "") or "").strip() or None,
        details={
            "decided_by": "system_startup",
            "decision_note": STALE_PENDING_APPROVAL_DECISION_NOTE,
            "decision_type": "decline",
            "decision_payload": {"type": "decline"},
            "decision_outcome": "stale_declined",
            "execution_skipped": True,
            "cleanup_reason": "stale_pending_approval_on_startup",
        },
    )


def _decline_stale_ticket(runtime: Any, ticket: Any, *, decision_at: str) -> Any:
    updated = approval_ticket_runtime.decided_approval_ticket(
        ticket,
        decision="decline",
        decided_by="system_startup",
        decision_note=STALE_PENDING_APPROVAL_DECISION_NOTE,
        decision_at=decision_at,
    )
    metadata = dict(getattr(updated, "metadata", {}) or {})
    metadata["startup_cleanup"] = {
        "reason": "stale_pending_approval",
        "action_executed": False,
        "decision_at": decision_at,
    }
    updated = replace(updated, metadata=metadata)
    runtime.save_gateway_approval_ticket(updated)
    return updated


def decline_stale_pending_approvals_on_startup(
    runtime: Any,
    *,
    stale_after_seconds: int = DEFAULT_STALE_PENDING_APPROVAL_SECONDS,
    now: datetime | None = None,
) -> list[Any]:
    list_approval_tickets = getattr(runtime, "list_approval_tickets", None)
    if not callable(list_approval_tickets):
        return []
    try:
        pending = list(list_approval_tickets(limit=1000, status="pending") or [])
    except Exception:
        return []
    current = _now_utc(now)
    decision_at = current.replace(microsecond=0).isoformat()
    stale_tickets = [
        ticket
        for ticket in pending
        if _is_stale_pending_approval(
            ticket,
            now=current,
            stale_after_seconds=stale_after_seconds,
        )
    ]
    updated_tickets: list[Any] = []
    state_store = getattr(runtime, "gateway_state_store", None)
    get_action_request = getattr(state_store, "get_action_request", None)
    for ticket in stale_tickets:
        action_request = None
        if callable(get_action_request):
            try:
                action_request = get_action_request(str(getattr(ticket, "action_id", "") or ""))
            except Exception:
                action_request = None
        updated = _decline_stale_ticket(runtime, ticket, decision_at=decision_at)
        append_audit_record = getattr(runtime, "append_gateway_audit_record", None)
        if callable(append_audit_record):
            try:
                append_audit_record(_approval_cleanup_audit_record(updated, action_request))
            except Exception:
                pass
        updated_tickets.append(updated)
    return updated_tickets

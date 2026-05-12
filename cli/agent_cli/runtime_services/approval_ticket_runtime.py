from __future__ import annotations

from typing import Any

from cli.agent_cli import approval_contract_runtime
from cli.agent_cli.gateway_core import ApprovalTicket


def decided_approval_ticket(
    approval_ticket: Any,
    *,
    decision: Any,
    decided_by: str,
    decision_note: str,
    decision_at: str,
) -> ApprovalTicket:
    normalized_decision = approval_contract_runtime.normalize_approval_decision(
        decision,
        fallback_proposed_rule=(
            dict(getattr(approval_ticket, "proposed_rule", {}) or {})
            if isinstance(getattr(approval_ticket, "proposed_rule", None), dict)
            else None
        ),
    )
    approved = approval_contract_runtime.is_approval_accepting(normalized_decision)
    return ApprovalTicket(
        approval_id=approval_ticket.approval_id,
        action_id=approval_ticket.action_id,
        trace_id=approval_ticket.trace_id,
        status="approved" if approved else "rejected",
        requested_at=approval_ticket.requested_at,
        requested_by=approval_ticket.requested_by,
        evidence_refs=list(approval_ticket.evidence_refs),
        reason=approval_ticket.reason,
        summary=approval_ticket.summary,
        decision_at=decision_at,
        decision_by=str(decided_by or "").strip(),
        decision_note=str(decision_note or "").strip() or None,
        available_decisions=list(getattr(approval_ticket, "available_decisions", []) or []),
        session_cache_keys=list(getattr(approval_ticket, "session_cache_keys", []) or []),
        proposed_rule=(
            dict(getattr(approval_ticket, "proposed_rule", {}) or {})
            if isinstance(getattr(approval_ticket, "proposed_rule", None), dict)
            else None
        ),
        grant_root=str(getattr(approval_ticket, "grant_root", "") or "").strip() or None,
        decision_type=str(normalized_decision.get("type") or "").strip() or None,
        decision_payload=dict(normalized_decision),
        metadata=dict(approval_ticket.metadata or {}),
    )


def merge_approval_evidence_refs(approval_ticket: ApprovalTicket, artifact_refs: list[str] | None) -> ApprovalTicket:
    merged_refs = list(dict.fromkeys([*approval_ticket.evidence_refs, *(artifact_refs or [])]))
    if merged_refs == list(approval_ticket.evidence_refs):
        return approval_ticket
    return ApprovalTicket(
        approval_id=approval_ticket.approval_id,
        action_id=approval_ticket.action_id,
        trace_id=approval_ticket.trace_id,
        status=approval_ticket.status,
        requested_at=approval_ticket.requested_at,
        requested_by=approval_ticket.requested_by,
        evidence_refs=merged_refs,
        reason=approval_ticket.reason,
        summary=approval_ticket.summary,
        decision_at=approval_ticket.decision_at,
        decision_by=approval_ticket.decision_by,
        decision_note=approval_ticket.decision_note,
        available_decisions=list(approval_ticket.available_decisions),
        session_cache_keys=list(approval_ticket.session_cache_keys),
        proposed_rule=dict(approval_ticket.proposed_rule) if isinstance(approval_ticket.proposed_rule, dict) else None,
        grant_root=approval_ticket.grant_root,
        decision_type=approval_ticket.decision_type,
        decision_payload=dict(approval_ticket.decision_payload or {}),
        metadata=dict(approval_ticket.metadata or {}),
    )

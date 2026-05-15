from __future__ import annotations

from typing import Any

from cli.agent_cli import approval_contract_runtime, runtime_exec_policy_rules
from cli.agent_cli.runtime_services import approval_resolution_helpers_runtime


def pending_approval_context(runtime: Any, approval_id: str) -> tuple[Any, Any]:
    return approval_resolution_helpers_runtime.pending_approval_context(runtime, approval_id)


def decided_approval_ticket(
    approval_ticket: Any,
    *,
    decision: Any,
    decided_by: str,
    decision_note: str,
) -> Any:
    return approval_resolution_helpers_runtime.decided_approval_ticket(
        approval_ticket,
        decision=decision,
        decided_by=decided_by,
        decision_note=decision_note,
    )


def normalized_approval_decision(
    approval_ticket: Any,
    *,
    approved: bool | None = None,
    decision: Any = None,
) -> dict[str, Any]:
    resolved_decision = decision
    if resolved_decision is None:
        resolved_decision = (
            approval_contract_runtime.APPROVAL_DECISION_ACCEPT
            if bool(approved)
            else approval_contract_runtime.APPROVAL_DECISION_DECLINE
        )
    return approval_contract_runtime.merge_available_decision(
        available_decisions=getattr(approval_ticket, "available_decisions", None),
        decision=resolved_decision,
        fallback_proposed_rule=(
            dict(getattr(approval_ticket, "proposed_rule", {}) or {})
            if isinstance(getattr(approval_ticket, "proposed_rule", None), dict)
            else None
        ),
    )


def store_session_approval(runtime: Any, approval_ticket: Any, *, decision: dict[str, Any]) -> None:
    approval_contract_runtime.store_session_approval(
        runtime,
        session_cache_keys=list(getattr(approval_ticket, "session_cache_keys", []) or []),
        grant_root=str(getattr(approval_ticket, "grant_root", "") or "").strip() or None,
        decision=decision,
    )


def persist_exec_policy_amendment(
    runtime: Any,
    action_request: Any,
    *,
    decision: dict[str, Any],
) -> dict[str, Any] | None:
    if (
        str(decision.get("type") or "").strip()
        != approval_contract_runtime.APPROVAL_DECISION_ACCEPT_WITH_EXECPOLICY_AMENDMENT
    ):
        return None
    proposed_rule = approval_contract_runtime.approval_execpolicy_amendment_rule(
        dict(decision.get("proposed_rule") or {})
        if isinstance(decision.get("proposed_rule"), dict)
        else None
    )
    if proposed_rule is None:
        return None
    payload = dict(getattr(action_request, "payload", None) or {})
    source_metadata = dict(proposed_rule.get("source_metadata") or {})
    source_metadata.update(
        {
            "action_id": str(getattr(action_request, "action_id", "") or "").strip() or None,
            "action_type": str(getattr(action_request, "action_type", "") or "").strip() or None,
            "trace_id": str(getattr(action_request, "trace_id", "") or "").strip() or None,
        }
    )
    normalized_rule = runtime_exec_policy_rules.append_runtime_exec_policy_rule(
        {
            **dict(proposed_rule),
            "decision": "allow",
            "source": str(proposed_rule.get("source") or "user").strip() or "user",
            "justification": str(
                proposed_rule.get("justification") or "approved via cli approval"
            ).strip(),
            "source_metadata": source_metadata,
        },
        cwd=str(payload.get("cwd") or "").strip() or getattr(runtime, "cwd", None),
    )
    return normalized_rule.to_dict()


def gateway_decision_outcome_from_approval_ticket(approval_ticket: Any) -> str:
    status = str(getattr(approval_ticket, "status", "") or "").strip().lower()
    note = str(getattr(approval_ticket, "decision_note", "") or "").strip().lower()
    if status == "approved":
        return "approved"
    if "timeout" in note:
        return "timed_out"
    if "expired" in note:
        return "expired"
    if status == "rejected":
        return "rejected"
    return status or "rejected"


def project_gateway_decision_outcome_into_approval_audit(
    audit_records: list[Any],
    *,
    decision_outcome: str,
    approved: bool,
) -> None:
    for audit_record in list(audit_records or []):
        if str(getattr(audit_record, "stage", "")).strip() != "approval":
            continue
        details = getattr(audit_record, "details", None)
        if not isinstance(details, dict):
            continue
        details["decision_outcome"] = decision_outcome
        details["execution_skipped"] = not approved
        break

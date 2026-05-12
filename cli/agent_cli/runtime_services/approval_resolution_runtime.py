from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from cli.agent_cli.runtime_services import approval_resolution_runtime_helpers as _helpers

from cli.agent_cli.runtime_services.approval_resolution_runtime_helpers import *


def _normalized_gateway_outcome(outcome: str) -> str:
    token = str(outcome or "").strip().lower()
    if token in {"approve", "approved", "ok", "allow"}:
        return "approved"
    if token in {"reject", "rejected", "deny", "denied"}:
        return "rejected"
    if token in {"timeout", "timed_out", "timed-out"}:
        return "timed_out"
    if token in {"expired", "expire"}:
        return "expired"
    raise ValueError(f"unsupported gateway approval outcome: {outcome}")


_OUTCOME_REJECTION_NOTES: dict[str, str] = {
    "timed_out": "approval timeout",
    "expired": "approval expired",
}

_OUTCOME_REASON_CODES: dict[str, str] = {
    "pending": "approval.pending",
    "approved": "approval.approved",
    "rejected": "approval.rejected",
    "timed_out": "approval.timed_out",
    "expired": "approval.expired",
}

_OBSERVABILITY_SCHEMA_VERSION = 1
_OBSERVABILITY_LATENCY_BUCKET_FIELD = "approval_latency_bucket"


def _rejection_note_for_outcome(outcome: str) -> str:
    """Provide the stable rejection note that compatibility layers expect."""
    return _OUTCOME_REJECTION_NOTES.get(outcome, "approval rejected")


def _decision_note_for_outcome(outcome: str, note: str, approved: bool) -> str:
    """Coerce a note string while keeping timeout/expired semantics deterministic."""
    sanitized_note = str(note or "").strip()
    if sanitized_note:
        return sanitized_note
    if approved:
        return sanitized_note
    return _rejection_note_for_outcome(outcome)


def _parse_iso_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _latency_bucket_millis(latency_ms: int) -> str:
    if latency_ms < 100:
        return "lt_100ms"
    if latency_ms < 500:
        return "100ms_500ms"
    if latency_ms < 1000:
        return "500ms_1s"
    if latency_ms < 5000:
        return "1s_5s"
    return "ge_5s"


def _gateway_tool_snapshot(response: Dict[str, Any]) -> Dict[str, Any]:
    action_request = response.get("action_request")
    payload = dict(getattr(action_request, "payload", None) or {})
    tool_contract = payload.get("tool_contract")
    if not isinstance(tool_contract, dict):
        tool_contract = {}
    snapshot: Dict[str, Any] = {
        "action_type": str(getattr(action_request, "action_type", "") or "").strip(),
        "connector_key": str(getattr(action_request, "connector_key", "") or "").strip(),
        "plugin_name": str(getattr(action_request, "plugin_name", "") or "").strip(),
        "projected_name": str(payload.get("projected_name") or payload.get("projectedName") or "").strip(),
    }
    for key in (
        "name",
        "server_name",
        "remote_name",
        "source",
        "tool_family",
        "approval_family",
        "approval_scope",
    ):
        value = str(tool_contract.get(key) or "").strip()
        if value:
            snapshot[key] = value
    return snapshot


def _approval_latency_observability(response: Dict[str, Any]) -> Dict[str, Any]:
    ticket = response.get("approval_ticket")
    requested_at = _parse_iso_datetime(getattr(ticket, "requested_at", None))
    decision_at = _parse_iso_datetime(getattr(ticket, "decision_at", None))
    if requested_at is None or decision_at is None:
        return {
            "latency_bucket_field": _OBSERVABILITY_LATENCY_BUCKET_FIELD,
            "latency_bucket": "unknown",
        }
    delta_ms = int(max((decision_at - requested_at).total_seconds(), 0.0) * 1000)
    return {
        "latency_bucket_field": _OBSERVABILITY_LATENCY_BUCKET_FIELD,
        "latency_bucket": _latency_bucket_millis(delta_ms),
        "latency_ms": delta_ms,
    }


def _project_gateway_decision_outcome_into_approval_audit(
    response: Dict[str, Any],
    *,
    decision_outcome: str,
    approved: bool,
) -> None:
    reason_codes = dict(_OUTCOME_REASON_CODES)
    reason_code = reason_codes.get(decision_outcome, reason_codes["rejected"])
    terminal_event = "action.executed" if approved else "gateway.action.skipped"
    decision_trace = [
        "approval.requested",
        f"approval.{decision_outcome}",
        terminal_event,
    ]
    latency_observability = _approval_latency_observability(response)
    tool_snapshot = _gateway_tool_snapshot(response)
    for audit_record in list(response.get("audit_records") or []):
        if str(getattr(audit_record, "stage", "")).strip() != "approval":
            continue
        details = getattr(audit_record, "details", None)
        if not isinstance(details, dict):
            continue
        details["schema_version"] = _OBSERVABILITY_SCHEMA_VERSION
        details["decision_outcome"] = decision_outcome
        details["execution_skipped"] = not approved
        details["reason_codes"] = reason_codes
        details["reason_code"] = reason_code
        details["decision_trace"] = decision_trace
        details["latency_bucket_field"] = latency_observability.get(
            "latency_bucket_field",
            _OBSERVABILITY_LATENCY_BUCKET_FIELD,
        )
        details["latency_bucket"] = latency_observability.get("latency_bucket")
        if "latency_ms" in latency_observability:
            details["latency_ms"] = latency_observability["latency_ms"]
        details["tool_snapshot"] = tool_snapshot
        details["observability"] = {
            "schema_version": _OBSERVABILITY_SCHEMA_VERSION,
            "reason_codes": reason_codes,
            "reason_code": reason_code,
            "decision_trace": list(decision_trace),
            "latency_bucket_field": details["latency_bucket_field"],
            "latency_bucket": details["latency_bucket"],
            **({"latency_ms": details["latency_ms"]} if "latency_ms" in details else {}),
            "tool_snapshot": dict(tool_snapshot),
        }
        break


def decide_gateway_approval_with_outcome(
    runtime: Any,
    approval_id: str,
    *,
    outcome: str,
    decided_by: str,
    decision_note: str = "",
    github_action_artifact_refs_fn: Any = None,
    find_github_workflow_run_fn: Any = None,
) -> Dict[str, Any]:
    normalized = _normalized_gateway_outcome(outcome)
    approved = normalized == "approved"
    note = _decision_note_for_outcome(normalized, decision_note, approved)
    # timeout/expired paths remain "rejected" so tickets and audits keep their legacy status.

    kwargs: Dict[str, Any] = {}
    if github_action_artifact_refs_fn is not None:
        kwargs["github_action_artifact_refs_fn"] = github_action_artifact_refs_fn
    if find_github_workflow_run_fn is not None:
        kwargs["find_github_workflow_run_fn"] = find_github_workflow_run_fn

    response = _helpers.decide_gateway_approval(
        runtime,
        approval_id,
        approved=approved,
        decided_by=decided_by,
        decision_note=note,
        **kwargs,
    )
    _project_gateway_decision_outcome_into_approval_audit(
        response,
        decision_outcome=normalized,
        approved=approved,
    )
    response["decision_outcome"] = normalized
    return response


def decide_gateway_approval_timeout(
    runtime: Any,
    approval_id: str,
    *,
    decided_by: str = "system",
    decision_note: str = "",
    github_action_artifact_refs_fn: Any = None,
    find_github_workflow_run_fn: Any = None,
) -> Dict[str, Any]:
    return decide_gateway_approval_with_outcome(
        runtime,
        approval_id,
        outcome="timeout",
        decided_by=decided_by,
        decision_note=decision_note,
        github_action_artifact_refs_fn=github_action_artifact_refs_fn,
        find_github_workflow_run_fn=find_github_workflow_run_fn,
    )


def decide_gateway_approval_expired(
    runtime: Any,
    approval_id: str,
    *,
    decided_by: str = "system",
    decision_note: str = "",
    github_action_artifact_refs_fn: Any = None,
    find_github_workflow_run_fn: Any = None,
) -> Dict[str, Any]:
    return decide_gateway_approval_with_outcome(
        runtime,
        approval_id,
        outcome="expired",
        decided_by=decided_by,
        decision_note=decision_note,
        github_action_artifact_refs_fn=github_action_artifact_refs_fn,
        find_github_workflow_run_fn=find_github_workflow_run_fn,
    )

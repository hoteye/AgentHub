from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha1
from typing import Any, Dict, Optional

from cli.agent_cli.approval_contract_runtime import generic_available_decisions

from .models import ActionRequest, ApprovalTicket


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _approval_metadata_from_action(action: ActionRequest) -> Dict[str, Any]:
    metadata = dict(action.metadata or {})
    action_policy = dict((action.metadata or {}).get("action_policy") or {})
    causality = dict(metadata.get("causality") or {})
    causality["action_id"] = action.action_id
    if action.event_id:
        causality["event_id"] = action.event_id
    if action.workflow_run_id:
        causality["workflow_run_id"] = action.workflow_run_id

    metadata.setdefault("source_action_type", action.action_type)
    metadata.setdefault("source_connector_key", action.connector_key)
    metadata.setdefault("source_plugin_name", action.plugin_name)
    if action.action_family:
        metadata.setdefault("source_action_family", action.action_family)
    if action.action_class:
        metadata.setdefault("source_action_class", action.action_class)
    if action.approval_policy:
        metadata.setdefault("source_approval_policy", action.approval_policy)
    if action.audit_stage:
        metadata.setdefault("source_audit_stage", action.audit_stage)
    browser_metadata = dict((action.metadata or {}).get("browser") or {})
    if browser_metadata:
        metadata.setdefault("browser", browser_metadata)
        action_kind = str(browser_metadata.get("action_kind") or "").strip()
        command = str(browser_metadata.get("command") or "").strip()
        if action_kind:
            metadata.setdefault("source_browser_action_kind", action_kind)
        if command:
            metadata.setdefault("source_browser_command", command)
    if action.event_id:
        metadata.setdefault("source_event_id", action.event_id)
    if action.workflow_run_id:
        metadata.setdefault("source_workflow_run_id", action.workflow_run_id)
    if action_policy:
        metadata["action_policy"] = action_policy
    metadata["causality"] = causality
    return metadata


def create_approval_ticket(
    action: ActionRequest,
    *,
    requested_by: Optional[str] = None,
    reason: str = "",
    summary: str = "",
    available_decisions: list[dict[str, Any]] | None = None,
    session_cache_keys: list[str] | None = None,
    proposed_rule: dict[str, Any] | None = None,
    grant_root: str | None = None,
) -> ApprovalTicket:
    requested_at = _utc_now_text()
    digest = sha1(f"{action.action_id}|{action.trace_id}|{requested_at}".encode("utf-8")).hexdigest()[:12]
    return ApprovalTicket(
        approval_id=f"approval_{digest}",
        action_id=action.action_id,
        trace_id=action.trace_id,
        status="pending",
        requested_at=requested_at,
        requested_by=str(requested_by or action.requested_by),
        reason=str(reason or ""),
        summary=str(summary or ""),
        evidence_refs=[],
        available_decisions=[dict(item) for item in list(available_decisions or generic_available_decisions()) if isinstance(item, dict)],
        session_cache_keys=[str(item or "").strip() for item in list(session_cache_keys or []) if str(item or "").strip()],
        proposed_rule=dict(proposed_rule) if isinstance(proposed_rule, dict) else None,
        grant_root=str(grant_root or "").strip() or None,
        decision_type=None,
        decision_payload={},
        metadata=_approval_metadata_from_action(action),
    )

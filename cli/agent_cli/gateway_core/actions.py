from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha1
from typing import Any, Dict, Optional

from .models import ActionRequest


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def create_action_request(
    *,
    action_type: str,
    connector_key: str,
    plugin_name: str,
    trace_id: str,
    requested_by: str,
    payload: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    approval_required: Optional[bool] = None,
    action_family: Optional[str] = None,
    action_class: Optional[str] = None,
    approval_policy: Optional[str] = None,
    audit_stage: Optional[str] = None,
    workflow_run_id: Optional[str] = None,
    event_id: Optional[str] = None,
) -> ActionRequest:
    from cli.agent_cli.runtime_action_policy_runtime import evaluate_browser_action_policy

    requested_at = _utc_now_text()
    normalized_payload = dict(payload or {})
    normalized_metadata = dict(metadata or {})
    browser_action_policy = evaluate_browser_action_policy(
        action_type=action_type,
        payload=normalized_payload,
        metadata=normalized_metadata,
    )
    if browser_action_policy is not None:
        browser_action = browser_action_policy["classification"]
        normalized_metadata = browser_action.to_metadata(normalized_metadata)
        normalized_metadata.setdefault(
            "action_policy",
            dict(browser_action_policy.get("action_policy_payload") or {}),
        )
        if action_family is None:
            action_family = browser_action.action_family
        if action_class is None:
            action_class = browser_action.action_class
        if approval_policy is None:
            approval_policy = browser_action.approval_policy
        if audit_stage is None:
            audit_stage = browser_action.audit_stage
        if approval_required is None:
            approval_required = bool(browser_action_policy.get("approval_required"))
    if approval_required is None:
        approval_required = True
    digest = sha1(
        f"{plugin_name}|{connector_key}|{action_type}|{trace_id}|{requested_at}".encode("utf-8")
    ).hexdigest()[:12]
    return ActionRequest(
        action_id=f"action_{digest}",
        action_type=str(action_type or "").strip(),
        connector_key=str(connector_key or "").strip(),
        plugin_name=str(plugin_name or "").strip(),
        trace_id=str(trace_id or "").strip(),
        requested_at=requested_at,
        requested_by=str(requested_by or "").strip(),
        approval_required=bool(approval_required),
        action_family=str(action_family).strip() if action_family is not None else None,
        action_class=str(action_class).strip() if action_class is not None else None,
        approval_policy=str(approval_policy).strip() if approval_policy is not None else None,
        audit_stage=str(audit_stage).strip() if audit_stage is not None else None,
        workflow_run_id=str(workflow_run_id).strip() if workflow_run_id is not None else None,
        event_id=str(event_id).strip() if event_id is not None else None,
        payload=normalized_payload,
        metadata=normalized_metadata,
    )

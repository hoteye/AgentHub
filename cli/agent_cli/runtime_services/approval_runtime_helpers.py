from __future__ import annotations

from typing import Any, Dict

from cli.agent_cli import approval_contract_runtime
from cli.agent_cli.gateway_core import (
    create_action_request,
    create_approval_ticket,
    create_audit_record,
)
from cli.agent_cli.runtime_services.approval_browser_runtime import (
    action_request_details,
    browser_session_contract,
)


def request_gateway_action(
    runtime: Any,
    *,
    action_type: str,
    connector_key: str,
    plugin_name: str,
    request_payload: Dict[str, Any],
    requested_by: str,
    trace_id: str,
    event_id: str | None = None,
    workflow_run_id: str | None = None,
    approval_required: bool | None = None,
    approval_summary: str = "",
    approval_reason: str = "",
    metadata: Dict[str, Any] | None = None,
    available_decisions: list[dict[str, Any]] | None = None,
    session_cache_keys: list[str] | None = None,
    proposed_rule: dict[str, Any] | None = None,
    grant_root: str | None = None,
) -> Dict[str, Any]:
    effective_metadata = dict(metadata or {})
    effective_available_decisions = (
        [dict(item) for item in list(available_decisions or []) if isinstance(item, dict)]
        if available_decisions is not None
        else None
    )
    effective_session_cache_keys = [
        str(item or "").strip()
        for item in list(session_cache_keys or [])
        if str(item or "").strip()
    ] or None
    effective_approval_required = approval_required
    normalized_action_type = str(action_type or "").strip().lower()
    if normalized_action_type.startswith("browser."):
        browser_contract = browser_session_contract(action_type, request_payload)
        browser_metadata = dict(effective_metadata.get("browser") or {})
        if browser_contract.get("host"):
            browser_metadata.setdefault("host", str(browser_contract["host"]))
        if browser_metadata:
            effective_metadata["browser"] = browser_metadata
        if effective_available_decisions is None and bool(browser_contract.get("allow_for_session")):
            effective_available_decisions = approval_contract_runtime.browser_available_decisions(
                allow_for_session=True,
            )
        if effective_session_cache_keys is None:
            candidate_keys = [
                str(item or "").strip()
                for item in list(browser_contract.get("session_cache_keys") or [])
                if str(item or "").strip()
            ]
            effective_session_cache_keys = candidate_keys or None
        if (
            effective_approval_required is not False
            and approval_contract_runtime.session_approval_is_cached(
                runtime,
                session_cache_keys=effective_session_cache_keys,
            )
        ):
            effective_approval_required = False
    action_request = create_action_request(
        action_type=action_type,
        connector_key=connector_key,
        plugin_name=plugin_name,
        trace_id=trace_id,
        requested_by=requested_by,
        payload=request_payload,
        metadata=effective_metadata,
        approval_required=effective_approval_required,
        workflow_run_id=workflow_run_id,
        event_id=event_id,
    )
    effective_approval_required = bool(action_request.approval_required)
    runtime.save_gateway_action_request(action_request)
    audit_records = [
        create_audit_record(
            trace_id=trace_id,
            stage="action_request",
            status="pending" if effective_approval_required else "ready",
            summary=f"created action request {action_type}",
            event_id=event_id,
            workflow_run_id=workflow_run_id,
            action_id=action_request.action_id,
            details=action_request_details(action_request),
        )
    ]
    approval_ticket = None
    if effective_approval_required:
        approval_ticket = create_approval_ticket(
            action_request,
            requested_by=requested_by,
            reason=approval_reason,
            summary=approval_summary or f"approval required for {action_type}",
            available_decisions=effective_available_decisions,
            session_cache_keys=effective_session_cache_keys,
            proposed_rule=proposed_rule,
            grant_root=grant_root,
        )
        runtime.save_gateway_approval_ticket(approval_ticket)
        audit_records.append(
            create_audit_record(
                trace_id=trace_id,
                stage="approval",
                status="pending",
                summary=approval_ticket.summary or f"approval requested for {action_type}",
                event_id=event_id,
                workflow_run_id=workflow_run_id,
                action_id=action_request.action_id,
                approval_id=approval_ticket.approval_id,
                details={
                    "reason": approval_ticket.reason,
                    **action_request_details(action_request),
                },
            )
        )
    for item in audit_records:
        runtime.append_gateway_audit_record(item)
    return {
        "action_request": action_request,
        "approval_ticket": approval_ticket,
        "audit_records": audit_records,
    }

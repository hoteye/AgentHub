from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli.approval_continuation_projection_runtime import continuation_status_from_metadata


def string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def workflow_result_details(workflow_run: Any) -> Dict[str, Any]:
    context = getattr(workflow_run, "context", {})
    if not isinstance(context, dict):
        return {}
    workflow_result = context.get("workflow_result")
    if isinstance(workflow_result, dict):
        return dict(workflow_result)
    return {}


def recommendation_item(action_request: Any) -> Dict[str, Any]:
    browser_metadata = dict(getattr(action_request, "metadata", {}) or {}).get("browser")
    normalized_browser_metadata = dict(browser_metadata or {}) if isinstance(browser_metadata, dict) else {}
    return {
        "action_id": action_request.action_id,
        "action_type": action_request.action_type,
        "connector_key": action_request.connector_key,
        "plugin_name": action_request.plugin_name,
        "requested_at": action_request.requested_at,
        "requested_by": action_request.requested_by,
        "approval_required": action_request.approval_required,
        "action_family": getattr(action_request, "action_family", None),
        "action_class": getattr(action_request, "action_class", None),
        "approval_policy": getattr(action_request, "approval_policy", None),
        "audit_stage": getattr(action_request, "audit_stage", None),
        "browser": normalized_browser_metadata or None,
    }


def execution_diagnostic(audit_record: Any | None) -> Dict[str, Any]:
    if audit_record is None:
        return {
            "status": "not_executed",
            "summary": "",
            "artifact_refs": [],
        }
    details = dict(getattr(audit_record, "details", {}) or {})
    return {
        "status": str(getattr(audit_record, "status", "") or "").strip(),
        "summary": str(getattr(audit_record, "summary", "") or "").strip(),
        "artifact_refs": string_list(details.get("artifact_refs")),
        "github_artifacts": dict(details.get("github_artifacts") or {}),
        "github_workflow_run": dict(details.get("github_workflow_run") or {}),
        "browser_execution": dict(details.get("browser_execution") or {}),
        "output": dict(details.get("output") or {}),
    }


def approval_diagnostic(
    runtime: Any,
    approval_ticket: Any,
    *,
    action_requests_by_id: Dict[str, Any],
    audit_records: List[Any],
) -> Dict[str, Any]:
    _ = runtime
    metadata = dict(approval_ticket.metadata or {})
    action_request = action_requests_by_id.get(approval_ticket.action_id)
    workflow_name = str(metadata.get("workflow_name") or "").strip()
    reasoning_summary = str(metadata.get("reasoning_summary") or "").strip()
    evidence_refs = list(
        dict.fromkeys(
            [
                *string_list(metadata.get("evidence_refs")),
                *string_list(approval_ticket.evidence_refs),
            ]
        )
    )
    execution_record = next(
        (
            item
            for item in audit_records
            if str(item.stage or "").strip().lower() == "action_execute"
            and str(item.approval_id or "").strip() == approval_ticket.approval_id
        ),
        None,
    )
    continuation = continuation_status_from_metadata(
        ticket=approval_ticket,
        action_request=action_request,
    )
    return {
        "trace_id": approval_ticket.trace_id,
        "event_id": (
            action_request.event_id
            if action_request is not None
            else str(metadata.get("source_event_id") or "").strip() or None
        ),
        "workflow_run_id": (
            action_request.workflow_run_id
            if action_request is not None
            else str(metadata.get("source_workflow_run_id") or "").strip() or None
        ),
        "approval_id": approval_ticket.approval_id,
        "action_id": approval_ticket.action_id,
        "plugin_name": (
            action_request.plugin_name
            if action_request is not None
            else str(metadata.get("source_plugin_name") or "").strip() or None
        ),
        "workflow_name": workflow_name or None,
        "reasoning": {
            "summary": reasoning_summary,
            "evidence_refs": evidence_refs,
        },
        "recommendation": (
            recommendation_item(action_request)
            if action_request is not None
            else {
                "action_id": approval_ticket.action_id,
                "action_type": str(metadata.get("source_action_type") or "").strip(),
                "connector_key": str(metadata.get("source_connector_key") or "").strip(),
                "plugin_name": str(metadata.get("source_plugin_name") or "").strip(),
                "requested_at": approval_ticket.requested_at,
                "requested_by": approval_ticket.requested_by,
                "approval_required": True,
                "action_family": str(metadata.get("source_action_family") or "").strip() or None,
                "action_class": str(metadata.get("source_action_class") or "").strip() or None,
                "approval_policy": str(metadata.get("source_approval_policy") or "").strip() or None,
                "audit_stage": str(metadata.get("source_audit_stage") or "").strip() or None,
                "browser": dict(metadata.get("browser") or {}) or None,
            }
        ),
        "approval": {
            "status": approval_ticket.status,
            "summary": approval_ticket.summary,
            "reason": approval_ticket.reason,
            "requested_at": approval_ticket.requested_at,
            "requested_by": approval_ticket.requested_by,
            "decision_at": approval_ticket.decision_at,
            "decision_by": approval_ticket.decision_by,
            "decision_note": approval_ticket.decision_note,
        },
        "execution": execution_diagnostic(execution_record),
        "continuation": continuation or None,
    }


def workflow_diagnostic(
    runtime: Any,
    workflow_run: Any,
    *,
    action_requests: List[Any],
    approval_tickets_by_action_id: Dict[str, Any],
    audit_records: List[Any],
) -> Dict[str, Any]:
    _ = runtime
    workflow_result = workflow_result_details(workflow_run)
    recommendations = [
        recommendation_item(item)
        for item in action_requests
        if str(item.workflow_run_id or "").strip() == workflow_run.workflow_run_id
    ]
    latest_approval = next(
        (
            approval_tickets_by_action_id[item["action_id"]]
            for item in recommendations
            if item["action_id"] in approval_tickets_by_action_id
        ),
        None,
    )
    approval = {
        "status": "not_requested",
        "approval_id": None,
    }
    execution = {
        "status": "not_executed",
        "summary": "",
        "artifact_refs": [],
    }
    if latest_approval is not None:
        approval = {
            "status": latest_approval.status,
            "approval_id": latest_approval.approval_id,
            "decision_at": latest_approval.decision_at,
            "decision_by": latest_approval.decision_by,
        }
        execution = execution_diagnostic(
            next(
                (
                    item
                    for item in audit_records
                    if str(item.stage or "").strip().lower() == "action_execute"
                    and str(item.approval_id or "").strip() == latest_approval.approval_id
                ),
                None,
            )
        )
    elif recommendations:
        execution = execution_diagnostic(
            next(
                (
                    item
                    for item in reversed(audit_records)
                    if str(item.stage or "").strip().lower() == "action_execute"
                    and str(item.workflow_run_id or "").strip() == workflow_run.workflow_run_id
                    and any(str(candidate["action_id"]) == str(item.action_id or "") for candidate in recommendations)
                ),
                None,
            )
        )
    return {
        "trace_id": workflow_run.trace_id,
        "event_id": workflow_run.event_id,
        "workflow_run_id": workflow_run.workflow_run_id,
        "plugin_name": workflow_run.plugin_name,
        "workflow_name": workflow_run.workflow_name,
        "workflow_status": workflow_run.status,
        "reasoning": {
            "status": str(workflow_result.get("status") or "").strip(),
            "summary": str(workflow_result.get("reasoning_summary") or workflow_run.result_summary or "").strip(),
            "evidence_refs": string_list(workflow_result.get("evidence_refs")),
        },
        "recommendation": {
            "count": len(recommendations),
            "items": recommendations,
        },
        "browser_workflow": dict((workflow_run.context or {}).get("browser_workflow") or {}) or None,
        "approval": approval,
        "execution": execution,
    }


def build_gateway_diagnostics(
    runtime: Any,
    *,
    workflow_runs: List[Any],
    action_requests: List[Any],
    approval_tickets: List[Any],
    audit_records: List[Any],
) -> Dict[str, Any]:
    action_requests_by_id = {item.action_id: item for item in action_requests}
    approval_tickets_by_action_id = {item.action_id: item for item in approval_tickets}
    return {
        "workflow_diagnostics": [
            workflow_diagnostic(
                runtime,
                workflow_run,
                action_requests=action_requests,
                approval_tickets_by_action_id=approval_tickets_by_action_id,
                audit_records=audit_records,
            )
            for workflow_run in workflow_runs
        ],
        "approval_diagnostics": [
            approval_diagnostic(
                runtime,
                approval_ticket,
                action_requests_by_id=action_requests_by_id,
                audit_records=audit_records,
            )
            for approval_ticket in approval_tickets
        ],
    }


def list_approval_diagnostics(runtime: Any, *, limit: int = 20, status: str | None = None) -> List[Dict[str, Any]]:
    safe_limit = max(1, int(limit))
    approval_tickets = runtime.gateway_state_store.list_approval_tickets(limit=safe_limit, status=status)
    action_requests = runtime.gateway_state_store.list_action_requests(limit=max(safe_limit, 100))
    audit_records = runtime.gateway_state_store.list_audit_records(limit=max(safe_limit * 5, 100))
    action_requests_by_id = {item.action_id: item for item in action_requests}
    return [
        approval_diagnostic(
            runtime,
            approval_ticket,
            action_requests_by_id=action_requests_by_id,
            audit_records=audit_records,
        )
        for approval_ticket in approval_tickets
    ]

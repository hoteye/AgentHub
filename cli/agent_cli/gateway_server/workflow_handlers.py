from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

JsonMap = dict[str, Any]


@dataclass(slots=True, frozen=True)
class WorkflowHandlerDeps:
    first_int: Callable[..., int]
    first_text: Callable[..., str]
    gateway_item_to_dict: Callable[[Any], JsonMap]
    sorted_trace_timeline: Callable[..., list[JsonMap]]
    workflow_resume_eligible: Callable[[JsonMap], bool]
    create_audit_record: Callable[..., Any]
    success: Callable[[JsonMap], Any]
    failure: Callable[[int, str], Any]
    handle_gateway_state_get: Callable[..., Any]


def build_workflow_handler_family(deps: WorkflowHandlerDeps) -> dict[str, Callable[..., Any]]:
    def handle_workflows_list(**kwargs: Any) -> Any:
        params = kwargs["params"]
        runtime = kwargs["runtime"]
        limit = deps.first_int(params, "limit", default=20, minimum=1, maximum=200)
        status_filter = deps.first_text(params, "status").lower()
        plugin_filter = deps.first_text(params, "pluginName", "plugin_name")
        trace_filter = deps.first_text(params, "traceId", "trace_id")
        snapshot = runtime.gateway_state_snapshot(limit=max(limit * 5, 100))
        workflow_runs = [
            deps.gateway_item_to_dict(item)
            for item in snapshot.get("workflow_runs") or []
        ]
        workflow_diagnostics = list((snapshot.get("diagnostics") or {}).get("workflow_diagnostics") or [])
        filtered_runs = []
        for item in workflow_runs:
            if status_filter and str(item.get("status") or "").strip().lower() != status_filter:
                continue
            if plugin_filter and str(item.get("plugin_name") or "").strip() != plugin_filter:
                continue
            if trace_filter and str(item.get("trace_id") or "").strip() != trace_filter:
                continue
            filtered_runs.append(item)
        filtered_runs = filtered_runs[:limit]
        selected_ids = {str(item.get("workflow_run_id") or "").strip() for item in filtered_runs}
        diagnostics_rows = [
            item for item in workflow_diagnostics if str(item.get("workflow_run_id") or "").strip() in selected_ids
        ]
        return deps.success(
            {
                "workflowRuns": filtered_runs,
                "workflowDiagnostics": diagnostics_rows,
                "counts": {
                    "workflowRuns": len(filtered_runs),
                    "running": sum(1 for item in filtered_runs if str(item.get("status") or "").strip().lower() == "running"),
                    "paused": sum(1 for item in filtered_runs if deps.workflow_resume_eligible(item)),
                },
            }
        )

    def handle_workflows_get(**kwargs: Any) -> Any:
        params = kwargs["params"]
        runtime = kwargs["runtime"]
        workflow_run_id = deps.first_text(params, "workflowRunId", "workflow_run_id")
        if not workflow_run_id:
            return deps.failure(-32602, "Invalid params", detail="params.workflowRunId must be a non-empty string")

        getter = getattr(getattr(runtime, "gateway_state_store", None), "get_workflow_run", None)
        item = getter(workflow_run_id) if callable(getter) else None
        workflow_run = deps.gateway_item_to_dict(item) if item is not None else None
        snapshot = runtime.gateway_state_snapshot(limit=200)
        if workflow_run is None:
            workflow_run = next(
                (
                    deps.gateway_item_to_dict(item)
                    for item in snapshot.get("workflow_runs") or []
                    if str(getattr(item, "workflow_run_id", None) or (item or {}).get("workflow_run_id") or "").strip() == workflow_run_id
                ),
                None,
            )
        if workflow_run is None:
            return deps.failure(-32040, "Workflow not found", detail=workflow_run_id)

        workflow_trace_id = str(workflow_run.get("trace_id") or "").strip()
        related_events = [
            deps.gateway_item_to_dict(item)
            for item in snapshot.get("events") or []
            if str(getattr(item, "trace_id", None) or (item or {}).get("trace_id") or "").strip() == workflow_trace_id
        ]
        related_actions = [
            deps.gateway_item_to_dict(item)
            for item in snapshot.get("action_requests") or []
            if (
                str(getattr(item, "workflow_run_id", None) or (item or {}).get("workflow_run_id") or "").strip() == workflow_run_id
                or str(getattr(item, "trace_id", None) or (item or {}).get("trace_id") or "").strip() == workflow_trace_id
            )
        ]
        action_ids = {
            str(item.get("action_id") or "").strip()
            for item in related_actions
            if str(item.get("action_id") or "").strip()
        }
        related_approvals = [
            deps.gateway_item_to_dict(item)
            for item in snapshot.get("approval_tickets") or []
            if (
                str(getattr(item, "trace_id", None) or (item or {}).get("trace_id") or "").strip() == workflow_trace_id
                or str(getattr(item, "action_id", None) or (item or {}).get("action_id") or "").strip() in action_ids
            )
        ]
        related_audits = [
            deps.gateway_item_to_dict(item)
            for item in snapshot.get("audit_records") or []
            if str(getattr(item, "trace_id", None) or (item or {}).get("trace_id") or "").strip() == workflow_trace_id
        ]
        workflow_diagnostic = next(
            (
                item
                for item in list((snapshot.get("diagnostics") or {}).get("workflow_diagnostics") or [])
                if str(item.get("workflow_run_id") or "").strip() == workflow_run_id
            ),
            None,
        )
        related_approval_diagnostics = [
            item
            for item in list((snapshot.get("diagnostics") or {}).get("approval_diagnostics") or [])
            if str(item.get("trace_id") or "").strip() == workflow_trace_id
            or str(item.get("approval_id") or "").strip()
            in {str(item.get("approval_id") or "").strip() for item in related_approvals}
        ]
        timeline = deps.sorted_trace_timeline(
            trace_id=workflow_trace_id,
            events=related_events,
            workflow_runs=[workflow_run],
            action_requests=related_actions,
            approval_tickets=related_approvals,
            audit_records=related_audits,
        )
        return deps.success(
            {
                "workflowRun": workflow_run,
                "workflowDiagnostic": workflow_diagnostic,
                "events": related_events,
                "actionRequests": related_actions,
                "approvalTickets": related_approvals,
                "approvalDiagnostics": related_approval_diagnostics,
                "auditRecords": related_audits,
                "traceId": workflow_trace_id,
                "timeline": timeline,
                "resumeEligible": deps.workflow_resume_eligible(workflow_run),
            }
        )

    def handle_workflows_resume(**kwargs: Any) -> Any:
        params = kwargs["params"]
        runtime = kwargs["runtime"]
        client_info = kwargs["client_info"]
        workflow_run_id = deps.first_text(params, "workflowRunId", "workflow_run_id")
        if not workflow_run_id:
            return deps.failure(-32602, "Invalid params", detail="params.workflowRunId must be a non-empty string")
        getter = getattr(getattr(runtime, "gateway_state_store", None), "get_workflow_run", None)
        workflow_run = getter(workflow_run_id) if callable(getter) else None
        if workflow_run is None:
            return deps.failure(-32040, "Workflow not found", detail=workflow_run_id)
        workflow_payload = deps.gateway_item_to_dict(workflow_run)
        if not deps.workflow_resume_eligible(workflow_payload):
            return deps.failure(
                -32042,
                "Workflow not resumable",
                detail=f"workflow {workflow_run_id} is not resumable from status={workflow_payload.get('status') or '-'}",
            )
        decided_by = (
            deps.first_text(params, "decidedBy", "decided_by")
            or deps.first_text(dict(client_info or {}), "actorId", "actor_id", "name")
            or "operator"
        )
        note = deps.first_text(params, "note", "decisionNote", "decision_note")
        updater = getattr(runtime, "update_workflow_run_state", None)
        updated = (
            updater(
                workflow_run_id,
                status="running",
                current_step="manual_resume_requested",
                result_summary=note or f"resume requested by {decided_by}",
                context_updates={
                    "operator_resume": {
                        "requested_by": decided_by,
                        "note": note,
                    }
                },
                finished=False,
            )
            if callable(updater)
            else workflow_run
        )
        audit_record = deps.create_audit_record(
            trace_id=str(getattr(updated, "trace_id", None) or workflow_payload.get("trace_id") or ""),
            stage="workflow_resume",
            status="requested",
            summary=f"operator requested resume for {workflow_run_id}",
            event_id=getattr(updated, "event_id", None) or workflow_payload.get("event_id"),
            workflow_run_id=workflow_run_id,
            details={
                "requested_by": decided_by,
                "note": note,
                "previous_status": workflow_payload.get("status"),
            },
        )
        append_audit = getattr(runtime, "append_gateway_audit_record", None)
        if callable(append_audit):
            append_audit(audit_record)
        detail_result = handle_workflows_get(
            params={"workflowRunId": workflow_run_id},
            runtime=runtime,
            action_worker=kwargs.get("action_worker"),
            request_id=kwargs.get("request_id"),
            client_info=client_info,
            method="workflows.get",
        )
        if not detail_result.ok:
            return detail_result
        payload = dict(detail_result.result or {})
        payload["resumeRequested"] = True
        payload["auditRecord"] = audit_record.to_dict()
        return deps.success(payload)

    def handle_gateway_trace_timeline(**kwargs: Any) -> Any:
        params = kwargs["params"]
        trace_id = deps.first_text(params, "traceId", "trace_id")
        if not trace_id:
            return deps.failure(-32602, "Invalid params", detail="params.traceId must be a non-empty string")
        state = deps.handle_gateway_state_get(**kwargs)
        if not state.ok:
            return state
        result = dict(state.result or {})
        timeline = deps.sorted_trace_timeline(
            trace_id=trace_id,
            events=result.get("events") or [],
            workflow_runs=result.get("workflowRuns") or [],
            action_requests=result.get("actionRequests") or [],
            approval_tickets=result.get("approvalTickets") or [],
            audit_records=result.get("auditRecords") or [],
        )
        return deps.success({"traceId": trace_id, "timeline": timeline})

    def handle_approvals_list(**kwargs: Any) -> Any:
        params = kwargs["params"]
        runtime = kwargs["runtime"]
        limit = int(params.get("limit") or 20)
        status = deps.first_text(params, "status") or None
        items = runtime.list_approval_tickets(limit=limit, status=status)
        diagnostics = runtime.list_approval_diagnostics(limit=limit, status=status)
        return deps.success(
            {
                "approvalTickets": [deps.gateway_item_to_dict(item) for item in items],
                "approvalDiagnostics": diagnostics,
            }
        )

    def handle_approvals_get(**kwargs: Any) -> Any:
        params = kwargs["params"]
        runtime = kwargs["runtime"]
        approval_id = deps.first_text(params, "approvalId", "approval_id")
        if not approval_id:
            return deps.failure(-32602, "Invalid params", detail="params.approvalId must be a non-empty string")
        ticket = runtime.gateway_state_store.get_approval_ticket(approval_id)
        if ticket is None:
            return deps.failure(-32040, "Approval not found", detail=approval_id)
        action_request = runtime.gateway_state_store.get_action_request(ticket.action_id)
        audit_records = runtime.gateway_state_store.list_audit_records(limit=200)
        matching_audits = [
            deps.gateway_item_to_dict(item)
            for item in audit_records
            if str(getattr(item, "trace_id", "") or "").strip() == str(ticket.trace_id or "").strip()
        ]
        return deps.success(
            {
                "approvalTicket": deps.gateway_item_to_dict(ticket),
                "actionRequest": deps.gateway_item_to_dict(action_request),
                "auditRecords": matching_audits,
            }
        )

    return {
        "workflows.list": handle_workflows_list,
        "workflows.get": handle_workflows_get,
        "workflows.resume": handle_workflows_resume,
        "gateway.trace.timeline": handle_gateway_trace_timeline,
        "approvals.list": handle_approvals_list,
        "approvals.get": handle_approvals_get,
    }

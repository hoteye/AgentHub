from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.gateway_api.approvals_api import approval_decision_result_to_snake_case
from cli.agent_cli.gateway_core import (
    TriggerRegistration,
    create_audit_record,
    create_gateway_event,
    create_workflow_run,
)


def gateway_item_to_dict(item: Any) -> dict[str, Any]:
    if hasattr(item, "to_dict"):
        return dict(item.to_dict())
    return dict(item or {})


def approval_risk(item: Any) -> str:
    metadata = getattr(item, "metadata", None) or {}
    if isinstance(metadata, dict):
        risk = str(metadata.get("risk_level") or metadata.get("risk") or "").strip().lower()
        if risk in {"low", "medium", "high"}:
            return risk
    status = str(getattr(item, "status", "") or "").strip().lower()
    return "high" if status == "pending" else "medium"


def approval_list_data(*, tickets: list[Any], diagnostics: list[Any]) -> dict[str, Any]:
    return {
        "approvals": [
            {
                "approval_id": item.approval_id,
                "action_id": item.action_id,
                "trace_id": item.trace_id,
                "status": item.status,
                "decision_type": getattr(item, "decision_type", None),
                "title": item.summary or item.reason or item.action_id,
                "risk": approval_risk(item),
                "summary": item.summary,
                "requested_at": item.requested_at,
                "requested_by": item.requested_by,
                "reason": item.reason,
                "available_decisions": [dict(choice) for choice in list(getattr(item, "available_decisions", []) or []) if isinstance(choice, dict)],
            }
            for item in tickets
        ],
        "approval_diagnostics": list(diagnostics or []),
        "pending_count": sum(
            1 for item in tickets if str(getattr(item, "status", "")).strip().lower() == "pending"
        ),
    }


def approval_resolve_data(*, approval_id: str, decision: str, result: Any) -> dict[str, Any]:
    carrier = approval_decision_result_to_snake_case(result)
    approval_ticket = carrier.get("approval_ticket") or {}
    return {
        "accepted": True,
        "approval_id": approval_id,
        "status": str(approval_ticket.get("status") or decision),
        "decision_type": approval_ticket.get("decision_type"),
        **carrier,
    }


def browser_workflow_bootstrap(
    runtime: Any,
    *,
    request_id: str,
    workflow_name: str,
    playbook_kind: str,
    payload: dict[str, Any],
    reasoning_summary: str,
    evidence_refs: list[str],
    browser_request: dict[str, Any],
    browser_workflow_plugin: str,
    browser_workflow_connector: str,
    get_gateway_request_scope_fn: Callable[[], Any],
) -> dict[str, Any]:
    event = create_gateway_event(
        event_type=f"browser.workflow.{playbook_kind}.requested",
        source_kind="gui_bridge",
        source_id=request_id,
        connector_key=browser_workflow_connector,
        payload=payload,
        metadata={"request_id": request_id, "playbook_kind": playbook_kind},
        plugin_name=browser_workflow_plugin,
    )
    trigger = TriggerRegistration(
        trigger_key=f"{playbook_kind}_manual",
        plugin_name=browser_workflow_plugin,
        trigger_kind="manual",
        connector_key=browser_workflow_connector,
        event_types=[event.event_type],
        workflow_name=workflow_name,
    )
    workflow_run = create_workflow_run(
        trigger=trigger,
        event=event,
        status="running",
        current_step="workflow_started",
        context={
            "workflow_result": {
                "status": "running",
                "reasoning_summary": reasoning_summary,
                "evidence_refs": list(evidence_refs),
                "action_request_count": 0,
            },
            "browser_workflow": {
                "playbook_kind": playbook_kind,
                "status": "running",
                "request_id": request_id,
                "browser_request": dict(browser_request),
                "evidence_refs": list(evidence_refs),
            },
        },
        metadata={"source": "gui_bridge", "request_id": request_id},
    )
    active_scope = get_gateway_request_scope_fn()
    if active_scope is not None:
        workflow_run.context.setdefault("request_scope", active_scope.to_dict())
    runtime.save_gateway_event(event)
    runtime.save_gateway_workflow_run(workflow_run)
    audit_records = [
        create_audit_record(
            trace_id=event.trace_id,
            stage="ingress",
            status="ok",
            summary=f"received {event.event_type}",
            event_id=event.event_id,
            workflow_run_id=workflow_run.workflow_run_id,
            details={
                "source_kind": event.source_kind,
                "source_id": event.source_id,
                "connector_key": event.connector_key,
            },
        ),
        create_audit_record(
            trace_id=event.trace_id,
            stage="route",
            status="host_workflow",
            summary=f"routed to {workflow_name}",
            event_id=event.event_id,
            workflow_run_id=workflow_run.workflow_run_id,
            details={
                "plugin_name": browser_workflow_plugin,
                "workflow_name": workflow_name,
                "playbook_kind": playbook_kind,
            },
        ),
        create_audit_record(
            trace_id=event.trace_id,
            stage="workflow_reasoning",
            status="ok",
            summary=reasoning_summary,
            event_id=event.event_id,
            workflow_run_id=workflow_run.workflow_run_id,
            details={
                "workflow_name": workflow_name,
                "reasoning_summary": reasoning_summary,
                "evidence_refs": list(evidence_refs),
                "browser": dict(browser_request),
            },
        ),
    ]
    for item in audit_records:
        runtime.append_gateway_audit_record(item)
    return {"event": event, "workflow_run": workflow_run, "audit_records": audit_records}


def browser_workflow_verify(
    runtime: Any,
    *,
    request_id: str,
    action: str,
    payload: dict[str, Any],
    success: Callable[..., dict[str, Any]],
    browser_request: dict[str, Any],
    browser_workflow_plugin: str,
    browser_workflow_connector: str,
    get_gateway_request_scope_fn: Callable[[], Any],
) -> dict[str, Any]:
    reasoning_summary = str(payload.get("reasoning_summary") or "verify current browser page state").strip()
    evidence_refs = list(payload.get("evidence_refs") or [])
    bootstrap = browser_workflow_bootstrap(
        runtime,
        request_id=request_id,
        workflow_name="browser_read_verify",
        playbook_kind="read_verify",
        payload=payload,
        reasoning_summary=reasoning_summary,
        evidence_refs=evidence_refs,
        browser_request=browser_request,
        browser_workflow_plugin=browser_workflow_plugin,
        browser_workflow_connector=browser_workflow_connector,
        get_gateway_request_scope_fn=get_gateway_request_scope_fn,
    )
    event = bootstrap["event"]
    workflow_run = bootstrap["workflow_run"]
    action_request_payload = runtime.request_gateway_action(
        action_type="browser.snapshot",
        connector_key=browser_workflow_connector,
        plugin_name=browser_workflow_plugin,
        request_payload={"browser_request": browser_request},
        requested_by="gui.browser.workflow",
        trace_id=event.trace_id,
        event_id=event.event_id,
        workflow_run_id=workflow_run.workflow_run_id,
        approval_summary="",
        metadata={
            "workflow_name": workflow_run.workflow_name,
            "reasoning_summary": reasoning_summary,
            "evidence_refs": evidence_refs,
        },
    )
    action_request = action_request_payload["action_request"]
    execution = runtime.execute_gateway_action_now(action_request)
    action_result = execution["action_result"]
    audit_records = [
        *bootstrap["audit_records"],
        *action_request_payload["audit_records"],
        execution["audit_record"],
    ]
    updated_workflow = runtime.update_workflow_run_state(
        workflow_run.workflow_run_id,
        status="ok" if action_result.ok else "failed",
        current_step="browser_verify_completed" if action_result.ok else "browser_verify_failed",
        result_summary=action_result.summary,
        context_updates={
            "workflow_result": {
                "status": "ok" if action_result.ok else "failed",
                "reasoning_summary": reasoning_summary,
                "evidence_refs": list(
                    dict.fromkeys(
                        [
                            *evidence_refs,
                            *list(execution["audit_record"].details.get("artifact_refs") or []),
                        ]
                    )
                ),
                "action_request_count": 1,
            },
            "browser_workflow": {
                "status": "completed" if action_result.ok else "failed",
                "action_id": action_request.action_id,
                "last_execution": {
                    "status": "ok" if action_result.ok else "failed",
                    "summary": action_result.summary,
                },
            },
        },
        finished=True,
    )
    return success(
        request_id=request_id,
        action=action,
        data={
            "accepted": True,
            "mode": "executed",
            "trace_id": event.trace_id,
            "event": gateway_item_to_dict(event),
            "workflow_run": gateway_item_to_dict(updated_workflow or workflow_run),
            "action_request": gateway_item_to_dict(action_request),
            "action_result": action_result.to_dict(),
            "audit_records": [gateway_item_to_dict(item) for item in audit_records],
        },
    )


def browser_workflow_mutate(
    runtime: Any,
    *,
    request_id: str,
    action: str,
    payload: dict[str, Any],
    success: Callable[..., dict[str, Any]],
    browser_request: dict[str, Any],
    action_type: str,
    browser_workflow_plugin: str,
    browser_workflow_connector: str,
    get_gateway_request_scope_fn: Callable[[], Any],
) -> dict[str, Any]:
    reasoning_summary = str(
        payload.get("reasoning_summary") or "propose browser mutation and wait for approval"
    ).strip()
    evidence_refs = list(payload.get("evidence_refs") or [])
    bootstrap = browser_workflow_bootstrap(
        runtime,
        request_id=request_id,
        workflow_name="browser_mutate_after_approval",
        playbook_kind="mutate_after_approval",
        payload=payload,
        reasoning_summary=reasoning_summary,
        evidence_refs=evidence_refs,
        browser_request=browser_request,
        browser_workflow_plugin=browser_workflow_plugin,
        browser_workflow_connector=browser_workflow_connector,
        get_gateway_request_scope_fn=get_gateway_request_scope_fn,
    )
    event = bootstrap["event"]
    workflow_run = bootstrap["workflow_run"]
    requested = runtime.request_gateway_action(
        action_type=action_type,
        connector_key=browser_workflow_connector,
        plugin_name=browser_workflow_plugin,
        request_payload={"browser_request": browser_request},
        requested_by="gui.browser.workflow",
        trace_id=event.trace_id,
        event_id=event.event_id,
        workflow_run_id=workflow_run.workflow_run_id,
        approval_summary=str(payload.get("approval_summary") or f"Approve {action_type}").strip(),
        approval_reason=str(
            payload.get("approval_reason") or "browser workflow mutation requires approval"
        ).strip(),
        metadata={
            "workflow_name": workflow_run.workflow_name,
            "reasoning_summary": reasoning_summary,
            "evidence_refs": evidence_refs,
        },
    )
    action_request = requested["action_request"]
    approval_ticket = requested["approval_ticket"]
    updated_workflow = runtime.update_workflow_run_state(
        workflow_run.workflow_run_id,
        status="approval_requested",
        current_step="approval_pending",
        result_summary=reasoning_summary,
        context_updates={
            "workflow_result": {
                "status": "approval_requested",
                "reasoning_summary": reasoning_summary,
                "evidence_refs": evidence_refs,
                "action_request_count": 1,
            },
            "browser_workflow": {
                "status": "paused_for_approval",
                "pending_action_id": action_request.action_id,
                "pending_approval_id": approval_ticket.approval_id if approval_ticket is not None else None,
                "action_id": action_request.action_id,
            },
        },
    )
    return success(
        request_id=request_id,
        action=action,
        data={
            "accepted": True,
            "mode": "approval_required" if approval_ticket is not None else "executed",
            "trace_id": event.trace_id,
            "event": gateway_item_to_dict(event),
            "workflow_run": gateway_item_to_dict(updated_workflow or workflow_run),
            "action_request": gateway_item_to_dict(action_request),
            "approval_ticket": gateway_item_to_dict(approval_ticket) if approval_ticket is not None else None,
            "audit_records": [
                gateway_item_to_dict(item)
                for item in [*bootstrap["audit_records"], *requested["audit_records"]]
            ],
        },
    )

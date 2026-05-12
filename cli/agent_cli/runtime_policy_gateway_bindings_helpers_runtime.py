from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli.runtime_services import approval_runtime as approval_runtime_service
from cli.agent_cli.runtime_services import gateway_runtime as gateway_runtime_service


def gateway_registry(self: Any):
    return gateway_runtime_service.gateway_registry(self)


def current_gateway_request_scope(self: Any):
    return gateway_runtime_service.current_gateway_request_scope()


def gateway_broadcast_since(
    self: Any,
    cursor: int = 0,
    *,
    streams: List[str] | None = None,
) -> Dict[str, Any]:
    return gateway_runtime_service.gateway_broadcast_since(self, cursor, streams=streams)


def subscribe_gateway_broadcast(
    self: Any,
    *,
    subscription_id: str,
    streams: List[str] | None = None,
    callback: Any | None = None,
):
    return gateway_runtime_service.subscribe_gateway_broadcast(
        self,
        subscription_id=subscription_id,
        streams=streams,
        callback=callback,
    )


def unsubscribe_gateway_broadcast(self: Any, subscription_id: str) -> bool:
    return gateway_runtime_service.unsubscribe_gateway_broadcast(self, subscription_id)


def _broadcast_gateway_state(
    self: Any,
    *,
    stream: str,
    event: str,
    payload: Any,
    trace_id: str | None = None,
    correlation_id: str | None = None,
) -> None:
    gateway_runtime_service.broadcast_gateway_state(
        self,
        stream=stream,
        event=event,
        payload=payload,
        trace_id=trace_id,
        correlation_id=correlation_id,
    )


def save_gateway_event(self: Any, item: Any) -> Any:
    return gateway_runtime_service.save_gateway_event(self, item)


def save_gateway_workflow_run(self: Any, item: Any) -> Any:
    return gateway_runtime_service.save_gateway_workflow_run(self, item)


def save_gateway_action_request(self: Any, item: Any) -> Any:
    return gateway_runtime_service.save_gateway_action_request(self, item)


def save_gateway_approval_ticket(self: Any, item: Any) -> Any:
    return gateway_runtime_service.save_gateway_approval_ticket(self, item)


def append_gateway_audit_record(self: Any, item: Any) -> Any:
    return gateway_runtime_service.append_gateway_audit_record(self, item)


def route_gateway_event(self: Any, event: Any) -> Any:
    return gateway_runtime_service.route_gateway_event(self, event)


def _workflow_handler_registration(self: Any, decision: Any) -> Any | None:
    return gateway_runtime_service.workflow_handler_registration(self, decision)


def _invoke_workflow_handler(
    self: Any,
    *,
    decision: Any,
    event: Any,
    workflow_run: Any,
) -> Dict[str, Any] | None:
    return gateway_runtime_service.invoke_workflow_handler(
        self,
        decision=decision,
        event=event,
        workflow_run=workflow_run,
    )


def dispatch_gateway_event(self: Any, event: Any) -> Dict[str, Any]:
    return gateway_runtime_service.dispatch_gateway_event(self, event)


def gateway_state_snapshot(self: Any, *, limit: int = 20) -> Dict[str, Any]:
    return gateway_runtime_service.gateway_state_snapshot(self, limit=limit)


def list_approval_tickets(
    self: Any,
    *,
    limit: int = 20,
    status: str | None = None,
) -> List[Any]:
    return gateway_runtime_service.list_approval_tickets(self, limit=limit, status=status)


def update_workflow_run_state(
    self: Any,
    workflow_run_id: str,
    *,
    status: str | None = None,
    current_step: str | None = None,
    result_summary: str | None = None,
    context_updates: Dict[str, Any] | None = None,
    finished: bool = False,
) -> Any | None:
    return gateway_runtime_service.update_workflow_run_state(
        self,
        workflow_run_id,
        status=status,
        current_step=current_step,
        result_summary=result_summary,
        context_updates=context_updates,
        finished=finished,
    )


def list_approval_diagnostics(
    self: Any,
    *,
    limit: int = 20,
    status: str | None = None,
) -> List[Dict[str, Any]]:
    return gateway_runtime_service.list_approval_diagnostics(self, limit=limit, status=status)


def request_gateway_action(
    self: Any,
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
) -> Dict[str, Any]:
    return approval_runtime_service.request_gateway_action(
        self,
        action_type=action_type,
        connector_key=connector_key,
        plugin_name=plugin_name,
        request_payload=request_payload,
        requested_by=requested_by,
        trace_id=trace_id,
        event_id=event_id,
        workflow_run_id=workflow_run_id,
        approval_required=approval_required,
        approval_summary=approval_summary,
        approval_reason=approval_reason,
        metadata=metadata,
    )


def execute_gateway_action_now(
    self: Any,
    action_request: Any,
    *,
    approval_id: str | None = None,
) -> Dict[str, Any]:
    return approval_runtime_service.execute_gateway_action_now(
        self,
        action_request,
        approval_id=approval_id,
    )


def record_gateway_action_denied(
    self: Any,
    *,
    action_type: str,
    connector_key: str,
    plugin_name: str,
    request_payload: Dict[str, Any],
    requested_by: str,
    trace_id: str,
    summary: str,
    reason: str,
    metadata: Dict[str, Any] | None = None,
    event_id: str | None = None,
    workflow_run_id: str | None = None,
) -> Dict[str, Any]:
    return approval_runtime_service.record_gateway_action_denied(
        self,
        action_type=action_type,
        connector_key=connector_key,
        plugin_name=plugin_name,
        request_payload=request_payload,
        requested_by=requested_by,
        trace_id=trace_id,
        summary=summary,
        reason=reason,
        metadata=metadata,
        event_id=event_id,
        workflow_run_id=workflow_run_id,
    )


def _default_browser_action_executor(self: Any, action_request: Any):
    return approval_runtime_service.default_browser_action_executor(self, action_request)


def _execute_browser_gateway_action(self: Any, action_request: Any):
    return approval_runtime_service.execute_browser_gateway_action(self, action_request)


def _approval_diagnostic(
    self: Any,
    approval_ticket: Any,
    *,
    action_requests_by_id: Dict[str, Any],
    audit_records: List[Any],
) -> Dict[str, Any]:
    return gateway_runtime_service.approval_diagnostic(
        self,
        approval_ticket,
        action_requests_by_id=action_requests_by_id,
        audit_records=audit_records,
    )


def _workflow_diagnostic(
    self: Any,
    workflow_run: Any,
    *,
    action_requests: List[Any],
    approval_tickets_by_action_id: Dict[str, Any],
    audit_records: List[Any],
) -> Dict[str, Any]:
    return gateway_runtime_service.workflow_diagnostic(
        self,
        workflow_run,
        action_requests=action_requests,
        approval_tickets_by_action_id=approval_tickets_by_action_id,
        audit_records=audit_records,
    )


def _build_gateway_diagnostics(
    self: Any,
    *,
    workflow_runs: List[Any],
    action_requests: List[Any],
    approval_tickets: List[Any],
    audit_records: List[Any],
) -> Dict[str, Any]:
    return gateway_runtime_service.build_gateway_diagnostics(
        self,
        workflow_runs=workflow_runs,
        action_requests=action_requests,
        approval_tickets=approval_tickets,
        audit_records=audit_records,
    )


def _decide_patch_approval(
    self: Any,
    approval_id: str,
    *,
    approved: bool | None = None,
    decision: Any = None,
    decided_by: str,
    decision_note: str = "",
) -> Dict[str, Any]:
    return approval_runtime_service.decide_patch_approval(
        self,
        approval_id,
        approved=approved,
        decision=decision,
        decided_by=decided_by,
        decision_note=decision_note,
    )


def _decide_shell_approval(
    self: Any,
    approval_id: str,
    *,
    approved: bool | None = None,
    decision: Any = None,
    decided_by: str,
    decision_note: str = "",
) -> Dict[str, Any]:
    return approval_runtime_service.decide_shell_approval(
        self,
        approval_id,
        approved=approved,
        decision=decision,
        decided_by=decided_by,
        decision_note=decision_note,
    )


def _decide_background_teammate_approval(
    self: Any,
    approval_id: str,
    *,
    approved: bool | None = None,
    decision: Any = None,
    decided_by: str,
    decision_note: str = "",
) -> Dict[str, Any]:
    return approval_runtime_service.decide_background_teammate_approval(
        self,
        approval_id,
        approved=approved,
        decision=decision,
        decided_by=decided_by,
        decision_note=decision_note,
    )

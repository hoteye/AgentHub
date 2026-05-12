from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli.gateway_core import GatewayRegistry, create_workflow_run, route_event
from cli.agent_cli.gateway_server.request_scope import get_gateway_request_scope
from cli.agent_cli.runtime_services import gateway_diagnostics_runtime
from cli.agent_cli.runtime_services import gateway_runtime_helpers_runtime
from cli.agent_cli.runtime_services import gateway_runtime_helper_runtime


def gateway_registry(runtime: Any) -> GatewayRegistry:
    registry = GatewayRegistry()
    plugin_manager = getattr(runtime.tools, "_plugin_manager", None)
    if plugin_manager is not None:
        registry.load_from_plugin_manager(plugin_manager)
    return registry


def current_gateway_request_scope() -> Any:
    return get_gateway_request_scope()


def gateway_broadcast_since(runtime: Any, cursor: int = 0, *, streams: List[str] | None = None) -> Dict[str, Any]:
    return runtime.gateway_broadcaster.list_since(cursor, streams=streams)


def subscribe_gateway_broadcast(
    runtime: Any,
    *,
    subscription_id: str,
    streams: List[str] | None = None,
    callback: Any = None,
) -> Any:
    return runtime.gateway_broadcaster.subscribe(
        subscription_id=subscription_id,
        streams=streams,
        callback=callback,
    )


def unsubscribe_gateway_broadcast(runtime: Any, subscription_id: str) -> bool:
    return runtime.gateway_broadcaster.unsubscribe(subscription_id)


def broadcast_gateway_state(
    runtime: Any,
    *,
    stream: str,
    event: str,
    payload: Any,
    trace_id: str | None = None,
    correlation_id: str | None = None,
) -> None:
    runtime.gateway_broadcaster.publish(
        stream=stream,
        event=event,
        payload=payload,
        trace_id=trace_id,
        correlation_id=correlation_id,
    )


def save_gateway_event(runtime: Any, item: Any) -> Any:
    saved = runtime.gateway_state_store.save_event(item)
    broadcast_gateway_state(
        runtime,
        stream="gateway_events",
        event="gateway.event.created",
        payload=saved.to_dict(),
        trace_id=saved.trace_id,
        correlation_id=saved.correlation_id,
    )
    return saved


def save_gateway_workflow_run(runtime: Any, item: Any) -> Any:
    normalized_item = gateway_runtime_helper_runtime.with_workflow_run_identifiers(item)
    saved = runtime.gateway_state_store.save_workflow_run(normalized_item)
    saved = gateway_runtime_helper_runtime.sync_workflow_run_with_run_manager(runtime, saved)
    broadcast_gateway_state(
        runtime,
        stream="workflow_runs",
        event="workflow.updated",
        payload=gateway_runtime_helper_runtime.broadcast_payload(saved),
        trace_id=getattr(saved, "trace_id", None),
        correlation_id=getattr(saved, "event_id", None),
    )
    return saved


def save_gateway_action_request(runtime: Any, item: Any) -> Any:
    saved = runtime.gateway_state_store.save_action_request(item)
    broadcast_gateway_state(
        runtime,
        stream="workflow_runs",
        event="action_request.created",
        payload=gateway_runtime_helper_runtime.broadcast_payload(saved),
        trace_id=getattr(saved, "trace_id", None),
        correlation_id=getattr(saved, "event_id", None),
    )
    return saved


def save_gateway_approval_ticket(runtime: Any, item: Any) -> Any:
    saved = runtime.gateway_state_store.save_approval_ticket(item)
    broadcast_gateway_state(
        runtime,
        stream="approvals",
        event="approval.updated",
        payload=gateway_runtime_helper_runtime.broadcast_payload(saved),
        trace_id=getattr(saved, "trace_id", None),
        correlation_id=getattr(saved, "action_id", None),
    )
    return saved


def append_gateway_audit_record(runtime: Any, item: Any) -> Any:
    saved = runtime.gateway_state_store.append_audit_record(item)
    broadcast_gateway_state(
        runtime,
        stream="audit",
        event="audit.appended",
        payload=gateway_runtime_helper_runtime.broadcast_payload(saved),
        trace_id=getattr(saved, "trace_id", None),
        correlation_id=getattr(saved, "event_id", None) or getattr(saved, "action_id", None),
    )
    return saved


def route_gateway_event(runtime: Any, event: Any) -> Any:
    return route_event(gateway_registry(runtime), event)


def gateway_state_snapshot(runtime: Any, *, limit: int = 20) -> Dict[str, Any]:
    return gateway_runtime_helpers_runtime.gateway_state_snapshot(runtime, limit=limit, build_gateway_diagnostics_fn=build_gateway_diagnostics)


def list_approval_tickets(runtime: Any, *, limit: int = 20, status: str | None = None) -> List[Any]:
    return runtime.gateway_state_store.list_approval_tickets(limit=limit, status=status)


def string_list(value: Any) -> List[str]:
    return gateway_diagnostics_runtime.string_list(value)


def workflow_result_details(workflow_run: Any) -> Dict[str, Any]:
    return gateway_diagnostics_runtime.workflow_result_details(workflow_run)


def merge_context(existing: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    return gateway_runtime_helper_runtime.merge_context(existing, updates)


def update_workflow_run_state(
    runtime: Any,
    workflow_run_id: str,
    *,
    status: str | None = None,
    current_step: str | None = None,
    result_summary: str | None = None,
    context_updates: Dict[str, Any] | None = None,
    finished: bool = False,
) -> Any | None:
    return gateway_runtime_helpers_runtime.update_workflow_run_state(runtime, workflow_run_id, status=status, current_step=current_step, result_summary=result_summary, context_updates=context_updates, finished=finished, update_workflow_run_record_fn=gateway_runtime_helper_runtime.update_workflow_run_record)


def filter_handler_kwargs(handler: Any, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    return gateway_runtime_helper_runtime.filter_handler_kwargs(handler, kwargs)


def normalized_workflow_result(raw_result: Any) -> Dict[str, Any]:
    return gateway_runtime_helper_runtime.normalized_workflow_result(raw_result)


def workflow_handler_registration(runtime: Any, decision: Any) -> Any | None:
    return gateway_runtime_helpers_runtime.workflow_handler_registration(runtime, decision)


def invoke_workflow_handler(
    runtime: Any,
    *,
    decision: Any,
    event: Any,
    workflow_run: Any,
) -> Dict[str, Any] | None:
    return gateway_runtime_helpers_runtime.invoke_workflow_handler(runtime, decision=decision, event=event, workflow_run=workflow_run, workflow_handler_registration_fn=workflow_handler_registration, filter_handler_kwargs_fn=filter_handler_kwargs, normalized_workflow_result_fn=normalized_workflow_result)


def dispatch_gateway_event(runtime: Any, event: Any) -> Dict[str, Any]:
    decision = runtime.route_gateway_event(event)
    workflow_run = (
        create_workflow_run(
            trigger=decision.trigger,
            event=event,
            status="pending",
            current_step="routed",
            metadata={"reason": decision.reason},
        )
        if decision.trigger is not None
        else None
    )
    if workflow_run is not None:
        workflow_run = gateway_runtime_helper_runtime.sync_workflow_run_with_run_manager(runtime, workflow_run)
    audit_records = gateway_runtime_helper_runtime.dispatch_gateway_event_artifacts(event, decision, workflow_run)
    workflow_result = None
    workflow_handler = workflow_handler_registration(runtime, decision)
    if workflow_run is not None and workflow_handler is not None:
        try:
            workflow_result = invoke_workflow_handler(
                runtime,
                decision=decision,
                event=event,
                workflow_run=workflow_run,
            )
            workflow_run, workflow_audit = gateway_runtime_helper_runtime.apply_workflow_success(
                workflow_run,
                workflow_result=dict(workflow_result or {}),
                decision=decision,
            )
            audit_records.append(workflow_audit)
        except Exception as exc:
            workflow_run, workflow_audit = gateway_runtime_helper_runtime.apply_workflow_failure(
                workflow_run,
                decision=decision,
                error_text=str(exc),
            )
            audit_records.append(workflow_audit)
    runtime.save_gateway_event(event)
    if workflow_run is not None:
        runtime.save_gateway_workflow_run(workflow_run)
    for item in audit_records:
        runtime.append_gateway_audit_record(item)
    return {
        "event": event,
        "decision": decision,
        "workflow_run": workflow_run,
        "workflow_result": workflow_result,
        "audit_records": audit_records,
    }


def recommendation_item(action_request: Any) -> Dict[str, Any]:
    return gateway_diagnostics_runtime.recommendation_item(action_request)


def execution_diagnostic(audit_record: Any | None) -> Dict[str, Any]:
    return gateway_diagnostics_runtime.execution_diagnostic(audit_record)


def approval_diagnostic(
    runtime: Any,
    approval_ticket: Any,
    *,
    action_requests_by_id: Dict[str, Any],
    audit_records: List[Any],
) -> Dict[str, Any]:
    return gateway_diagnostics_runtime.approval_diagnostic(
        runtime,
        approval_ticket,
        action_requests_by_id=action_requests_by_id,
        audit_records=audit_records,
    )


def workflow_diagnostic(
    runtime: Any,
    workflow_run: Any,
    *,
    action_requests: List[Any],
    approval_tickets_by_action_id: Dict[str, Any],
    audit_records: List[Any],
) -> Dict[str, Any]:
    return gateway_diagnostics_runtime.workflow_diagnostic(
        runtime,
        workflow_run,
        action_requests=action_requests,
        approval_tickets_by_action_id=approval_tickets_by_action_id,
        audit_records=audit_records,
    )


def build_gateway_diagnostics(
    runtime: Any,
    *,
    workflow_runs: List[Any],
    action_requests: List[Any],
    approval_tickets: List[Any],
    audit_records: List[Any],
) -> Dict[str, Any]:
    return gateway_diagnostics_runtime.build_gateway_diagnostics(
        runtime,
        workflow_runs=workflow_runs,
        action_requests=action_requests,
        approval_tickets=approval_tickets,
        audit_records=audit_records,
    )


def list_approval_diagnostics(runtime: Any, *, limit: int = 20, status: str | None = None) -> List[Dict[str, Any]]:
    return gateway_diagnostics_runtime.list_approval_diagnostics(
        runtime,
        limit=limit,
        status=status,
    )

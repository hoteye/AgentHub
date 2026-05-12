from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.gateway_server.request_scope import with_gateway_plugin_scope


def gateway_state_snapshot(
    runtime: Any,
    *,
    limit: int = 20,
    build_gateway_diagnostics_fn: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    safe_limit = max(1, int(limit))
    events = runtime.gateway_state_store.list_events(limit=safe_limit)
    workflow_runs = runtime.gateway_state_store.list_workflow_runs(limit=safe_limit)
    action_requests = runtime.gateway_state_store.list_action_requests(limit=safe_limit)
    approval_tickets = runtime.gateway_state_store.list_approval_tickets(limit=safe_limit)
    audit_records = runtime.gateway_state_store.list_audit_records(limit=safe_limit)
    return {
        "events": events,
        "workflow_runs": workflow_runs,
        "action_requests": action_requests,
        "approval_tickets": approval_tickets,
        "audit_records": audit_records,
        "diagnostics": build_gateway_diagnostics_fn(
            runtime,
            workflow_runs=workflow_runs,
            action_requests=action_requests,
            approval_tickets=approval_tickets,
            audit_records=audit_records,
        ),
    }


def update_workflow_run_state(
    runtime: Any,
    workflow_run_id: str,
    *,
    status: str | None = None,
    current_step: str | None = None,
    result_summary: str | None = None,
    context_updates: dict[str, Any] | None = None,
    finished: bool = False,
    update_workflow_run_record_fn: Callable[..., Any],
) -> Any | None:
    workflow_run = runtime.gateway_state_store.get_workflow_run(workflow_run_id)
    if workflow_run is None:
        return None
    updated = update_workflow_run_record_fn(
        workflow_run,
        status=status,
        current_step=current_step,
        result_summary=result_summary,
        context_updates=context_updates,
        finished=finished,
    )
    runtime.save_gateway_workflow_run(updated)
    return updated


def workflow_handler_registration(runtime: Any, decision: Any) -> Any | None:
    plugin_manager = getattr(runtime.tools, "_plugin_manager", None)
    if plugin_manager is None or decision.plugin_name is None or decision.workflow_name is None:
        return None
    getter = getattr(plugin_manager, "get_workflow_handler", None)
    if not callable(getter):
        return None
    return getter(plugin_name=decision.plugin_name, workflow_name=decision.workflow_name)


def invoke_workflow_handler(
    runtime: Any,
    *,
    decision: Any,
    event: Any,
    workflow_run: Any,
    workflow_handler_registration_fn: Callable[..., Any | None],
    filter_handler_kwargs_fn: Callable[..., dict[str, Any]],
    normalized_workflow_result_fn: Callable[[Any], dict[str, Any]],
) -> dict[str, Any] | None:
    registration = workflow_handler_registration_fn(runtime, decision)
    if registration is None:
        return None
    handler = getattr(registration, "handler", None)
    if not callable(handler):
        return None
    kwargs = filter_handler_kwargs_fn(
        handler,
        {
            "event": event,
            "decision": decision,
            "workflow_run": workflow_run,
            "runtime": runtime,
        },
    )
    plugin_name = str(decision.plugin_name or "").strip()
    if plugin_name:
        return with_gateway_plugin_scope(
            plugin_name,
            lambda: normalized_workflow_result_fn(handler(**kwargs)),
        )
    return normalized_workflow_result_fn(handler(**kwargs))

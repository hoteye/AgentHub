from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli.runtime_services import approval_resolution_action_runtime
from cli.agent_cli.runtime_services import approval_decision_runtime
from cli.agent_cli.runtime_services import approval_resolution_decision_handlers_runtime
from cli.agent_cli.runtime_services import approval_resolution_summary_runtime
from cli.agent_cli.gateway_core import create_action_request, create_audit_record
from shared.integrations import find_github_workflow_run, github_action_artifact_refs


def _preview_text(value: Any, *, max_chars: int = 120) -> str:
    return approval_resolution_summary_runtime.preview_text(value, max_chars=max_chars)


def background_teammate_summary_text(
    *,
    title: str,
    approval_id: str = "",
    task_id: str = "",
    status: str = "",
    task: str = "",
    provider: str = "",
    model: str = "",
    reasoning_effort: str = "",
    cwd: str = "",
    approval_policy: str = "",
    sandbox_mode: str = "",
    allowed_paths: list[str] | None = None,
    blocked_paths: list[str] | None = None,
    timeout_seconds: float | None = None,
    queue_provider: str = "",
    include_approval_commands: bool = False,
) -> str:
    return approval_resolution_summary_runtime.background_teammate_summary_text(
        title=title,
        approval_id=approval_id,
        task_id=task_id,
        status=status,
        task=task,
        provider=provider,
        model=model,
        reasoning_effort=reasoning_effort,
        cwd=cwd,
        approval_policy=approval_policy,
        sandbox_mode=sandbox_mode,
        allowed_paths=allowed_paths,
        blocked_paths=blocked_paths,
        timeout_seconds=timeout_seconds,
        queue_provider=queue_provider,
        include_approval_commands=include_approval_commands,
    )


def gateway_item_payload(item: Any) -> Dict[str, Any]:
    return approval_decision_runtime.gateway_item_payload(item)


def approval_decision_turn_events(
    approval_ticket: Any,
    action_request: Any,
    action_result: Any,
    *,
    item_index_start: int = 0,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    return approval_decision_runtime.approval_decision_turn_events(
        approval_ticket,
        action_request,
        action_result,
        item_index_start=item_index_start,
    )


def execute_gateway_action_now(
    runtime: Any,
    action_request: Any,
    *,
    approval_id: str | None = None,
) -> Dict[str, Any]:
    action_result, execution_details = approval_resolution_action_runtime.execute_gateway_action_details(
        runtime,
        action_request,
    )
    audit_record = create_audit_record(
        trace_id=action_request.trace_id,
        stage="action_execute",
        status="ok" if action_result.ok else "failed",
        summary=action_result.summary,
        event_id=action_request.event_id,
        workflow_run_id=action_request.workflow_run_id,
        action_id=action_request.action_id,
        approval_id=approval_id,
        details=execution_details,
    )
    runtime.append_gateway_audit_record(audit_record)
    return {
        "action_result": action_result,
        "audit_record": audit_record,
    }


def record_gateway_action_denied(
    runtime: Any,
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
    action_request = create_action_request(
        action_type=action_type,
        connector_key=connector_key,
        plugin_name=plugin_name,
        trace_id=trace_id,
        requested_by=requested_by,
        payload=request_payload,
        metadata={**dict(metadata or {}), "decision": "denied"},
        approval_required=False,
        workflow_run_id=workflow_run_id,
        event_id=event_id,
    )
    runtime.save_gateway_action_request(action_request)
    audit_records = [
        approval_resolution_action_runtime.denied_action_request_audit_record(
            trace_id=trace_id,
            summary=summary,
            action_request=action_request,
            plugin_name=plugin_name,
            connector_key=connector_key,
            requested_by=requested_by,
            reason=reason,
            event_id=event_id,
            workflow_run_id=workflow_run_id,
        )
    ]
    for item in audit_records:
        runtime.append_gateway_audit_record(item)
    return {
        "action_request": action_request,
        "audit_records": audit_records,
    }


def decide_patch_approval(
    runtime: Any,
    approval_id: str,
    *,
    approved: bool | None = None,
    decision: Any = None,
    decided_by: str,
    decision_note: str = "",
) -> Dict[str, Any]:
    return approval_resolution_decision_handlers_runtime.decide_patch_approval(
        runtime,
        approval_id,
        approved=approved,
        decision=decision,
        decided_by=decided_by,
        decision_note=decision_note,
    )


def decide_shell_approval(
    runtime: Any,
    approval_id: str,
    *,
    approved: bool | None = None,
    decision: Any = None,
    decided_by: str,
    decision_note: str = "",
) -> Dict[str, Any]:
    return approval_resolution_decision_handlers_runtime.decide_shell_approval(
        runtime,
        approval_id,
        approved=approved,
        decision=decision,
        decided_by=decided_by,
        decision_note=decision_note,
    )


def decide_background_teammate_approval(
    runtime: Any,
    approval_id: str,
    *,
    approved: bool | None = None,
    decision: Any = None,
    decided_by: str,
    decision_note: str = "",
) -> Dict[str, Any]:
    return approval_resolution_decision_handlers_runtime.decide_background_teammate_approval(
        runtime,
        approval_id,
        approved=approved,
        decision=decision,
        decided_by=decided_by,
        decision_note=decision_note,
    )


def decide_gateway_approval(
    runtime: Any,
    approval_id: str,
    *,
    approved: bool | None = None,
    decision: Any = None,
    decided_by: str,
    decision_note: str = "",
    github_action_artifact_refs_fn: Any = github_action_artifact_refs,
    find_github_workflow_run_fn: Any = find_github_workflow_run,
) -> Dict[str, Any]:
    return approval_resolution_decision_handlers_runtime.decide_gateway_approval(
        runtime,
        approval_id,
        approved=approved,
        decision=decision,
        decided_by=decided_by,
        decision_note=decision_note,
        github_action_artifact_refs_fn=github_action_artifact_refs_fn,
        find_github_workflow_run_fn=find_github_workflow_run_fn,
    )

from __future__ import annotations

from typing import Any

from cli.agent_cli import approval_contract_runtime
from cli.agent_cli.runtime_services import (
    approval_continuation_runtime,
    approval_projection_runtime,
    approval_resolution_action_runtime,
    approval_resolution_diagnostics_runtime,
    approval_resolution_execution_runtime,
    approval_resolution_gateway_runtime,
    approval_resolution_helpers_runtime,
)
from cli.agent_cli.runtime_services import (
    approval_resolution_decision_shared_runtime as decision_shared_runtime,
)
from cli.agent_cli.runtime_services.approval_browser_runtime import action_request_details
from shared.integrations import find_github_workflow_run, github_action_artifact_refs


def decide_patch_approval(
    runtime: Any,
    approval_id: str,
    *,
    approved: bool | None = None,
    decision: Any = None,
    decided_by: str,
    decision_note: str = "",
) -> dict[str, Any]:
    approval_ticket, action_request = decision_shared_runtime.pending_approval_context(
        runtime, approval_id
    )
    normalized_decision = decision_shared_runtime.normalized_approval_decision(
        approval_ticket,
        approved=approved,
        decision=decision,
    )
    approved = approval_contract_runtime.is_approval_accepting(normalized_decision)
    updated_ticket = decision_shared_runtime.decided_approval_ticket(
        approval_ticket,
        decision=normalized_decision,
        decided_by=decided_by,
        decision_note=decision_note,
    )
    runtime.save_gateway_approval_ticket(updated_ticket)
    decision_shared_runtime.store_session_approval(
        runtime, approval_ticket, decision=normalized_decision
    )
    audit_records = [
        approval_resolution_diagnostics_runtime.approval_decision_audit_record(
            updated_ticket,
            action_request,
            summary=f"{updated_ticket.status} {str(updated_ticket.decision_type or 'accept').strip()} apply_patch",
        )
    ]
    apply_event = None
    action_result: dict[str, Any] | None = None
    if approved:
        apply_event = runtime.tools.apply_patch(
            str((action_request.payload or {}).get("patch_text") or "")
        )
        action_result = approval_resolution_diagnostics_runtime.tool_event_action_result(
            apply_event,
            action="apply_patch",
        )
        audit_records.append(
            approval_resolution_diagnostics_runtime.tool_event_execution_audit_record(
                updated_ticket,
                action_request,
                apply_event,
            )
        )
    approval_resolution_helpers_runtime.append_audit_records(runtime, audit_records)
    response = approval_resolution_helpers_runtime.approval_resolution_response(
        updated_ticket,
        action_request,
        action_result,
        audit_records,
        extra_events=[apply_event] if apply_event is not None else [],
    )
    response["continuation"] = approval_continuation_runtime.prepare_resume_after_approval(
        runtime,
        approval_id=approval_id,
        decision_response=response,
    )
    for event in list(response.get("tool_events") or []):
        if isinstance(getattr(event, "payload", None), dict):
            event.payload.setdefault("continuation", dict(response["continuation"] or {}))
    return response


def decide_shell_approval(
    runtime: Any,
    approval_id: str,
    *,
    approved: bool | None = None,
    decision: Any = None,
    decided_by: str,
    decision_note: str = "",
) -> dict[str, Any]:
    approval_ticket, action_request = decision_shared_runtime.pending_approval_context(
        runtime, approval_id
    )
    normalized_decision = decision_shared_runtime.normalized_approval_decision(
        approval_ticket,
        approved=approved,
        decision=decision,
    )
    approved = approval_contract_runtime.is_approval_accepting(normalized_decision)
    updated_ticket = decision_shared_runtime.decided_approval_ticket(
        approval_ticket,
        decision=normalized_decision,
        decided_by=decided_by,
        decision_note=decision_note,
    )
    runtime.save_gateway_approval_ticket(updated_ticket)
    decision_shared_runtime.store_session_approval(
        runtime, approval_ticket, decision=normalized_decision
    )
    persisted_rule = decision_shared_runtime.persist_exec_policy_amendment(
        runtime,
        action_request,
        decision=normalized_decision,
    )
    audit_records = [
        approval_resolution_diagnostics_runtime.approval_decision_audit_record(
            updated_ticket,
            action_request,
            summary=f"{updated_ticket.status} {str(updated_ticket.decision_type or 'accept').strip()} shell command",
            extra_details=(
                {"persisted_rule": persisted_rule} if persisted_rule is not None else None
            ),
        )
    ]
    shell_event = None
    action_result: dict[str, Any] | None = None
    if approved:
        payload = dict(action_request.payload or {})
        shell_event, normalized_exec_mode = (
            approval_resolution_execution_runtime.execute_shell_approval_action(
                runtime,
                payload,
            )
        )
        action_result = approval_resolution_diagnostics_runtime.tool_event_action_result(
            shell_event,
            action=(
                "shell_command_start"
                if normalized_exec_mode == "session_start"
                else "shell_command"
            ),
        )
        audit_records.append(
            approval_resolution_diagnostics_runtime.tool_event_execution_audit_record(
                updated_ticket,
                action_request,
                shell_event,
            )
        )
    approval_resolution_helpers_runtime.append_audit_records(runtime, audit_records)
    response = approval_resolution_helpers_runtime.approval_resolution_response(
        updated_ticket,
        action_request,
        action_result,
        audit_records,
        payload_updates=approval_resolution_helpers_runtime.shell_payload_updates(
            runtime, action_request
        ),
        extra_events=[shell_event] if shell_event is not None else [],
    )
    response["continuation"] = approval_continuation_runtime.prepare_resume_after_approval(
        runtime,
        approval_id=approval_id,
        decision_response=response,
    )
    for event in list(response.get("tool_events") or []):
        if isinstance(getattr(event, "payload", None), dict):
            event.payload.setdefault("continuation", dict(response["continuation"] or {}))
    return response


def decide_background_teammate_approval(
    runtime: Any,
    approval_id: str,
    *,
    approved: bool | None = None,
    decision: Any = None,
    decided_by: str,
    decision_note: str = "",
) -> dict[str, Any]:
    from cli.agent_cli.background_tasks import enqueue_background_task

    approval_ticket, action_request = decision_shared_runtime.pending_approval_context(
        runtime, approval_id
    )
    normalized_decision = decision_shared_runtime.normalized_approval_decision(
        approval_ticket,
        approved=approved,
        decision=decision,
    )
    approved = approval_contract_runtime.is_approval_accepting(normalized_decision)
    updated_ticket = decision_shared_runtime.decided_approval_ticket(
        approval_ticket,
        decision=normalized_decision,
        decided_by=decided_by,
        decision_note=decision_note,
    )
    runtime.save_gateway_approval_ticket(updated_ticket)
    payload = dict(action_request.payload or {})
    audit_records = [
        approval_resolution_diagnostics_runtime.approval_decision_audit_record(
            updated_ticket,
            action_request,
            summary=f"{updated_ticket.status} {str(updated_ticket.decision_type or 'accept').strip()} background teammate",
            extra_details=approval_resolution_helpers_runtime.background_teammate_audit_details(
                payload
            ),
        )
    ]
    submit_event = None
    action_result: dict[str, Any] | None = None
    if approved:
        try:
            handle = enqueue_background_task(
                task_type="teammate",
                payload=approval_resolution_helpers_runtime.background_teammate_enqueue_payload(
                    payload
                ),
                source="cli",
                cwd=str(payload.get("queue_cwd") or "").strip() or getattr(runtime, "cwd", None),
                force_enable=True,
                metadata=approval_resolution_helpers_runtime.background_teammate_enqueue_metadata(
                    payload
                ),
            )
            submit_event = approval_resolution_action_runtime.background_teammate_submit_event(
                payload=payload,
                handle=handle,
            )
        except Exception as exc:
            submit_event = approval_resolution_action_runtime.background_teammate_submit_event(
                payload=payload,
                error=str(exc),
            )
        action_result = approval_resolution_diagnostics_runtime.tool_event_action_result(
            submit_event,
            action="background_teammate_enqueue",
        )
        audit_records.append(
            approval_resolution_diagnostics_runtime.tool_event_execution_audit_record(
                updated_ticket,
                action_request,
                submit_event,
            )
        )
    approval_resolution_helpers_runtime.append_audit_records(runtime, audit_records)
    return approval_resolution_helpers_runtime.approval_resolution_response(
        updated_ticket,
        action_request,
        action_result,
        audit_records,
        payload_updates=approval_resolution_helpers_runtime.background_teammate_payload_updates(
            payload
        ),
        extra_events=[submit_event] if submit_event is not None else [],
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
) -> dict[str, Any]:
    approval_ticket, action_request = decision_shared_runtime.pending_approval_context(
        runtime, approval_id
    )
    normalized_decision = decision_shared_runtime.normalized_approval_decision(
        approval_ticket,
        approved=approved,
        decision=decision,
    )
    approved = approval_contract_runtime.is_approval_accepting(normalized_decision)
    updated_ticket = decision_shared_runtime.decided_approval_ticket(
        approval_ticket,
        decision=normalized_decision,
        decided_by=decided_by,
        decision_note=decision_note,
    )
    decision_outcome = decision_shared_runtime.gateway_decision_outcome_from_approval_ticket(
        updated_ticket
    )
    runtime.save_gateway_approval_ticket(updated_ticket)
    decision_shared_runtime.store_session_approval(
        runtime, approval_ticket, decision=normalized_decision
    )
    audit_records = [
        approval_resolution_diagnostics_runtime.approval_decision_audit_record(
            updated_ticket,
            action_request,
            summary=(
                f"{updated_ticket.status} "
                f"{str(updated_ticket.decision_type or 'accept').strip()} "
                f"{action_request.action_type}"
            ),
            extra_details=action_request_details(action_request),
        )
    ]
    decision_shared_runtime.project_gateway_decision_outcome_into_approval_audit(
        audit_records,
        decision_outcome=decision_outcome,
        approved=approved,
    )
    action_result = None
    artifact_refs: list[str] = []
    execution_summary = ""
    if approved:
        execution = approval_resolution_gateway_runtime.execute_approved_gateway_action(
            runtime,
            action_request,
            updated_ticket,
            github_action_artifact_refs_fn=github_action_artifact_refs_fn,
            find_github_workflow_run_fn=find_github_workflow_run_fn,
        )
        action_result = execution["action_result"]
        updated_ticket = execution["approval_ticket"]
        artifact_refs = execution["artifact_refs"]
        execution_status = execution["execution_status"]
        execution_summary = execution["execution_summary"]
        execution_details = execution["execution_details"]
        audit_records.append(
            approval_resolution_execution_runtime.approved_gateway_execution_audit_record(
                updated_ticket,
                action_request,
                execution_status=execution_status,
                execution_summary=execution_summary,
                execution_details=execution_details,
            )
        )
    approval_resolution_gateway_runtime.update_browser_workflow_terminal_state(
        runtime,
        action_request,
        updated_ticket,
        approved=approved,
        action_result=action_result,
        artifact_refs=artifact_refs,
        execution_summary=execution_summary,
    )
    approval_resolution_helpers_runtime.append_audit_records(runtime, audit_records)
    response = approval_projection_runtime.approval_resolution_response(
        updated_ticket,
        action_request,
        action_result,
        audit_records,
    )
    response["decision_outcome"] = decision_outcome
    return response

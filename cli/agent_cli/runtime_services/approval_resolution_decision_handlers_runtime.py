from __future__ import annotations

from typing import Any, Dict

from cli.agent_cli import approval_contract_runtime
from cli.agent_cli import runtime_exec_policy_rules
from cli.agent_cli.runtime_services.approval_browser_runtime import action_request_details
from cli.agent_cli.runtime_services import approval_projection_runtime
from cli.agent_cli.runtime_services import approval_continuation_runtime
from cli.agent_cli.runtime_services import approval_resolution_action_runtime
from cli.agent_cli.runtime_services import approval_resolution_diagnostics_runtime
from cli.agent_cli.runtime_services import approval_resolution_execution_runtime
from cli.agent_cli.runtime_services import approval_resolution_gateway_runtime
from cli.agent_cli.runtime_services import approval_resolution_helpers_runtime
from shared.integrations import find_github_workflow_run, github_action_artifact_refs


def _pending_approval_context(runtime: Any, approval_id: str) -> tuple[Any, Any]:
    return approval_resolution_helpers_runtime.pending_approval_context(runtime, approval_id)


def _decided_approval_ticket(
    approval_ticket: Any,
    *,
    decision: Any,
    decided_by: str,
    decision_note: str,
) -> Any:
    return approval_resolution_helpers_runtime.decided_approval_ticket(
        approval_ticket,
        decision=decision,
        decided_by=decided_by,
        decision_note=decision_note,
    )


def _normalized_approval_decision(
    approval_ticket: Any,
    *,
    approved: bool | None = None,
    decision: Any = None,
) -> Dict[str, Any]:
    resolved_decision = decision
    if resolved_decision is None:
        resolved_decision = (
            approval_contract_runtime.APPROVAL_DECISION_ACCEPT
            if bool(approved)
            else approval_contract_runtime.APPROVAL_DECISION_DECLINE
        )
    return approval_contract_runtime.merge_available_decision(
        available_decisions=getattr(approval_ticket, "available_decisions", None),
        decision=resolved_decision,
        fallback_proposed_rule=(
            dict(getattr(approval_ticket, "proposed_rule", {}) or {})
            if isinstance(getattr(approval_ticket, "proposed_rule", None), dict)
            else None
        ),
    )


def _store_session_approval(runtime: Any, approval_ticket: Any, *, decision: Dict[str, Any]) -> None:
    approval_contract_runtime.store_session_approval(
        runtime,
        session_cache_keys=list(getattr(approval_ticket, "session_cache_keys", []) or []),
        grant_root=str(getattr(approval_ticket, "grant_root", "") or "").strip() or None,
        decision=decision,
    )


def _persist_exec_policy_amendment(runtime: Any, action_request: Any, *, decision: Dict[str, Any]) -> Dict[str, Any] | None:
    if str(decision.get("type") or "").strip() != approval_contract_runtime.APPROVAL_DECISION_ACCEPT_WITH_EXECPOLICY_AMENDMENT:
        return None
    proposed_rule = approval_contract_runtime.approval_execpolicy_amendment_rule(
        dict(decision.get("proposed_rule") or {})
        if isinstance(decision.get("proposed_rule"), dict)
        else None
    )
    if proposed_rule is None:
        return None
    payload = dict(getattr(action_request, "payload", None) or {})
    source_metadata = dict(proposed_rule.get("source_metadata") or {})
    source_metadata.update(
        {
            "action_id": str(getattr(action_request, "action_id", "") or "").strip() or None,
            "action_type": str(getattr(action_request, "action_type", "") or "").strip() or None,
            "trace_id": str(getattr(action_request, "trace_id", "") or "").strip() or None,
        }
    )
    normalized_rule = runtime_exec_policy_rules.append_runtime_exec_policy_rule(
        {
            **dict(proposed_rule),
            "decision": "allow",
            "source": str(proposed_rule.get("source") or "user").strip() or "user",
            "justification": str(proposed_rule.get("justification") or "approved via cli approval").strip(),
            "source_metadata": source_metadata,
        },
        cwd=str(payload.get("cwd") or "").strip() or getattr(runtime, "cwd", None),
    )
    return normalized_rule.to_dict()


def _gateway_decision_outcome_from_approval_ticket(approval_ticket: Any) -> str:
    status = str(getattr(approval_ticket, "status", "") or "").strip().lower()
    note = str(getattr(approval_ticket, "decision_note", "") or "").strip().lower()
    if status == "approved":
        return "approved"
    if "timeout" in note:
        return "timed_out"
    if "expired" in note:
        return "expired"
    if status == "rejected":
        return "rejected"
    return status or "rejected"


def _project_gateway_decision_outcome_into_approval_audit(
    audit_records: list[Any],
    *,
    decision_outcome: str,
    approved: bool,
) -> None:
    for audit_record in list(audit_records or []):
        if str(getattr(audit_record, "stage", "")).strip() != "approval":
            continue
        details = getattr(audit_record, "details", None)
        if not isinstance(details, dict):
            continue
        details["decision_outcome"] = decision_outcome
        details["execution_skipped"] = not approved
        break


def decide_patch_approval(
    runtime: Any,
    approval_id: str,
    *,
    approved: bool | None = None,
    decision: Any = None,
    decided_by: str,
    decision_note: str = "",
) -> Dict[str, Any]:
    approval_ticket, action_request = _pending_approval_context(runtime, approval_id)
    normalized_decision = _normalized_approval_decision(
        approval_ticket,
        approved=approved,
        decision=decision,
    )
    approved = approval_contract_runtime.is_approval_accepting(normalized_decision)
    updated_ticket = _decided_approval_ticket(
        approval_ticket,
        decision=normalized_decision,
        decided_by=decided_by,
        decision_note=decision_note,
    )
    runtime.save_gateway_approval_ticket(updated_ticket)
    _store_session_approval(runtime, approval_ticket, decision=normalized_decision)
    audit_records = [
        approval_resolution_diagnostics_runtime.approval_decision_audit_record(
            updated_ticket,
            action_request,
            summary=f"{updated_ticket.status} {str(updated_ticket.decision_type or 'accept').strip()} apply_patch",
        )
    ]
    apply_event = None
    action_result: Dict[str, Any] | None = None
    if approved:
        apply_event = runtime.tools.apply_patch(str((action_request.payload or {}).get("patch_text") or ""))
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
) -> Dict[str, Any]:
    approval_ticket, action_request = _pending_approval_context(runtime, approval_id)
    normalized_decision = _normalized_approval_decision(
        approval_ticket,
        approved=approved,
        decision=decision,
    )
    approved = approval_contract_runtime.is_approval_accepting(normalized_decision)
    updated_ticket = _decided_approval_ticket(
        approval_ticket,
        decision=normalized_decision,
        decided_by=decided_by,
        decision_note=decision_note,
    )
    runtime.save_gateway_approval_ticket(updated_ticket)
    _store_session_approval(runtime, approval_ticket, decision=normalized_decision)
    persisted_rule = _persist_exec_policy_amendment(
        runtime,
        action_request,
        decision=normalized_decision,
    )
    audit_records = [
        approval_resolution_diagnostics_runtime.approval_decision_audit_record(
            updated_ticket,
            action_request,
            summary=f"{updated_ticket.status} {str(updated_ticket.decision_type or 'accept').strip()} shell command",
            extra_details={"persisted_rule": persisted_rule} if persisted_rule is not None else None,
        )
    ]
    shell_event = None
    action_result: Dict[str, Any] | None = None
    if approved:
        payload = dict(action_request.payload or {})
        shell_event, normalized_exec_mode = approval_resolution_execution_runtime.execute_shell_approval_action(
            runtime,
            payload,
        )
        action_result = approval_resolution_diagnostics_runtime.tool_event_action_result(
            shell_event,
            action="shell_command_start" if normalized_exec_mode == "session_start" else "shell_command",
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
        payload_updates=approval_resolution_helpers_runtime.shell_payload_updates(runtime, action_request),
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
) -> Dict[str, Any]:
    from cli.agent_cli.background_tasks import enqueue_background_task

    approval_ticket, action_request = _pending_approval_context(runtime, approval_id)
    normalized_decision = _normalized_approval_decision(
        approval_ticket,
        approved=approved,
        decision=decision,
    )
    approved = approval_contract_runtime.is_approval_accepting(normalized_decision)
    updated_ticket = _decided_approval_ticket(
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
            extra_details=approval_resolution_helpers_runtime.background_teammate_audit_details(payload),
        )
    ]
    submit_event = None
    action_result: Dict[str, Any] | None = None
    if approved:
        try:
            handle = enqueue_background_task(
                task_type="teammate",
                payload=approval_resolution_helpers_runtime.background_teammate_enqueue_payload(payload),
                source="cli",
                cwd=str(payload.get("queue_cwd") or "").strip() or getattr(runtime, "cwd", None),
                force_enable=True,
                metadata=approval_resolution_helpers_runtime.background_teammate_enqueue_metadata(payload),
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
        payload_updates=approval_resolution_helpers_runtime.background_teammate_payload_updates(payload),
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
) -> Dict[str, Any]:
    approval_ticket, action_request = _pending_approval_context(runtime, approval_id)
    normalized_decision = _normalized_approval_decision(
        approval_ticket,
        approved=approved,
        decision=decision,
    )
    approved = approval_contract_runtime.is_approval_accepting(normalized_decision)
    updated_ticket = _decided_approval_ticket(
        approval_ticket,
        decision=normalized_decision,
        decided_by=decided_by,
        decision_note=decision_note,
    )
    decision_outcome = _gateway_decision_outcome_from_approval_ticket(updated_ticket)
    runtime.save_gateway_approval_ticket(updated_ticket)
    _store_session_approval(runtime, approval_ticket, decision=normalized_decision)
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
    _project_gateway_decision_outcome_into_approval_audit(
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

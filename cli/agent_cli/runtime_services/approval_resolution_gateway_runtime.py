from __future__ import annotations

from typing import Any, Dict, List

from cli.agent_cli.runtime_services.approval_browser_runtime import (
    browser_artifact_refs,
    browser_request_from_action_request,
    execute_browser_gateway_action,
)
from cli.agent_cli.runtime_services import approval_ticket_runtime
from shared.integrations import find_github_workflow_run, github_action_artifact_refs
from workers.actions import ActionError, ActionResult


def _decision_outcome_from_approval_ticket(approval_ticket: Any) -> str:
    status = str(getattr(approval_ticket, "status", "") or "").strip().lower()
    note = str(getattr(approval_ticket, "decision_note", "") or "").strip().lower()
    normalized_note = note.replace("-", " ").replace("_", " ")
    if status == "approved":
        return "approved"
    if status in {"timed_out", "timeout"} or "timeout" in normalized_note or "timed out" in normalized_note:
        return "timed_out"
    if status in {"expired", "expire"} or "expired" in normalized_note or "expire" in normalized_note:
        return "expired"
    if status == "rejected":
        return "rejected"
    return status or "rejected"


def _gateway_execution_contract(action_request: Any, approval_ticket: Any) -> Dict[str, Any]:
    action_family = str(getattr(action_request, "action_family", "") or "").strip()
    action_type = str(getattr(action_request, "action_type", "") or "").strip()
    if not action_family and action_type.startswith("browser."):
        action_family = "browser"
    elif not action_family and action_type.startswith("mcp."):
        action_family = "mcp"
    elif not action_family:
        action_family = "gateway"
    tool_family = "gateway_action"
    source = "gateway"
    if action_family == "mcp":
        tool_family = "mcp_tool_call"
        source = "mcp"
    return {
        "source": source,
        "tool_family": tool_family,
        "action_family": action_family,
        "action_type": action_type,
        "decision_outcome": _decision_outcome_from_approval_ticket(approval_ticket),
        "connector_key": str(getattr(action_request, "connector_key", "") or "").strip(),
        "plugin_name": str(getattr(action_request, "plugin_name", "") or "").strip(),
        "approval_id": str(getattr(approval_ticket, "approval_id", "") or "").strip(),
        "approval_required": True,
        "requires_confirmation": True,
        "mutates_ui": bool(action_family == "browser"),
    }


def _execution_details_for_outcome(decision_outcome: str, base_details: Dict[str, Any]) -> Dict[str, Any]:
    details = dict(base_details)
    details["decision_outcome"] = decision_outcome
    return details


def is_browser_action_request(action_request: Any) -> bool:
    return getattr(action_request, "action_family", None) == "browser" or str(
        action_request.action_type or ""
    ).startswith("browser.")


def is_mcp_tool_action_request(action_request: Any) -> bool:
    return getattr(action_request, "action_family", None) == "mcp" or str(
        action_request.action_type or ""
    ).startswith("mcp.")


def _extract_mcp_tool_call_payload(action_request: Any) -> tuple[str, Dict[str, Any]]:
    payload = dict(getattr(action_request, "payload", None) or {})
    projected_name = str(payload.get("projected_name") or payload.get("projectedName") or "").strip()
    arguments = payload.get("arguments")
    if not isinstance(arguments, dict):
        arguments = {}
    return projected_name, dict(arguments)


def _execute_mcp_tool_action(runtime: Any, action_request: Any) -> ActionResult:
    projected_name, arguments = _extract_mcp_tool_call_payload(action_request)
    if not projected_name:
        raise ActionError("missing projected_name for mcp tool approval request")
    getter = getattr(runtime, "get_mcp_runtime", None)
    mcp_runtime = getter() if callable(getter) else getattr(runtime, "_mcp_runtime", None)
    if mcp_runtime is None:
        raise ActionError("mcp runtime unavailable")
    call = getattr(mcp_runtime, "call_projected_tool", None)
    if not callable(call):
        raise ActionError("mcp runtime unavailable")
    payload = call(projected_name=projected_name, arguments=arguments)
    ok = bool(payload.get("ok"))
    summary = (
        f"mcp tool call approved {projected_name}"
        if ok
        else f"mcp tool call failed {projected_name}: {str(payload.get('error') or '').strip() or 'unknown error'}"
    )
    return ActionResult(
        ok=ok,
        action="mcp.tool.call",
        summary=summary,
        output=dict(payload),
        error=str(payload.get("error") or "").strip() or None,
    )


def execute_approved_gateway_action(
    runtime: Any,
    action_request: Any,
    approval_ticket: Any,
    *,
    github_action_artifact_refs_fn: Any = github_action_artifact_refs,
    find_github_workflow_run_fn: Any = find_github_workflow_run,
) -> Dict[str, Any]:
    artifact_refs: List[str] = []
    execution_contract = _gateway_execution_contract(action_request, approval_ticket)
    decision_outcome = str(execution_contract.get("decision_outcome") or "approved")

    try:
        if is_browser_action_request(action_request):
            action_result = execute_browser_gateway_action(runtime, action_request)
            base_details = {
                "output": action_result.output,
                "execution_contract": dict(execution_contract),
                "browser_execution": {
                    "action_type": action_request.action_type,
                    "action_class": getattr(action_request, "action_class", None),
                    "approval_policy": getattr(action_request, "approval_policy", None),
                    "audit_stage": getattr(action_request, "audit_stage", None),
                    "request": browser_request_from_action_request(action_request),
                    "result_ok": action_result.ok,
                },
            }
            execution_details = _execution_details_for_outcome(decision_outcome, base_details)
            artifact_refs.extend(browser_artifact_refs(action_result.output))
        elif is_mcp_tool_action_request(action_request):
            action_result = _execute_mcp_tool_action(runtime, action_request)
            base_details = {
                "output": action_result.output,
                "execution_contract": dict(execution_contract),
                "mcp_execution": {
                    "projected_name": str(action_result.output.get("projected_name") or "").strip(),
                    "server_name": str(action_result.output.get("server_name") or "").strip(),
                    "remote_name": str(action_result.output.get("remote_name") or "").strip(),
                    "approval": dict(action_result.output.get("approval") or {}),
                },
            }
            execution_details = _execution_details_for_outcome(decision_outcome, base_details)
        else:
            action_result = runtime.action_worker.execute(action_request.payload)
            base_details = {
                "output": action_result.output,
                "execution_contract": dict(execution_contract),
            }
            execution_details = _execution_details_for_outcome(decision_outcome, base_details)

        execution_status = "ok" if action_result.ok else "failed"
        execution_summary = action_result.summary

        if action_result.ok and action_request.plugin_name == "github_phase1":
            artifact_payload = github_action_artifact_refs_fn(
                action_type=action_request.action_type,
                request_payload=action_request.payload,
                action_output=action_result.output,
            )
            artifact_refs.extend(list(artifact_payload.get("artifact_refs") or []))
            if artifact_payload.get("details"):
                execution_details["github_artifacts"] = artifact_payload["details"]
            if action_request.action_type == "github.workflow.dispatch":
                workflow_run = find_github_workflow_run_fn(
                    request_payload=action_request.payload,
                    trace_id=approval_ticket.trace_id,
                    occurred_after=approval_ticket.decision_at,
                )
                if workflow_run is not None:
                    workflow_url = str(workflow_run.get("html_url") or "").strip()
                    if workflow_url:
                        artifact_refs.append(workflow_url)
                    execution_details["github_workflow_run"] = workflow_run
    except ActionError as exc:
        action_result = None
        execution_status = "failed"
        execution_summary = str(exc)
        base_details = {
            "error": str(exc),
            "execution_contract": dict(execution_contract),
        }
        execution_details = _execution_details_for_outcome(decision_outcome, base_details)

    deduped_artifact_refs = list(dict.fromkeys(item for item in artifact_refs if item))
    updated_ticket = approval_ticket
    if deduped_artifact_refs:
        execution_details["artifact_refs"] = deduped_artifact_refs
        updated_ticket = approval_ticket_runtime.merge_approval_evidence_refs(
            approval_ticket,
            deduped_artifact_refs,
        )
        runtime.save_gateway_approval_ticket(updated_ticket)

    return {
        "action_result": action_result,
        "approval_ticket": updated_ticket,
        "artifact_refs": deduped_artifact_refs,
        "execution_status": execution_status,
        "execution_summary": execution_summary,
        "execution_details": execution_details,
    }


def update_browser_workflow_terminal_state(
    runtime: Any,
    action_request: Any,
    approval_ticket: Any,
    *,
    approved: bool,
    action_result: Any,
    artifact_refs: List[str] | None = None,
    execution_summary: str = "",
) -> None:
    if not is_browser_action_request(action_request) or not action_request.workflow_run_id:
        return

    deduped_artifact_refs = list(dict.fromkeys(item for item in list(artifact_refs or []) if item))
    terminal_status = "rejected"
    terminal_step = "approval_rejected"
    terminal_summary = f"{approval_ticket.status} {action_request.action_type}"
    context_updates: Dict[str, Any] = {
        "browser_workflow": {
            "status": "rejected" if not approved else "completed",
            "approval_status": approval_ticket.status,
            "pending_action_id": action_request.action_id,
            "pending_approval_id": approval_ticket.approval_id,
        },
        "workflow_result": {
            "status": "rejected" if not approved else ("ok" if action_result and action_result.ok else "failed"),
            "action_request_count": 1,
        },
    }
    if approved:
        terminal_status = "ok" if action_result and action_result.ok else "failed"
        terminal_step = "browser_action_executed" if terminal_status == "ok" else "browser_action_failed"
        terminal_summary = execution_summary
        context_updates["browser_workflow"]["last_execution"] = {
            "status": terminal_status,
            "summary": execution_summary,
            "artifact_refs": deduped_artifact_refs,
        }
        context_updates["workflow_result"]["evidence_refs"] = deduped_artifact_refs

    runtime.update_workflow_run_state(
        action_request.workflow_run_id,
        status=terminal_status,
        current_step=terminal_step,
        result_summary=terminal_summary,
        context_updates=context_updates,
        finished=True,
    )

from __future__ import annotations

from typing import Any, Dict

from cli.agent_cli.gateway_core import create_audit_record
from cli.agent_cli.models import ToolEvent
from cli.agent_cli.runtime_services.approval_browser_runtime import (
    browser_artifact_refs,
    browser_request_from_action_request,
    execute_browser_gateway_action,
)
from cli.agent_cli.runtime_services import approval_resolution_summary_runtime


def execute_gateway_action_details(
    runtime: Any,
    action_request: Any,
) -> tuple[Any, Dict[str, Any]]:
    if getattr(action_request, "action_family", None) == "browser" or str(action_request.action_type or "").startswith("browser."):
        action_result = execute_browser_gateway_action(runtime, action_request)
        execution_details = {
            "output": action_result.output,
            "browser_execution": {
                "action_type": action_request.action_type,
                "action_class": getattr(action_request, "action_class", None),
                "approval_policy": getattr(action_request, "approval_policy", None),
                "audit_stage": getattr(action_request, "audit_stage", None),
                "request": browser_request_from_action_request(action_request),
                "result_ok": action_result.ok,
            },
        }
        artifact_refs = browser_artifact_refs(action_result.output)
        if artifact_refs:
            execution_details["artifact_refs"] = artifact_refs
        return action_result, execution_details
    action_result = runtime.action_worker.execute(action_request.payload)
    return action_result, {"output": action_result.output}


def denied_action_request_audit_record(
    *,
    trace_id: str,
    summary: str,
    action_request: Any,
    plugin_name: str,
    connector_key: str,
    requested_by: str,
    reason: str,
    event_id: str | None = None,
    workflow_run_id: str | None = None,
) -> Any:
    return create_audit_record(
        trace_id=trace_id,
        stage="action_request",
        status="denied",
        summary=summary,
        event_id=event_id,
        workflow_run_id=workflow_run_id,
        action_id=action_request.action_id,
        details={
            "plugin_name": plugin_name,
            "connector_key": connector_key,
            "requested_by": requested_by,
            "reason": reason,
        },
    )


def background_teammate_submit_event(
    *,
    payload: Dict[str, Any],
    handle: Any | None = None,
    error: str | None = None,
) -> ToolEvent:
    ok = handle is not None and not error
    submit_payload = approval_resolution_summary_runtime.background_teammate_submit_payload(
        payload=payload,
        task_id=str(getattr(handle, "task_id", "") or "").strip(),
        status=(
            str(getattr(handle, "status", "") or "").strip()
            if handle is not None
            else "failed"
        ),
        job_id=str(getattr(handle, "job_id", "") or "").strip() or None,
        queue_provider=str(getattr(handle, "provider", "") or "").strip() or None,
        ok=ok,
        error=error,
    )
    submit_payload["summary_text"] = approval_resolution_summary_runtime.background_teammate_summary_text(
        title="background teammate submitted" if ok else "background teammate submission failed",
        task_id=str(getattr(handle, "task_id", "") or "").strip(),
        status=(
            str(getattr(handle, "status", "") or "").strip()
            if handle is not None
            else "failed"
        ),
        task=str(payload.get("task") or "").strip(),
        provider=str(payload.get("provider") or "").strip(),
        model=str(payload.get("model") or "").strip(),
        reasoning_effort=str(payload.get("reasoning_effort") or "").strip(),
        cwd=str(payload.get("cwd") or "").strip(),
        approval_policy=str(payload.get("approval_policy") or "never").strip() or "never",
        sandbox_mode=str(payload.get("sandbox_mode") or "read-only").strip() or "read-only",
        allowed_paths=list(payload.get("allowed_paths") or []),
        blocked_paths=list(payload.get("blocked_paths") or []),
        timeout_seconds=payload.get("timeout_seconds"),
        queue_provider=str(getattr(handle, "provider", "") or "").strip(),
    )
    return ToolEvent(
        name="background_teammate_submitted",
        ok=ok,
        summary=(
            f"background teammate submitted {handle.task_id}"
            if ok
            else "background teammate submission failed"
        ),
        payload=submit_payload,
    )

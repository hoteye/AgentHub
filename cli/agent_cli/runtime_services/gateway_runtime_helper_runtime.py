from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import inspect
from typing import Any, Dict

from cli.agent_cli.gateway_core import create_audit_record
from cli.agent_cli.runtime_runs import RunKind, RunStatus


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def broadcast_payload(saved: Any) -> dict[str, Any]:
    if hasattr(saved, "to_dict"):
        return saved.to_dict()
    return dict(saved or {})


def merge_context(existing: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(existing or {})
    for key, value in dict(updates or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**dict(merged.get(key) or {}), **value}
        else:
            merged[key] = value
    return merged


def gateway_run_id_for_workflow_id(workflow_run_id: Any) -> str:
    normalized = str(workflow_run_id or "").strip()
    if not normalized:
        return ""
    return f"run_gateway_{normalized}"


def with_workflow_run_identifiers(workflow_run: Any) -> Any:
    run_id = str(getattr(workflow_run, "run_id", "") or "").strip()
    workflow_run_id = str(getattr(workflow_run, "workflow_run_id", "") or "").strip()
    if run_id:
        return workflow_run
    resolved_run_id = gateway_run_id_for_workflow_id(workflow_run_id)
    if not resolved_run_id:
        return workflow_run
    return replace(workflow_run, run_id=resolved_run_id)


def run_status_from_workflow_status(status: Any) -> RunStatus:
    normalized = str(status or "").strip().lower()
    if normalized == "running":
        return RunStatus.RUNNING
    if normalized in {"completed", "ok", "succeeded", "success"}:
        return RunStatus.COMPLETED
    if normalized in {"failed", "error"}:
        return RunStatus.FAILED
    if normalized in {"cancelled", "canceled"}:
        return RunStatus.CANCELLED
    if normalized in {"timed_out", "timeout", "expired"}:
        return RunStatus.TIMED_OUT
    if normalized in {"pending", "queued"}:
        return RunStatus.CREATED
    return RunStatus.CREATED


def sync_workflow_run_with_run_manager(runtime: Any, workflow_run: Any) -> Any:
    if workflow_run is None:
        return None
    run_manager = getattr(runtime, "run_manager", None)
    if run_manager is None:
        return workflow_run
    normalized_workflow_run = with_workflow_run_identifiers(workflow_run)
    run_id = str(getattr(normalized_workflow_run, "run_id", "") or "").strip()
    if not run_id:
        return normalized_workflow_run
    parent_run_id = str(getattr(normalized_workflow_run, "parent_run_id", "") or "").strip()
    summary = str(getattr(normalized_workflow_run, "result_summary", "") or "").strip()
    if not summary:
        summary = str(getattr(normalized_workflow_run, "status", "") or "").strip()
    payload = {
        "workflow_run_id": str(getattr(normalized_workflow_run, "workflow_run_id", "") or "").strip(),
        "workflow_name": str(getattr(normalized_workflow_run, "workflow_name", "") or "").strip(),
        "plugin_name": str(getattr(normalized_workflow_run, "plugin_name", "") or "").strip(),
        "trace_id": str(getattr(normalized_workflow_run, "trace_id", "") or "").strip(),
        "event_id": str(getattr(normalized_workflow_run, "event_id", "") or "").strip(),
        "status": str(getattr(normalized_workflow_run, "status", "") or "").strip(),
        "current_step": str(getattr(normalized_workflow_run, "current_step", "") or "").strip(),
    }
    mapped_status = run_status_from_workflow_status(getattr(normalized_workflow_run, "status", ""))
    existing = run_manager.get(run_id) if callable(getattr(run_manager, "get", None)) else None
    if existing is None and callable(getattr(run_manager, "create", None)):
        try:
            run_manager.create(
                run_id=run_id,
                kind=RunKind.WORKFLOW,
                thread_id=str(getattr(runtime, "thread_id", "") or ""),
                parent_run_id=parent_run_id,
                summary=summary,
                payload=payload,
            )
        except Exception:
            pass
    if callable(getattr(run_manager, "update", None)):
        try:
            run_manager.update(
                run_id,
                status=mapped_status,
                summary=summary,
                payload=payload,
            )
        except Exception:
            pass
    return normalized_workflow_run


def update_workflow_run_record(
    workflow_run: Any,
    *,
    status: str | None = None,
    current_step: str | None = None,
    result_summary: str | None = None,
    context_updates: Dict[str, Any] | None = None,
    finished: bool = False,
) -> Any:
    now = now_iso()
    return replace(
        workflow_run,
        status=str(status or workflow_run.status or "").strip() or workflow_run.status,
        current_step=str(current_step).strip() if current_step is not None else workflow_run.current_step,
        result_summary=str(result_summary).strip() if result_summary is not None else workflow_run.result_summary,
        updated_at=now,
        finished_at=now if finished else workflow_run.finished_at,
        context=merge_context(dict(workflow_run.context or {}), dict(context_updates or {})),
        run_id=str(getattr(workflow_run, "run_id", "") or "").strip() or None,
        parent_run_id=str(getattr(workflow_run, "parent_run_id", "") or "").strip() or None,
    )


def filter_handler_kwargs(handler: Any, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):
        return kwargs
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
        return kwargs
    return {key: value for key, value in kwargs.items() if key in signature.parameters}


def normalized_workflow_result(raw_result: Any) -> Dict[str, Any]:
    if isinstance(raw_result, dict):
        result = dict(raw_result)
    elif raw_result is None:
        result = {}
    else:
        result = {"output": raw_result}
    result["status"] = str(result.get("status") or "ok").strip() or "ok"
    result["reasoning_summary"] = str(result.get("reasoning_summary") or result.get("summary") or "").strip()
    evidence_refs = result.get("evidence_refs") or []
    result["evidence_refs"] = [str(item).strip() for item in evidence_refs if str(item).strip()]
    action_requests = result.get("action_requests") or []
    if not isinstance(action_requests, list):
        action_requests = [action_requests]
    result["action_requests"] = action_requests
    return result


def dispatch_gateway_event_artifacts(event: Any, decision: Any, workflow_run: Any | None) -> list[Any]:
    route_status = "ok" if decision.trigger is not None else "unrouted"
    route_summary = (
        f"routed to {decision.plugin_name}:{decision.workflow_name}"
        if decision.trigger is not None
        else "no trigger matched"
    )
    return [
        create_audit_record(
            trace_id=event.trace_id,
            stage="ingress",
            status="ok",
            summary=f"received {event.event_type}",
            event_id=event.event_id,
            details={
                "source_kind": event.source_kind,
                "source_id": event.source_id,
                "connector_key": event.connector_key,
            },
        ),
        create_audit_record(
            trace_id=event.trace_id,
            stage="route",
            status=route_status,
            summary=route_summary,
            event_id=event.event_id,
            workflow_run_id=workflow_run.workflow_run_id if workflow_run is not None else None,
            details={
                "plugin_name": decision.plugin_name,
                "workflow_name": decision.workflow_name,
                "reason": decision.reason,
            },
        ),
    ]


def apply_workflow_success(
    workflow_run: Any,
    *,
    workflow_result: dict[str, Any],
    decision: Any,
) -> tuple[Any, Any]:
    reasoning_summary = str((workflow_result or {}).get("reasoning_summary") or "").strip()
    action_requests = list((workflow_result or {}).get("action_requests") or [])
    updated_workflow_run = replace(
        workflow_run,
        status=str((workflow_result or {}).get("status") or "completed").strip() or "completed",
        current_step="workflow_executed",
        result_summary=reasoning_summary or f"workflow executed: {decision.workflow_name}",
        updated_at=now_iso(),
        finished_at=now_iso(),
        context={
            **dict(workflow_run.context or {}),
            "workflow_result": {
                "status": str((workflow_result or {}).get("status") or "completed").strip() or "completed",
                "reasoning_summary": reasoning_summary,
                "evidence_refs": list((workflow_result or {}).get("evidence_refs") or []),
                "action_request_count": len(action_requests),
            },
        },
    )
    audit_record = create_audit_record(
        trace_id=workflow_run.trace_id,
        stage="workflow",
        status=str((workflow_result or {}).get("status") or "ok").strip() or "ok",
        summary=reasoning_summary or f"workflow executed: {decision.workflow_name}",
        event_id=workflow_run.event_id,
        workflow_run_id=updated_workflow_run.workflow_run_id,
        details={
            "plugin_name": decision.plugin_name,
            "workflow_name": decision.workflow_name,
            "reasoning_summary": reasoning_summary,
            "evidence_refs": list((workflow_result or {}).get("evidence_refs") or []),
            "action_request_count": len(action_requests),
        },
    )
    return updated_workflow_run, audit_record


def apply_workflow_failure(workflow_run: Any, *, decision: Any, error_text: str) -> tuple[Any, Any]:
    updated_workflow_run = replace(
        workflow_run,
        status="failed",
        current_step="workflow_failed",
        result_summary=error_text,
        updated_at=now_iso(),
        finished_at=now_iso(),
        context={
            **dict(workflow_run.context or {}),
            "workflow_error": error_text,
        },
    )
    audit_record = create_audit_record(
        trace_id=workflow_run.trace_id,
        stage="workflow",
        status="failed",
        summary=error_text,
        event_id=workflow_run.event_id,
        workflow_run_id=updated_workflow_run.workflow_run_id,
        details={
            "plugin_name": decision.plugin_name,
            "workflow_name": decision.workflow_name,
            "error": error_text,
        },
    )
    return updated_workflow_run, audit_record

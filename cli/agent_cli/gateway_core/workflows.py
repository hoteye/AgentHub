from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha1
from typing import Any, Dict, Optional

from .models import GatewayEvent, TriggerRegistration, WorkflowRun


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def create_workflow_run(
    *,
    trigger: TriggerRegistration,
    event: GatewayEvent,
    status: str = "pending",
    current_step: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    run_id: Optional[str] = None,
    parent_run_id: Optional[str] = None,
) -> WorkflowRun:
    started_at = _utc_now_text()
    digest = sha1(f"{trigger.workflow_name}|{event.event_id}|{started_at}".encode("utf-8")).hexdigest()[:12]
    resolved_run_id = str(run_id or "").strip() or f"run_gateway_{digest}"
    resolved_parent_run_id = str(parent_run_id or "").strip() or None
    return WorkflowRun(
        workflow_run_id=f"wf_{digest}",
        workflow_name=trigger.workflow_name,
        plugin_name=trigger.plugin_name,
        event_id=event.event_id,
        trace_id=event.trace_id,
        status=str(status or "").strip(),
        started_at=started_at,
        updated_at=started_at,
        finished_at=None,
        current_step=str(current_step).strip() if current_step is not None else None,
        result_summary=None,
        context=dict(context or {}),
        metadata=dict(metadata or {}),
        run_id=resolved_run_id,
        parent_run_id=resolved_parent_run_id,
    )

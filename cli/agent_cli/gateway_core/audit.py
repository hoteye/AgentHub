from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha1
from typing import Any, Dict, Optional

from .models import AuditRecord


def _stage_group(stage: str) -> str:
    normalized = str(stage or "").strip().lower()
    if normalized in {"ingress", "route", "action_request", "approval", "action_execute"}:
        return normalized
    if normalized in {"workflow_reasoning", "workflow", "reasoning"}:
        return "workflow_reasoning"
    return "other"


def create_audit_record(
    *,
    trace_id: str,
    stage: str,
    status: str,
    summary: str,
    details: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    event_id: Optional[str] = None,
    workflow_run_id: Optional[str] = None,
    action_id: Optional[str] = None,
    approval_id: Optional[str] = None,
) -> AuditRecord:
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    normalized_stage = str(stage or "").strip()
    normalized_status = str(status or "").strip()
    normalized_summary = str(summary or "").strip()
    normalized_details = dict(details or {})
    normalized_metadata = dict(metadata or {})

    causality = dict(normalized_metadata.get("causality") or {})
    causality["trace_id"] = str(trace_id or "").strip()
    if event_id is not None:
        causality["event_id"] = str(event_id).strip()
    if workflow_run_id is not None:
        causality["workflow_run_id"] = str(workflow_run_id).strip()
    if action_id is not None:
        causality["action_id"] = str(action_id).strip()
    if approval_id is not None:
        causality["approval_id"] = str(approval_id).strip()
    normalized_metadata["causality"] = causality
    normalized_metadata["stage_group"] = _stage_group(normalized_stage)

    digest = sha1(f"{trace_id}|{normalized_stage}|{created_at}|{normalized_summary}".encode("utf-8")).hexdigest()[:12]
    return AuditRecord(
        audit_id=f"audit_{digest}",
        trace_id=str(trace_id or "").strip(),
        stage=normalized_stage,
        created_at=created_at,
        event_id=str(event_id).strip() if event_id is not None else None,
        workflow_run_id=str(workflow_run_id).strip() if workflow_run_id is not None else None,
        action_id=str(action_id).strip() if action_id is not None else None,
        approval_id=str(approval_id).strip() if approval_id is not None else None,
        status=normalized_status,
        summary=normalized_summary,
        details=normalized_details,
        metadata=normalized_metadata,
    )

from __future__ import annotations

from typing import Any

JsonMap = dict[str, Any]


def gateway_item_to_dict(item: Any) -> Any:
    to_dict = getattr(item, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    return item


def route_decision_to_dict(item: Any) -> JsonMap:
    return {
        "targetKind": getattr(item, "target_kind", None),
        "pluginName": getattr(item, "plugin_name", None),
        "workflowName": getattr(item, "workflow_name", None),
        "reason": getattr(item, "reason", None),
        "trigger": gateway_item_to_dict(getattr(item, "trigger", None)),
    }


def gateway_dispatch_result_payload(result: JsonMap) -> JsonMap:
    return {
        "event": gateway_item_to_dict(result.get("event")),
        "decision": route_decision_to_dict(result["decision"]),
        "workflowRun": gateway_item_to_dict(result.get("workflow_run")),
        "auditRecords": [gateway_item_to_dict(item) for item in result.get("audit_records") or []],
    }


def nodes_last_seen_at(events: list[Any]) -> str | None:
    timestamps: list[str] = []
    for item in events:
        if not isinstance(item, dict):
            continue
        for key in ("received_at", "occurred_at", "receivedAt", "occurredAt"):
            value = str(item.get(key) or "").strip()
            if value:
                timestamps.append(value)
    if not timestamps:
        return None
    return sorted(timestamps)[-1]


def pairing_pending_refs(pairing: JsonMap) -> list[JsonMap]:
    refs: list[JsonMap] = []
    for item in list(pairing.get("pendingRefs") or []):
        if not isinstance(item, dict):
            continue
        ref = {
            "approvalId": str(item.get("approvalId") or ""),
            "traceId": str(item.get("traceId") or ""),
            "title": str(item.get("title") or ""),
            "actionType": str(item.get("actionType") or ""),
        }
        requested_at = str(item.get("requestedAt") or "").strip()
        if requested_at:
            ref["requestedAt"] = requested_at
        refs.append(ref)
    return refs


def workflow_resume_eligible(item: JsonMap) -> bool:
    status = str(item.get("status") or "").strip().lower()
    current_step = str(item.get("current_step") or item.get("currentStep") or "").strip().lower()
    if status in {"ok", "completed", "noop", "failed", "rejected"}:
        return False
    return status in {"paused", "waiting", "blocked", "pending"} or "paused" in current_step or "waiting" in current_step


def sorted_trace_timeline(
    *,
    trace_id: str,
    events: list[JsonMap],
    workflow_runs: list[JsonMap],
    action_requests: list[JsonMap],
    approval_tickets: list[JsonMap],
    audit_records: list[JsonMap],
) -> list[JsonMap]:
    timeline: list[JsonMap] = []
    for family_name, items in (
        ("events", events),
        ("workflowRuns", workflow_runs),
        ("actionRequests", action_requests),
        ("approvalTickets", approval_tickets),
        ("auditRecords", audit_records),
    ):
        for item in items:
            item_trace_id = str((item or {}).get("trace_id") or (item or {}).get("traceId") or "").strip()
            if item_trace_id != trace_id:
                continue
            timeline.append({"kind": family_name, "item": item})
    timeline.sort(key=lambda entry: timeline_sort_key(entry["kind"], entry["item"]))
    return timeline


def timeline_sort_key(kind: str, item: JsonMap) -> tuple[str, str]:
    order = {
        "events": 0,
        "workflowRuns": 1,
        "actionRequests": 2,
        "approvalTickets": 3,
        "auditRecords": 4,
    }
    timestamp = ""
    if kind == "events":
        timestamp = str(item.get("received_at") or item.get("occurred_at") or "")
    elif kind == "workflowRuns":
        timestamp = str(item.get("started_at") or item.get("updated_at") or "")
    elif kind == "actionRequests":
        timestamp = str(item.get("requested_at") or "")
    elif kind == "approvalTickets":
        timestamp = str(item.get("requested_at") or item.get("decision_at") or "")
    elif kind == "auditRecords":
        timestamp = str(item.get("created_at") or "")
    return (timestamp, f"{order.get(kind, 9):02d}")

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .models import (
    action_request_from_mapping,
    approval_ticket_from_mapping,
    audit_record_from_mapping,
    gateway_event_from_mapping,
    workflow_run_from_mapping,
)


def append_jsonl_record(files: Mapping[str, Path], key: str, payload: dict) -> None:
    target = files[key]
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_jsonl_records_into_store(store: Any, files: Mapping[str, Path]) -> None:
    loaders = {
        "events": _load_gateway_event,
        "workflow_runs": _load_workflow_run,
        "action_requests": _load_action_request,
        "approval_tickets": _load_approval_ticket,
        "audit_records": _load_audit_record,
    }
    for key, target in files.items():
        if not target.exists():
            continue
        with target.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                loaders[key](store, payload)


def load_existing_jsonl_records_in_background(
    store: Any,
    files: Mapping[str, Path],
    empty_store_factory: Callable[[], Any],
) -> None:
    loaded = empty_store_factory()
    try:
        load_jsonl_records_into_store(loaded, files)
        with store._lock:
            merge_loaded_jsonl_state(store, loaded)
    except Exception as exc:
        store._load_error = exc
    finally:
        store._load_complete.set()


def merge_loaded_jsonl_state(store: Any, loaded: Any) -> None:
    pending_events = dict(store.events)
    pending_workflow_runs = dict(store.workflow_runs)
    pending_action_requests = dict(store.action_requests)
    pending_approval_tickets = dict(store.approval_tickets)
    pending_audit_records = list(store.audit_records)
    store.events = dict(loaded.events)
    store.workflow_runs = dict(loaded.workflow_runs)
    store.action_requests = dict(loaded.action_requests)
    store.approval_tickets = dict(loaded.approval_tickets)
    store.audit_records = list(loaded.audit_records)
    store.events.update(pending_events)
    store.workflow_runs.update(pending_workflow_runs)
    store.action_requests.update(pending_action_requests)
    store.approval_tickets.update(pending_approval_tickets)
    seen_audit_ids = {str(getattr(record, "audit_id", "") or "") for record in store.audit_records}
    for record in pending_audit_records:
        audit_id = str(getattr(record, "audit_id", "") or "")
        if audit_id and audit_id in seen_audit_ids:
            continue
        store.audit_records.append(record)
        if audit_id:
            seen_audit_ids.add(audit_id)


def _load_gateway_event(store: Any, payload: dict) -> None:
    item = gateway_event_from_mapping(payload)
    store.events[item.event_id] = item


def _load_workflow_run(store: Any, payload: dict) -> None:
    item = workflow_run_from_mapping(payload)
    store.workflow_runs[item.workflow_run_id] = item


def _load_action_request(store: Any, payload: dict) -> None:
    item = action_request_from_mapping(payload)
    store.action_requests[item.action_id] = item


def _load_approval_ticket(store: Any, payload: dict) -> None:
    item = approval_ticket_from_mapping(payload)
    store.approval_tickets[item.approval_id] = item


def _load_audit_record(store: Any, payload: dict) -> None:
    store.audit_records.append(audit_record_from_mapping(payload))

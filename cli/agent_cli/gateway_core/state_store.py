from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from shutil import copy2

from cli.agent_cli.runtime_paths import (
    LEGACY_PROJECT_LOCAL_DATA_DIRNAMES,
    PROJECT_LOCAL_DATA_DIRNAME,
    PROJECT_ROOT_ENV,
    is_frozen_runtime,
    project_local_data_dir,
)

from .models import (
    ActionRequest,
    ApprovalTicket,
    AuditRecord,
    GatewayEvent,
    WorkflowRun,
    action_request_from_mapping,
    approval_ticket_from_mapping,
    audit_record_from_mapping,
    gateway_event_from_mapping,
    workflow_run_from_mapping,
)

_GATEWAY_JSONL_FILENAMES = {
    "events": "events.jsonl",
    "workflow_runs": "workflow_runs.jsonl",
    "action_requests": "action_requests.jsonl",
    "approval_tickets": "approval_tickets.jsonl",
    "audit_records": "audit_records.jsonl",
}


def _safe_resolve(path: Path) -> Path:
    try:
        return path.expanduser().resolve()
    except OSError:
        return path.expanduser()


def _default_gateway_project_root() -> Path:
    configured = str(os.environ.get(PROJECT_ROOT_ENV) or "").strip()
    if configured:
        return _safe_resolve(Path(configured))
    return _safe_resolve(Path(__file__).resolve().parents[2])


def _default_gateway_base_dir(*, root: Path | None = None) -> Path:
    if root is None and is_frozen_runtime():
        return project_local_data_dir() / "gateway"
    project_root = _safe_resolve(root or _default_gateway_project_root())
    return project_root / PROJECT_LOCAL_DATA_DIRNAME / "gateway"


def _legacy_gateway_base_dirs(*, root: Path | None = None) -> list[Path]:
    project_root = _safe_resolve(root or _default_gateway_project_root())
    return [project_root / dirname / "gateway" for dirname in LEGACY_PROJECT_LOCAL_DATA_DIRNAMES]


def _migrate_legacy_gateway_state(preferred_dir: Path, *, root: Path | None = None) -> None:
    preferred_dir.mkdir(parents=True, exist_ok=True)
    for legacy_dir in _legacy_gateway_base_dirs(root=root):
        if not legacy_dir.exists() or legacy_dir == preferred_dir:
            continue
        for filename in _GATEWAY_JSONL_FILENAMES.values():
            source = legacy_dir / filename
            target = preferred_dir / filename
            if not source.exists() or target.exists():
                continue
            copy2(source, target)


@dataclass(slots=True)
class InMemoryGatewayStateStore:
    events: dict[str, GatewayEvent] = field(default_factory=dict)
    workflow_runs: dict[str, WorkflowRun] = field(default_factory=dict)
    action_requests: dict[str, ActionRequest] = field(default_factory=dict)
    approval_tickets: dict[str, ApprovalTicket] = field(default_factory=dict)
    audit_records: list[AuditRecord] = field(default_factory=list)

    def save_event(self, item: GatewayEvent) -> GatewayEvent:
        self.events[item.event_id] = item
        return item

    def save_workflow_run(self, item: WorkflowRun) -> WorkflowRun:
        self.workflow_runs[item.workflow_run_id] = item
        return item

    def save_action_request(self, item: ActionRequest) -> ActionRequest:
        self.action_requests[item.action_id] = item
        return item

    def save_approval_ticket(self, item: ApprovalTicket) -> ApprovalTicket:
        self.approval_tickets[item.approval_id] = item
        return item

    def append_audit_record(self, item: AuditRecord) -> AuditRecord:
        self.audit_records.append(item)
        return item

    def get_action_request(self, action_id: str) -> ActionRequest | None:
        return self.action_requests.get(str(action_id or "").strip())

    def get_workflow_run(self, workflow_run_id: str) -> WorkflowRun | None:
        return self.workflow_runs.get(str(workflow_run_id or "").strip())

    def get_approval_ticket(self, approval_id: str) -> ApprovalTicket | None:
        return self.approval_tickets.get(str(approval_id or "").strip())

    def list_events(self, *, limit: int = 50) -> list[GatewayEvent]:
        items = list(self.events.values())
        items.sort(key=lambda item: (item.received_at, item.event_id), reverse=True)
        return items[: max(1, int(limit))]

    def list_workflow_runs(self, *, limit: int = 50) -> list[WorkflowRun]:
        items = list(self.workflow_runs.values())
        items.sort(key=lambda item: (item.updated_at, item.workflow_run_id), reverse=True)
        return items[: max(1, int(limit))]

    def list_action_requests(self, *, limit: int = 50) -> list[ActionRequest]:
        items = list(self.action_requests.values())
        items.sort(key=lambda item: (item.requested_at, item.action_id), reverse=True)
        return items[: max(1, int(limit))]

    def list_approval_tickets(
        self,
        *,
        limit: int = 50,
        status: str | None = None,
        trace_id: str | None = None,
        action_id: str | None = None,
    ) -> list[ApprovalTicket]:
        normalized_status = str(status or "").strip().lower()
        normalized_trace_id = str(trace_id or "").strip()
        normalized_action_id = str(action_id or "").strip()
        items = list(self.approval_tickets.values())
        if normalized_status:
            items = [
                item
                for item in items
                if str(item.status or "").strip().lower() == normalized_status
            ]
        if normalized_trace_id:
            items = [item for item in items if item.trace_id == normalized_trace_id]
        if normalized_action_id:
            items = [item for item in items if item.action_id == normalized_action_id]
        items.sort(key=lambda item: (item.requested_at, item.approval_id), reverse=True)
        return items[: max(1, int(limit))]

    def list_audit_records(
        self,
        *,
        limit: int = 50,
        trace_id: str | None = None,
        stage: str | None = None,
        status: str | None = None,
        event_id: str | None = None,
        workflow_run_id: str | None = None,
        action_id: str | None = None,
        approval_id: str | None = None,
    ) -> list[AuditRecord]:
        normalized_trace_id = str(trace_id or "").strip()
        normalized_stage = str(stage or "").strip().lower()
        normalized_status = str(status or "").strip().lower()
        normalized_event_id = str(event_id or "").strip()
        normalized_workflow_run_id = str(workflow_run_id or "").strip()
        normalized_action_id = str(action_id or "").strip()
        normalized_approval_id = str(approval_id or "").strip()
        items = list(self.audit_records)
        if normalized_trace_id:
            items = [item for item in items if item.trace_id == normalized_trace_id]
        if normalized_stage:
            items = [
                item for item in items if str(item.stage or "").strip().lower() == normalized_stage
            ]
        if normalized_status:
            items = [
                item
                for item in items
                if str(item.status or "").strip().lower() == normalized_status
            ]
        if normalized_event_id:
            items = [
                item for item in items if str(item.event_id or "").strip() == normalized_event_id
            ]
        if normalized_workflow_run_id:
            items = [
                item
                for item in items
                if str(item.workflow_run_id or "").strip() == normalized_workflow_run_id
            ]
        if normalized_action_id:
            items = [
                item for item in items if str(item.action_id or "").strip() == normalized_action_id
            ]
        if normalized_approval_id:
            items = [
                item
                for item in items
                if str(item.approval_id or "").strip() == normalized_approval_id
            ]
        items.sort(key=lambda item: (item.created_at, item.audit_id), reverse=True)
        return items[: max(1, int(limit))]

    def trace_timeline(self, trace_id: str, *, limit: int = 200) -> list[AuditRecord]:
        normalized_trace_id = str(trace_id or "").strip()
        if not normalized_trace_id:
            return []
        items = [item for item in self.audit_records if item.trace_id == normalized_trace_id]
        return items[: max(1, int(limit))]


def _load_jsonl_records_into_store(
    store: InMemoryGatewayStateStore,
    files: dict[str, Path],
) -> None:
    loaders = {
        "events": lambda payload: InMemoryGatewayStateStore.save_event(
            store, gateway_event_from_mapping(payload)
        ),
        "workflow_runs": lambda payload: InMemoryGatewayStateStore.save_workflow_run(
            store, workflow_run_from_mapping(payload)
        ),
        "action_requests": lambda payload: InMemoryGatewayStateStore.save_action_request(
            store, action_request_from_mapping(payload)
        ),
        "approval_tickets": lambda payload: InMemoryGatewayStateStore.save_approval_ticket(
            store, approval_ticket_from_mapping(payload)
        ),
        "audit_records": lambda payload: InMemoryGatewayStateStore.append_audit_record(
            store, audit_record_from_mapping(payload)
        ),
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
                loaders[key](payload)


class JsonlGatewayStateStore(InMemoryGatewayStateStore):
    def __init__(self, base_dir: str | Path) -> None:
        super().__init__()
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._files = {
            key: self.base_dir / filename for key, filename in _GATEWAY_JSONL_FILENAMES.items()
        }
        self._load_existing()

    @classmethod
    def default(cls, *, lazy: bool = False) -> JsonlGatewayStateStore | LazyJsonlGatewayStateStore:
        root = _default_gateway_base_dir()
        _migrate_legacy_gateway_state(root)
        if lazy:
            return LazyJsonlGatewayStateStore(root)
        return cls(root)

    def _append_jsonl(self, key: str, payload: dict) -> None:
        target = self._files[key]
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _load_existing(self) -> None:
        _load_jsonl_records_into_store(self, self._files)

    def save_event(self, item: GatewayEvent) -> GatewayEvent:
        with self._lock:
            saved = super().save_event(item)
            self._append_jsonl("events", saved.to_dict())
            return saved

    def save_workflow_run(self, item: WorkflowRun) -> WorkflowRun:
        with self._lock:
            saved = super().save_workflow_run(item)
            self._append_jsonl("workflow_runs", saved.to_dict())
            return saved

    def save_action_request(self, item: ActionRequest) -> ActionRequest:
        with self._lock:
            saved = super().save_action_request(item)
            self._append_jsonl("action_requests", saved.to_dict())
            return saved

    def save_approval_ticket(self, item: ApprovalTicket) -> ApprovalTicket:
        with self._lock:
            saved = super().save_approval_ticket(item)
            self._append_jsonl("approval_tickets", saved.to_dict())
            return saved

    def append_audit_record(self, item: AuditRecord) -> AuditRecord:
        with self._lock:
            saved = super().append_audit_record(item)
            self._append_jsonl("audit_records", saved.to_dict())
            return saved


class LazyJsonlGatewayStateStore(InMemoryGatewayStateStore):
    def __init__(self, base_dir: str | Path) -> None:
        super().__init__()
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._files = {
            key: self.base_dir / filename for key, filename in _GATEWAY_JSONL_FILENAMES.items()
        }
        self._load_complete = threading.Event()
        self._load_error: BaseException | None = None
        self._load_thread = threading.Thread(
            target=self._load_existing_in_background,
            name="agenthub-gateway-state-load",
            daemon=True,
        )
        self._load_thread.start()

    @property
    def load_error(self) -> BaseException | None:
        return self._load_error

    def wait_until_loaded(self, timeout: float | None = None) -> bool:
        return self._load_complete.wait(timeout)

    def _append_jsonl(self, key: str, payload: dict) -> None:
        target = self._files[key]
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _load_existing_in_background(self) -> None:
        loaded = InMemoryGatewayStateStore()
        try:
            _load_jsonl_records_into_store(loaded, self._files)
            with self._lock:
                pending_events = dict(self.events)
                pending_workflow_runs = dict(self.workflow_runs)
                pending_action_requests = dict(self.action_requests)
                pending_approval_tickets = dict(self.approval_tickets)
                pending_audit_records = list(self.audit_records)
                self.events = dict(loaded.events)
                self.workflow_runs = dict(loaded.workflow_runs)
                self.action_requests = dict(loaded.action_requests)
                self.approval_tickets = dict(loaded.approval_tickets)
                self.audit_records = list(loaded.audit_records)
                self.events.update(pending_events)
                self.workflow_runs.update(pending_workflow_runs)
                self.action_requests.update(pending_action_requests)
                self.approval_tickets.update(pending_approval_tickets)
                seen_audit_ids = {
                    str(getattr(record, "audit_id", "") or "") for record in self.audit_records
                }
                for record in pending_audit_records:
                    audit_id = str(getattr(record, "audit_id", "") or "")
                    if audit_id and audit_id in seen_audit_ids:
                        continue
                    self.audit_records.append(record)
                    if audit_id:
                        seen_audit_ids.add(audit_id)
        except Exception as exc:
            self._load_error = exc
        finally:
            self._load_complete.set()

    def save_event(self, item: GatewayEvent) -> GatewayEvent:
        with self._lock:
            saved = InMemoryGatewayStateStore.save_event(self, item)
            self._append_jsonl("events", saved.to_dict())
            return saved

    def save_workflow_run(self, item: WorkflowRun) -> WorkflowRun:
        with self._lock:
            saved = InMemoryGatewayStateStore.save_workflow_run(self, item)
            self._append_jsonl("workflow_runs", saved.to_dict())
            return saved

    def save_action_request(self, item: ActionRequest) -> ActionRequest:
        with self._lock:
            saved = InMemoryGatewayStateStore.save_action_request(self, item)
            self._append_jsonl("action_requests", saved.to_dict())
            return saved

    def save_approval_ticket(self, item: ApprovalTicket) -> ApprovalTicket:
        with self._lock:
            saved = InMemoryGatewayStateStore.save_approval_ticket(self, item)
            self._append_jsonl("approval_tickets", saved.to_dict())
            return saved

    def append_audit_record(self, item: AuditRecord) -> AuditRecord:
        with self._lock:
            saved = InMemoryGatewayStateStore.append_audit_record(self, item)
            self._append_jsonl("audit_records", saved.to_dict())
            return saved

    def get_action_request(self, action_id: str) -> ActionRequest | None:
        with self._lock:
            return InMemoryGatewayStateStore.get_action_request(self, action_id)

    def get_workflow_run(self, workflow_run_id: str) -> WorkflowRun | None:
        with self._lock:
            return InMemoryGatewayStateStore.get_workflow_run(self, workflow_run_id)

    def get_approval_ticket(self, approval_id: str) -> ApprovalTicket | None:
        with self._lock:
            return InMemoryGatewayStateStore.get_approval_ticket(self, approval_id)

    def list_events(self, *, limit: int = 50) -> list[GatewayEvent]:
        with self._lock:
            return InMemoryGatewayStateStore.list_events(self, limit=limit)

    def list_workflow_runs(self, *, limit: int = 50) -> list[WorkflowRun]:
        with self._lock:
            return InMemoryGatewayStateStore.list_workflow_runs(self, limit=limit)

    def list_action_requests(self, *, limit: int = 50) -> list[ActionRequest]:
        with self._lock:
            return InMemoryGatewayStateStore.list_action_requests(self, limit=limit)

    def list_approval_tickets(
        self,
        *,
        limit: int = 50,
        status: str | None = None,
        trace_id: str | None = None,
        action_id: str | None = None,
    ) -> list[ApprovalTicket]:
        with self._lock:
            return InMemoryGatewayStateStore.list_approval_tickets(
                self,
                limit=limit,
                status=status,
                trace_id=trace_id,
                action_id=action_id,
            )

    def list_audit_records(
        self,
        *,
        limit: int = 50,
        trace_id: str | None = None,
        stage: str | None = None,
        status: str | None = None,
        event_id: str | None = None,
        workflow_run_id: str | None = None,
        action_id: str | None = None,
        approval_id: str | None = None,
    ) -> list[AuditRecord]:
        with self._lock:
            return InMemoryGatewayStateStore.list_audit_records(
                self,
                limit=limit,
                trace_id=trace_id,
                stage=stage,
                status=status,
                event_id=event_id,
                workflow_run_id=workflow_run_id,
                action_id=action_id,
                approval_id=approval_id,
            )

    def trace_timeline(self, trace_id: str, *, limit: int = 200) -> list[AuditRecord]:
        with self._lock:
            return InMemoryGatewayStateStore.trace_timeline(self, trace_id, limit=limit)

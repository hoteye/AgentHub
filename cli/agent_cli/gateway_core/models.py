from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


def _copy_map(value: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return dict(value or {})


def _copy_list(value: Optional[List[str]] = None) -> List[str]:
    return list(value or [])


def _copy_mapping_list(value: Any = None) -> List[Dict[str, Any]]:
    copied: List[Dict[str, Any]] = []
    for item in list(value or []):
        if isinstance(item, dict):
            copied.append(dict(item))
    return copied


@dataclass(slots=True)
class GatewayEvent:
    event_id: str
    event_type: str
    source_kind: str
    source_id: str
    connector_key: Optional[str]
    plugin_name: Optional[str]
    tenant_id: Optional[str]
    occurred_at: str
    received_at: str
    trace_id: str
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ConnectorRegistration:
    connector_key: str
    plugin_name: str
    display_name: str
    version: str
    connector_kind: str
    description: str = ""
    supports_webhook: bool = False
    supports_polling: bool = False
    supports_actions: bool = False
    event_types: List[str] = field(default_factory=list)
    action_types: List[str] = field(default_factory=list)
    config_schema_ref: Optional[str] = None
    enabled_by_default: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TriggerRegistration:
    trigger_key: str
    plugin_name: str
    trigger_kind: str
    connector_key: Optional[str]
    event_types: List[str]
    workflow_name: str
    priority: int = 100
    filters: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PolicyRegistration:
    policy_key: str
    plugin_name: str
    display_name: str
    version: str
    policy_kind: str
    description: str = ""
    applies_to: List[str] = field(default_factory=list)
    ruleset_ref: Optional[str] = None
    enabled_by_default: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ActionRequest:
    action_id: str
    action_type: str
    connector_key: str
    plugin_name: str
    trace_id: str
    requested_at: str
    requested_by: str
    approval_required: bool
    action_family: Optional[str] = None
    action_class: Optional[str] = None
    approval_policy: Optional[str] = None
    audit_stage: Optional[str] = None
    workflow_run_id: Optional[str] = None
    event_id: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ApprovalTicket:
    approval_id: str
    action_id: str
    trace_id: str
    status: str
    requested_at: str
    requested_by: str
    evidence_refs: List[str] = field(default_factory=list)
    reason: str = ""
    summary: str = ""
    decision_at: Optional[str] = None
    decision_by: Optional[str] = None
    decision_note: Optional[str] = None
    available_decisions: List[Dict[str, Any]] = field(default_factory=list)
    session_cache_keys: List[str] = field(default_factory=list)
    proposed_rule: Dict[str, Any] | None = None
    grant_root: Optional[str] = None
    decision_type: Optional[str] = None
    decision_payload: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AuditRecord:
    audit_id: str
    trace_id: str
    stage: str
    created_at: str
    status: str
    summary: str
    event_id: Optional[str] = None
    workflow_run_id: Optional[str] = None
    action_id: Optional[str] = None
    approval_id: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class WorkflowRun:
    workflow_run_id: str
    workflow_name: str
    plugin_name: str
    trace_id: str
    status: str
    started_at: str
    updated_at: str
    event_id: Optional[str] = None
    finished_at: Optional[str] = None
    current_step: Optional[str] = None
    result_summary: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    run_id: Optional[str] = None
    parent_run_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def gateway_event_from_mapping(payload: Dict[str, Any]) -> GatewayEvent:
    return GatewayEvent(
        event_id=str(payload.get("event_id") or ""),
        event_type=str(payload.get("event_type") or ""),
        source_kind=str(payload.get("source_kind") or ""),
        source_id=str(payload.get("source_id") or ""),
        connector_key=payload.get("connector_key"),
        plugin_name=payload.get("plugin_name"),
        tenant_id=payload.get("tenant_id"),
        occurred_at=str(payload.get("occurred_at") or ""),
        received_at=str(payload.get("received_at") or ""),
        trace_id=str(payload.get("trace_id") or ""),
        correlation_id=payload.get("correlation_id"),
        causation_id=payload.get("causation_id"),
        payload=_copy_map(payload.get("payload")),
        metadata=_copy_map(payload.get("metadata")),
    )


def workflow_run_from_mapping(payload: Dict[str, Any]) -> WorkflowRun:
    return WorkflowRun(
        workflow_run_id=str(payload.get("workflow_run_id") or ""),
        workflow_name=str(payload.get("workflow_name") or ""),
        plugin_name=str(payload.get("plugin_name") or ""),
        trace_id=str(payload.get("trace_id") or ""),
        status=str(payload.get("status") or ""),
        started_at=str(payload.get("started_at") or ""),
        updated_at=str(payload.get("updated_at") or ""),
        event_id=payload.get("event_id"),
        finished_at=payload.get("finished_at"),
        current_step=payload.get("current_step"),
        result_summary=payload.get("result_summary"),
        context=_copy_map(payload.get("context")),
        metadata=_copy_map(payload.get("metadata")),
        run_id=payload.get("run_id"),
        parent_run_id=payload.get("parent_run_id"),
    )


def connector_registration_from_mapping(payload: Dict[str, Any]) -> ConnectorRegistration:
    return ConnectorRegistration(
        connector_key=str(payload.get("connector_key") or ""),
        plugin_name=str(payload.get("plugin_name") or ""),
        display_name=str(payload.get("display_name") or ""),
        version=str(payload.get("version") or ""),
        connector_kind=str(payload.get("connector_kind") or ""),
        description=str(payload.get("description") or ""),
        supports_webhook=bool(payload.get("supports_webhook")),
        supports_polling=bool(payload.get("supports_polling")),
        supports_actions=bool(payload.get("supports_actions")),
        event_types=_copy_list(payload.get("event_types")),
        action_types=_copy_list(payload.get("action_types")),
        config_schema_ref=payload.get("config_schema_ref"),
        enabled_by_default=bool(payload.get("enabled_by_default", True)),
        metadata=_copy_map(payload.get("metadata")),
    )


def trigger_registration_from_mapping(payload: Dict[str, Any]) -> TriggerRegistration:
    return TriggerRegistration(
        trigger_key=str(payload.get("trigger_key") or ""),
        plugin_name=str(payload.get("plugin_name") or ""),
        trigger_kind=str(payload.get("trigger_kind") or ""),
        connector_key=payload.get("connector_key"),
        event_types=_copy_list(payload.get("event_types")),
        workflow_name=str(payload.get("workflow_name") or ""),
        priority=int(payload.get("priority") or 100),
        filters=_copy_map(payload.get("filters")),
        enabled=bool(payload.get("enabled", True)),
        metadata=_copy_map(payload.get("metadata")),
    )


def policy_registration_from_mapping(payload: Dict[str, Any]) -> PolicyRegistration:
    return PolicyRegistration(
        policy_key=str(payload.get("policy_key") or ""),
        plugin_name=str(payload.get("plugin_name") or ""),
        display_name=str(payload.get("display_name") or ""),
        version=str(payload.get("version") or ""),
        policy_kind=str(payload.get("policy_kind") or ""),
        description=str(payload.get("description") or ""),
        applies_to=_copy_list(payload.get("applies_to")),
        ruleset_ref=payload.get("ruleset_ref"),
        enabled_by_default=bool(payload.get("enabled_by_default", True)),
        metadata=_copy_map(payload.get("metadata")),
    )


def action_request_from_mapping(payload: Dict[str, Any]) -> ActionRequest:
    return ActionRequest(
        action_id=str(payload.get("action_id") or ""),
        action_type=str(payload.get("action_type") or ""),
        connector_key=str(payload.get("connector_key") or ""),
        plugin_name=str(payload.get("plugin_name") or ""),
        trace_id=str(payload.get("trace_id") or ""),
        requested_at=str(payload.get("requested_at") or ""),
        requested_by=str(payload.get("requested_by") or ""),
        approval_required=bool(payload.get("approval_required")),
        action_family=payload.get("action_family"),
        action_class=payload.get("action_class"),
        approval_policy=payload.get("approval_policy"),
        audit_stage=payload.get("audit_stage"),
        workflow_run_id=payload.get("workflow_run_id"),
        event_id=payload.get("event_id"),
        payload=_copy_map(payload.get("payload")),
        metadata=_copy_map(payload.get("metadata")),
    )


def approval_ticket_from_mapping(payload: Dict[str, Any]) -> ApprovalTicket:
    return ApprovalTicket(
        approval_id=str(payload.get("approval_id") or ""),
        action_id=str(payload.get("action_id") or ""),
        trace_id=str(payload.get("trace_id") or ""),
        status=str(payload.get("status") or ""),
        requested_at=str(payload.get("requested_at") or ""),
        requested_by=str(payload.get("requested_by") or ""),
        evidence_refs=_copy_list(payload.get("evidence_refs")),
        reason=str(payload.get("reason") or ""),
        summary=str(payload.get("summary") or ""),
        decision_at=payload.get("decision_at"),
        decision_by=payload.get("decision_by"),
        decision_note=payload.get("decision_note"),
        available_decisions=_copy_mapping_list(payload.get("available_decisions")),
        session_cache_keys=_copy_list(payload.get("session_cache_keys")),
        proposed_rule=_copy_map(payload.get("proposed_rule")),
        grant_root=payload.get("grant_root"),
        decision_type=payload.get("decision_type"),
        decision_payload=_copy_map(payload.get("decision_payload")),
        metadata=_copy_map(payload.get("metadata")),
    )


def audit_record_from_mapping(payload: Dict[str, Any]) -> AuditRecord:
    return AuditRecord(
        audit_id=str(payload.get("audit_id") or ""),
        trace_id=str(payload.get("trace_id") or ""),
        stage=str(payload.get("stage") or ""),
        created_at=str(payload.get("created_at") or ""),
        status=str(payload.get("status") or ""),
        summary=str(payload.get("summary") or ""),
        event_id=payload.get("event_id"),
        workflow_run_id=payload.get("workflow_run_id"),
        action_id=payload.get("action_id"),
        approval_id=payload.get("approval_id"),
        details=_copy_map(payload.get("details")),
        metadata=_copy_map(payload.get("metadata")),
    )

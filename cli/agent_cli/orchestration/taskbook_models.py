from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

from . import taskbook_models_serialization_runtime
from .taskbook_state import (
    CardAcceptanceDecision,
    CardResultStatus,
    ComplexTaskMode,
    ComplexTaskRunStatus,
    ExecutionRefKind,
    TaskCardExecutionMode,
    TaskCardExecutorRole,
    TaskCardDependencyStatus,
    TaskCardKind,
    TaskCardStatus,
)
from .taskbook_models_helpers import (
    complex_task_run_kwargs,
    complex_task_run_payload,
    execution_ref_kwargs,
    execution_ref_payload,
    task_card_kwargs,
    task_card_payload,
    taskbook_snapshot_kwargs,
    taskbook_snapshot_payload,
)


SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_orchestration_id(prefix: str) -> str:
    normalized = str(prefix or "orch").strip() or "orch"
    return f"{normalized}_{uuid4().hex}"


@dataclass(slots=True)
class ExecutionRef:
    kind: ExecutionRefKind
    task_id: str = ""
    agent_id: str = ""
    dispatch_id: int = 0
    provider_name: str = ""
    model: str = ""
    route_label: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return execution_ref_payload(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "ExecutionRef":
        data = payload if isinstance(payload, dict) else {}
        return cls(**execution_ref_kwargs(data))


@dataclass(slots=True)
class ComplexTaskRun:
    run_id: str
    thread_id: str = ""
    objective: str = ""
    mode: ComplexTaskMode = ComplexTaskMode.ORCHESTRATED
    status: ComplexTaskRunStatus = ComplexTaskRunStatus.DRAFT
    current_phase: str = ""
    planner_provider: str = ""
    planner_model: str = ""
    planner_reasoning_effort: str = ""
    reviewer_policy: Dict[str, Any] = field(default_factory=dict)
    global_constraints: Dict[str, Any] = field(default_factory=dict)
    taskbook_version_current: int = 0
    accepted_facts: List[str] = field(default_factory=list)
    ready_card_ids: List[str] = field(default_factory=list)
    running_card_ids: List[str] = field(default_factory=list)
    blocked_card_ids: List[str] = field(default_factory=list)
    completed_card_ids: List[str] = field(default_factory=list)
    latest_event_seq: int = 0
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    final_summary: str = ""
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return complex_task_run_payload(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "ComplexTaskRun":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            **complex_task_run_kwargs(
                data,
                utc_now_iso_fn=utc_now_iso,
                schema_version_default=SCHEMA_VERSION,
            )
        )


@dataclass(slots=True)
class TaskbookSnapshot:
    taskbook_id: str
    run_id: str = ""
    version: int = 1
    derived_from_version: int = 0
    goal: str = ""
    success_definition: List[str] = field(default_factory=list)
    global_rules: Dict[str, Any] = field(default_factory=dict)
    assumptions: List[str] = field(default_factory=list)
    critical_path: List[str] = field(default_factory=list)
    open_risks: List[str] = field(default_factory=list)
    cards: List[str] = field(default_factory=list)
    planner_summary: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return taskbook_snapshot_payload(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "TaskbookSnapshot":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            **taskbook_snapshot_kwargs(
                data,
                utc_now_iso_fn=utc_now_iso,
                schema_version_default=SCHEMA_VERSION,
            )
        )


@dataclass(slots=True)
class TaskCard:
    card_id: str
    taskbook_version: int = 1
    title: str = ""
    goal: str = ""
    kind: TaskCardKind = TaskCardKind.READ_ONLY
    owned_files: List[str] = field(default_factory=list)
    allowed_paths: List[str] = field(default_factory=list)
    blocked_paths: List[str] = field(default_factory=list)
    out_of_scope: List[str] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)
    can_run_in_parallel: bool = False
    execution_mode: TaskCardExecutionMode = TaskCardExecutionMode.STAY_LOCAL
    executor_role: TaskCardExecutorRole = TaskCardExecutorRole.EXECUTOR
    acceptance_criteria: List[str] = field(default_factory=list)
    test_requirements: List[str] = field(default_factory=list)
    risk_hints: List[str] = field(default_factory=list)
    handoff_requirements: List[str] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return task_card_payload(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "TaskCard":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            **task_card_kwargs(data, schema_version_default=SCHEMA_VERSION)
        )


@dataclass(slots=True)
class TaskCardState:
    card_id: str
    status: TaskCardStatus = TaskCardStatus.DRAFT
    attempt: int = 0
    execution_refs: List[ExecutionRef] = field(default_factory=list)
    latest_result_ref: str = ""
    latest_acceptance_ref: str = ""
    dependency_status: TaskCardDependencyStatus = TaskCardDependencyStatus.PENDING
    owned_file_lock: bool = False
    last_scheduler_decision: str = ""
    last_error: str = ""
    queued_at: str = ""
    started_at: str = ""
    finished_at: str = ""
    updated_at: str = field(default_factory=utc_now_iso)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return taskbook_models_serialization_runtime.task_card_state_payload(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "TaskCardState":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            **taskbook_models_serialization_runtime.task_card_state_kwargs(
                data,
                execution_ref_from_dict=ExecutionRef.from_dict,
                utc_now_iso_fn=utc_now_iso,
                schema_version=SCHEMA_VERSION,
            )
        )


@dataclass(slots=True)
class CardResult:
    result_id: str
    run_id: str = ""
    card_id: str = ""
    attempt: int = 0
    status: CardResultStatus = CardResultStatus.REPORTED
    summary: str = ""
    modified_files: List[str] = field(default_factory=list)
    commands: List[str] = field(default_factory=list)
    test_commands: List[str] = field(default_factory=list)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    needs_review: bool = True
    rework_required: bool = False
    suggested_next_action: str = ""
    execution_ref: ExecutionRef | None = None
    reported_at: str = field(default_factory=utc_now_iso)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return taskbook_models_serialization_runtime.card_result_payload(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "CardResult":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            **taskbook_models_serialization_runtime.card_result_kwargs(
                data,
                execution_ref_from_dict=ExecutionRef.from_dict,
                utc_now_iso_fn=utc_now_iso,
                schema_version=SCHEMA_VERSION,
            )
        )


@dataclass(slots=True)
class CardAcceptance:
    acceptance_id: str
    run_id: str = ""
    card_id: str = ""
    result_id: str = ""
    decision: CardAcceptanceDecision = CardAcceptanceDecision.REJECT
    reason: str = ""
    accepted_facts_delta: List[str] = field(default_factory=list)
    followup_actions: List[Dict[str, Any]] = field(default_factory=list)
    reviewer_provider: str = ""
    reviewer_model: str = ""
    reviewed_at: str = field(default_factory=utc_now_iso)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return taskbook_models_serialization_runtime.card_acceptance_payload(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "CardAcceptance":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            **taskbook_models_serialization_runtime.card_acceptance_kwargs(
                data,
                utc_now_iso_fn=utc_now_iso,
                schema_version=SCHEMA_VERSION,
            )
        )


@dataclass(slots=True)
class OrchestrationEvent:
    seq: int
    run_id: str
    card_id: str = ""
    event_type: str = ""
    actor_type: str = ""
    actor_id: str = ""
    from_status: str = ""
    to_status: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now_iso)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        return taskbook_models_serialization_runtime.orchestration_event_payload(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "OrchestrationEvent":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            **taskbook_models_serialization_runtime.orchestration_event_kwargs(
                data,
                utc_now_iso_fn=utc_now_iso,
                schema_version=SCHEMA_VERSION,
            )
        )

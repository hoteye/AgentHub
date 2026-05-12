from __future__ import annotations

from typing import Any, Callable, Dict

from .taskbook_state import (
    ComplexTaskMode,
    ComplexTaskRunStatus,
    ExecutionRefKind,
    TaskCardExecutionMode,
    TaskCardExecutorRole,
    TaskCardKind,
    coerce_bool,
    coerce_dict,
    coerce_int,
    coerce_str_list,
    coerce_text,
    parse_enum,
)


IsoFn = Callable[[], str]


def execution_ref_payload(ref: Any) -> Dict[str, Any]:
    return {
        "kind": ref.kind.value,
        "task_id": ref.task_id,
        "agent_id": ref.agent_id,
        "dispatch_id": int(ref.dispatch_id),
        "provider_name": ref.provider_name,
        "model": ref.model,
        "route_label": ref.route_label,
    }


def execution_ref_kwargs(payload: Dict[str, Any] | None) -> Dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    return {
        "kind": parse_enum(
            ExecutionRefKind,
            data.get("kind") or ExecutionRefKind.LOCAL.value,
            field_name="execution_ref.kind",
        ),
        "task_id": coerce_text(data.get("task_id")),
        "agent_id": coerce_text(data.get("agent_id")),
        "dispatch_id": coerce_int(data.get("dispatch_id"), default=0, minimum=0),
        "provider_name": coerce_text(data.get("provider_name")),
        "model": coerce_text(data.get("model")),
        "route_label": coerce_text(data.get("route_label")),
    }


def complex_task_run_payload(run: Any) -> Dict[str, Any]:
    return {
        "schema_version": int(run.schema_version),
        "run_id": run.run_id,
        "thread_id": run.thread_id,
        "objective": run.objective,
        "mode": run.mode.value,
        "status": run.status.value,
        "current_phase": run.current_phase,
        "planner_provider": run.planner_provider,
        "planner_model": run.planner_model,
        "planner_reasoning_effort": run.planner_reasoning_effort,
        "reviewer_policy": dict(run.reviewer_policy),
        "global_constraints": dict(run.global_constraints),
        "taskbook_version_current": int(run.taskbook_version_current),
        "accepted_facts": list(run.accepted_facts),
        "ready_card_ids": list(run.ready_card_ids),
        "running_card_ids": list(run.running_card_ids),
        "blocked_card_ids": list(run.blocked_card_ids),
        "completed_card_ids": list(run.completed_card_ids),
        "latest_event_seq": int(run.latest_event_seq),
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "final_summary": run.final_summary,
    }


def complex_task_run_kwargs(
    payload: Dict[str, Any] | None,
    utc_now_iso_fn: IsoFn,
    schema_version_default: int,
) -> Dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    return {
        "run_id": coerce_text(data.get("run_id")),
        "thread_id": coerce_text(data.get("thread_id")),
        "objective": coerce_text(data.get("objective")),
        "mode": parse_enum(
            ComplexTaskMode,
            data.get("mode") or ComplexTaskMode.ORCHESTRATED.value,
            field_name="complex_task_run.mode",
        ),
        "status": parse_enum(
            ComplexTaskRunStatus,
            data.get("status") or ComplexTaskRunStatus.DRAFT.value,
            field_name="complex_task_run.status",
        ),
        "current_phase": coerce_text(data.get("current_phase")),
        "planner_provider": coerce_text(data.get("planner_provider")),
        "planner_model": coerce_text(data.get("planner_model")),
        "planner_reasoning_effort": coerce_text(data.get("planner_reasoning_effort")),
        "reviewer_policy": coerce_dict(data.get("reviewer_policy")),
        "global_constraints": coerce_dict(data.get("global_constraints")),
        "taskbook_version_current": coerce_int(
            data.get("taskbook_version_current"), default=0, minimum=0
        ),
        "accepted_facts": coerce_str_list(data.get("accepted_facts")),
        "ready_card_ids": coerce_str_list(data.get("ready_card_ids")),
        "running_card_ids": coerce_str_list(data.get("running_card_ids")),
        "blocked_card_ids": coerce_str_list(data.get("blocked_card_ids")),
        "completed_card_ids": coerce_str_list(data.get("completed_card_ids")),
        "latest_event_seq": coerce_int(data.get("latest_event_seq"), default=0, minimum=0),
        "created_at": coerce_text(
            data.get("created_at"), default=utc_now_iso_fn()
        ),
        "updated_at": coerce_text(
            data.get("updated_at"), default=utc_now_iso_fn()
        ),
        "final_summary": coerce_text(data.get("final_summary")),
        "schema_version": coerce_int(
            data.get("schema_version"),
            default=schema_version_default,
            minimum=1,
        ),
    }


def taskbook_snapshot_payload(snapshot: Any) -> Dict[str, Any]:
    return {
        "schema_version": int(snapshot.schema_version),
        "taskbook_id": snapshot.taskbook_id,
        "run_id": snapshot.run_id,
        "version": int(snapshot.version),
        "derived_from_version": int(snapshot.derived_from_version),
        "goal": snapshot.goal,
        "success_definition": list(snapshot.success_definition),
        "global_rules": dict(snapshot.global_rules),
        "assumptions": list(snapshot.assumptions),
        "critical_path": list(snapshot.critical_path),
        "open_risks": list(snapshot.open_risks),
        "cards": list(snapshot.cards),
        "planner_summary": snapshot.planner_summary,
        "created_at": snapshot.created_at,
    }


def taskbook_snapshot_kwargs(
    payload: Dict[str, Any] | None,
    utc_now_iso_fn: IsoFn,
    schema_version_default: int,
) -> Dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    return {
        "taskbook_id": coerce_text(data.get("taskbook_id")),
        "run_id": coerce_text(data.get("run_id")),
        "version": coerce_int(data.get("version"), default=1, minimum=1),
        "derived_from_version": coerce_int(
            data.get("derived_from_version"), default=0, minimum=0
        ),
        "goal": coerce_text(data.get("goal")),
        "success_definition": coerce_str_list(data.get("success_definition")),
        "global_rules": coerce_dict(data.get("global_rules")),
        "assumptions": coerce_str_list(data.get("assumptions")),
        "critical_path": coerce_str_list(data.get("critical_path")),
        "open_risks": coerce_str_list(data.get("open_risks")),
        "cards": coerce_str_list(data.get("cards")),
        "planner_summary": coerce_text(data.get("planner_summary")),
        "created_at": coerce_text(
            data.get("created_at"), default=utc_now_iso_fn()
        ),
        "schema_version": coerce_int(
            data.get("schema_version"),
            default=schema_version_default,
            minimum=1,
        ),
    }


def task_card_payload(card: Any) -> Dict[str, Any]:
    return {
        "schema_version": int(card.schema_version),
        "card_id": card.card_id,
        "taskbook_version": int(card.taskbook_version),
        "title": card.title,
        "goal": card.goal,
        "kind": card.kind.value,
        "owned_files": list(card.owned_files),
        "allowed_paths": list(card.allowed_paths),
        "blocked_paths": list(card.blocked_paths),
        "out_of_scope": list(card.out_of_scope),
        "depends_on": list(card.depends_on),
        "can_run_in_parallel": bool(card.can_run_in_parallel),
        "execution_mode": card.execution_mode.value,
        "executor_role": card.executor_role.value,
        "acceptance_criteria": list(card.acceptance_criteria),
        "test_requirements": list(card.test_requirements),
        "risk_hints": list(card.risk_hints),
        "handoff_requirements": list(card.handoff_requirements),
    }


def task_card_kwargs(payload: Dict[str, Any] | None, schema_version_default: int) -> Dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    return {
        "card_id": coerce_text(data.get("card_id")),
        "taskbook_version": coerce_int(data.get("taskbook_version"), default=1, minimum=1),
        "title": coerce_text(data.get("title")),
        "goal": coerce_text(data.get("goal")),
        "kind": parse_enum(
            TaskCardKind,
            data.get("kind") or TaskCardKind.READ_ONLY.value,
            field_name="task_card.kind",
        ),
        "owned_files": coerce_str_list(data.get("owned_files")),
        "allowed_paths": coerce_str_list(data.get("allowed_paths")),
        "blocked_paths": coerce_str_list(data.get("blocked_paths")),
        "out_of_scope": coerce_str_list(data.get("out_of_scope")),
        "depends_on": coerce_str_list(data.get("depends_on")),
        "can_run_in_parallel": coerce_bool(data.get("can_run_in_parallel"), default=False),
        "execution_mode": parse_enum(
            TaskCardExecutionMode,
            data.get("execution_mode") or TaskCardExecutionMode.STAY_LOCAL.value,
            field_name="task_card.execution_mode",
        ),
        "executor_role": parse_enum(
            TaskCardExecutorRole,
            data.get("executor_role") or TaskCardExecutorRole.EXECUTOR.value,
            field_name="task_card.executor_role",
        ),
        "acceptance_criteria": coerce_str_list(data.get("acceptance_criteria")),
        "test_requirements": coerce_str_list(data.get("test_requirements")),
        "risk_hints": coerce_str_list(data.get("risk_hints")),
        "handoff_requirements": coerce_str_list(data.get("handoff_requirements")),
        "schema_version": coerce_int(
            data.get("schema_version"),
            default=schema_version_default,
            minimum=1,
        ),
    }

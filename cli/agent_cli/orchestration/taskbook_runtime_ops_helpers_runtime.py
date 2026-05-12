from __future__ import annotations

from typing import Any

from cli.agent_cli.orchestration.complexity_router import classify_complexity
from cli.agent_cli.orchestration.taskbook_models import (
    ComplexTaskMode,
    ComplexTaskRun,
    ComplexTaskRunStatus,
    TaskCardState,
    utc_now_iso,
)
from cli.agent_cli.orchestration.taskbook_planner import plan_taskbook_from_text
from cli.agent_cli.orchestration.taskbook_projection import build_workflows_view
from cli.agent_cli.orchestration.taskbook_runtime_planning_adjustments_runtime import (
    apply_planning_adjustments,
    normalize_planning_adjustments,
    planning_adjustment_lines,
)
from cli.agent_cli.orchestration.taskbook_state import ExecutionRefKind

from . import taskbook_runtime_ops_helpers_continue_runtime
from .taskbook_runtime_results_runtime import latest_execution_ref
from .taskbook_runtime_support_runtime import (
    append_event,
    background_adapter_for_progress,
    looks_like_checklist,
    looks_like_taskbook_markdown,
    normalized_initial_state,
    planner_identity,
    refresh_operator_views,
    run_payload,
    runtime_services,
    selector_value,
    workflow_line,
)


def build_planned_orchestration_bundle(
    runtime: Any,
    source_text: str,
    *,
    run_id: str,
    planning_adjustments: dict[str, Any] | None = None,
    relaxed_taskbook: bool = False,
) -> dict[str, Any]:
    raw_text = str(source_text or "").strip()
    if not raw_text:
        raise ValueError("orchestrate requires task text or taskbook markdown")
    routing = classify_complexity(
        raw_text,
        has_taskbook_markdown=looks_like_taskbook_markdown(raw_text),
        has_checklist=looks_like_checklist(raw_text),
    )
    planner_provider, planner_model, planner_reasoning_effort = planner_identity(runtime)
    planned = plan_taskbook_from_text(
        run_id=run_id,
        source_text=raw_text,
        version=1,
        relaxed_markdown=relaxed_taskbook,
    )
    normalized_adjustments = normalize_planning_adjustments(planning_adjustments)
    apply_planning_adjustments(
        snapshot=planned.snapshot,
        cards=planned.cards,
        planning_adjustments=normalized_adjustments,
    )
    normalized_states = [normalized_initial_state(state) for state in planned.states]
    ready_card_ids = [state.card_id for state in normalized_states if state.status.value == "ready"]
    blocked_card_ids = [state.card_id for state in normalized_states if state.status.value != "ready"]
    return {
        "run_id": run_id,
        "routing": routing,
        "planner_provider": planner_provider,
        "planner_model": planner_model,
        "planner_reasoning_effort": planner_reasoning_effort,
        "planned": planned,
        "normalized_states": normalized_states,
        "ready_card_ids": ready_card_ids,
        "blocked_card_ids": blocked_card_ids,
        "planning_adjustments": normalized_adjustments,
    }


def preview_orchestration_run_impl(
    runtime: Any,
    source_text: str,
    *,
    run_id: str,
    planning_adjustments: dict[str, Any] | None = None,
    relaxed_taskbook: bool = False,
) -> dict[str, Any]:
    planned_bundle = build_planned_orchestration_bundle(
        runtime,
        source_text,
        run_id=run_id,
        planning_adjustments=planning_adjustments,
        relaxed_taskbook=relaxed_taskbook,
    )
    planned = planned_bundle["planned"]
    normalized_states = planned_bundle["normalized_states"]
    return {
        "preview_id": planned_bundle["run_id"],
        "objective": planned.snapshot.goal,
        "mode": ComplexTaskMode.ORCHESTRATED.value,
        "routing_mode": planned_bundle["routing"].mode,
        "routing_reasons": list(planned_bundle["routing"].reasons),
        "taskbook_source": planned.source,
        "taskbook_version": int(planned.snapshot.version),
        "planner_provider": planned_bundle["planner_provider"],
        "planner_model": planned_bundle["planner_model"],
        "planner_reasoning_effort": planned_bundle["planner_reasoning_effort"],
        "card_count": len(planned.cards),
        "ready_card_ids": list(planned_bundle["ready_card_ids"]),
        "blocked_card_ids": list(planned_bundle["blocked_card_ids"]),
        "planning_adjustments": dict(planned_bundle["planning_adjustments"]),
        "planning_adjustment_lines": planning_adjustment_lines(planned_bundle["planning_adjustments"]),
        "taskbook": planned.snapshot.to_dict(),
        "cards": [card.to_dict() for card in planned.cards],
        "card_states": [state.to_dict() for state in normalized_states],
    }


def create_orchestration_run_impl(
    runtime: Any,
    source_text: str,
    *,
    run_id: str,
    planning_adjustments: dict[str, Any] | None = None,
    relaxed_taskbook: bool = False,
) -> dict[str, Any]:
    planned_bundle = build_planned_orchestration_bundle(
        runtime,
        source_text,
        run_id=run_id,
        planning_adjustments=planning_adjustments,
        relaxed_taskbook=relaxed_taskbook,
    )
    services = runtime_services(runtime)
    planned = planned_bundle["planned"]
    routing = planned_bundle["routing"]
    planner_provider = planned_bundle["planner_provider"]
    planner_model = planned_bundle["planner_model"]
    planner_reasoning_effort = planned_bundle["planner_reasoning_effort"]
    ready_card_ids = planned_bundle["ready_card_ids"]
    blocked_card_ids = planned_bundle["blocked_card_ids"]
    planning_constraints = dict(planned_bundle["planning_adjustments"])
    normalized_states = planned_bundle["normalized_states"]
    raw_text = str(source_text or "").strip()
    run = ComplexTaskRun(
        run_id=run_id,
        thread_id=str(getattr(runtime, "thread_id", "") or "").strip(),
        objective=planned.snapshot.goal or raw_text.splitlines()[0].strip(),
        mode=ComplexTaskMode.ORCHESTRATED,
        status=ComplexTaskRunStatus.PLANNING,
        current_phase="taskbook_planning",
        planner_provider=planner_provider,
        planner_model=planner_model,
        planner_reasoning_effort=planner_reasoning_effort,
        taskbook_version_current=planned.snapshot.version,
        global_constraints=planning_constraints,
    )
    run.updated_at = utc_now_iso()
    services.storage.save_run(run)
    append_event(
        services,
        run,
        event_type="taskbook_planned",
        actor_type="runtime",
        to_status=ComplexTaskRunStatus.PLANNING.value,
        payload={
            "routing_mode": routing.mode,
            "routing_reasons": list(routing.reasons),
            "taskbook_source": planned.source,
            "card_ids": [card.card_id for card in planned.cards],
            "planning_adjustments": planning_constraints,
        },
    )
    services.storage.save_taskbook(planned.snapshot)
    for card, state in zip(planned.cards, normalized_states):
        services.storage.save_card_spec(run_id, card)
        services.storage.save_card_state(run_id, state)
    run.ready_card_ids = sorted(ready_card_ids)
    run.blocked_card_ids = sorted(blocked_card_ids)
    run.running_card_ids = []
    run.completed_card_ids = []
    run.status = ComplexTaskRunStatus.READY if ready_card_ids else ComplexTaskRunStatus.BLOCKED
    run.current_phase = "taskbook_ready" if ready_card_ids else "taskbook_blocked"
    run.updated_at = utc_now_iso()
    services.storage.save_run(run)
    append_event(
        services,
        run,
        event_type="initial_state_materialized",
        actor_type="runtime",
        from_status=ComplexTaskRunStatus.PLANNING.value,
        to_status=run.status.value,
        payload={
            "ready_card_ids": list(run.ready_card_ids),
            "blocked_card_ids": list(run.blocked_card_ids),
        },
    )
    refresh_operator_views(services, run_id)
    return run_payload(
        services,
        run,
        routing_mode=routing.mode,
        routing_reasons=routing.reasons,
        taskbook_source=planned.source,
    )


def payload_card_ids(payload: dict[str, Any], key: str) -> list[str]:
    return taskbook_runtime_ops_helpers_continue_runtime.payload_card_ids(payload, key)


def defer_progress_auto_dispatch(state: TaskCardState | None) -> bool:
    return taskbook_runtime_ops_helpers_continue_runtime.defer_progress_auto_dispatch(state)


def continue_pass_summary(pass_index: int, payload: dict[str, Any]) -> dict[str, Any]:
    return taskbook_runtime_ops_helpers_continue_runtime.continue_pass_summary(pass_index, payload)


def continue_orchestration_run_impl(
    runtime: Any,
    run_id: str,
    *,
    max_passes: int = 8,
    dispatch_ready: bool = True,
    progress_orchestration_run_fn: Any,
) -> dict[str, Any]:
    return taskbook_runtime_ops_helpers_continue_runtime.continue_orchestration_run_impl(
        runtime,
        run_id,
        max_passes=max_passes,
        dispatch_ready=dispatch_ready,
        progress_orchestration_run_fn=progress_orchestration_run_fn,
    )


def load_orchestration_bundle(runtime: Any, run_id: str) -> tuple[Any, ComplexTaskRun, dict[str, Any], dict[str, TaskCardState]]:
    services = runtime_services(runtime)
    bundle = services.storage.load_run_bundle(run_id)
    run = bundle.get("run") if isinstance(bundle, dict) else None
    if not isinstance(run, ComplexTaskRun):
        raise ValueError(f"unknown orchestration run: {run_id}")
    card_specs = dict(bundle.get("card_specs") or {})
    card_states = dict(bundle.get("card_states") or {})
    return services, run, card_specs, card_states


def background_review_adapter(runtime: Any) -> Any:
    from . import taskbook_runtime as taskbook_runtime_module

    background_builder = getattr(taskbook_runtime_module, "build_background_task_adapter", None)
    if callable(background_builder):
        try:
            adapter = background_builder(cwd=getattr(runtime, "cwd", None))
        except Exception as exc:
            raise ValueError("background task adapter unavailable for orchestration review") from exc
    else:
        adapter = background_adapter_for_progress(runtime)
    if adapter is None:
        raise ValueError("background task adapter unavailable for orchestration review")
    return adapter


def resolve_background_review_target(runtime: Any, run_id: str, card_id: str) -> tuple[Any, ComplexTaskRun, str]:
    resolved_run_id = str(run_id or "").strip()
    resolved_card_id = str(card_id or "").strip()
    if not resolved_run_id:
        raise ValueError("orchestration review requires a run_id")
    if not resolved_card_id:
        raise ValueError("orchestration review requires a card_id")
    _services, run, _card_specs, card_states = load_orchestration_bundle(runtime, resolved_run_id)
    state = card_states.get(resolved_card_id)
    if not isinstance(state, TaskCardState):
        raise ValueError(f"unknown orchestration card: {resolved_card_id}")
    execution_ref = latest_execution_ref(state)
    if execution_ref is None or execution_ref.kind is not ExecutionRefKind.BACKGROUND_TASK:
        raise ValueError(f"orchestration card is not backed by a background task: {resolved_card_id}")
    task_id = str(execution_ref.task_id or "").strip()
    if not task_id:
        raise ValueError(f"orchestration card has no background task id: {resolved_card_id}")
    adapter = background_review_adapter(runtime)
    payload = adapter.get_status(task_id) if hasattr(adapter, "get_status") else None
    if not isinstance(payload, dict):
        raise ValueError(f"background task not found: {task_id}")
    artifact = dict(payload.get("artifact") or {})
    if not artifact.get("staged_workspace"):
        raise ValueError(f"orchestration card has no staged workspace review: {resolved_card_id}")
    return adapter, run, task_id


def review_orchestration_card(
    runtime: Any,
    run_id: str,
    card_id: str,
    *,
    action: str,
    progress_orchestration_run_fn: Any,
) -> dict[str, Any]:
    adapter, _run, task_id = resolve_background_review_target(runtime, run_id, card_id)
    if action == "apply":
        operation = getattr(adapter, "apply_staged_changes", None)
    else:
        operation = getattr(adapter, "reject_staged_changes", None)
    if not callable(operation):
        raise ValueError("background task adapter does not support staged workspace review")
    review_payload = operation(task_id)
    if not isinstance(review_payload, dict):
        raise ValueError(f"background task not found: {task_id}")
    artifact = dict(review_payload.get("artifact") or {})
    if not artifact.get("staged_workspace"):
        raise ValueError(f"orchestration card has no staged workspace review: {card_id}")
    progress_payload = progress_orchestration_run_fn(runtime, run_id, dispatch_ready=action == "apply")
    return {
        **progress_payload,
        "card_id": str(card_id or "").strip(),
        "task_id": task_id,
        "review_action": action,
        "task_status": selector_value(review_payload.get("status")),
        "final_apply_state": selector_value(artifact.get("final_apply_state")),
        "applied_files": list(artifact.get("applied_files") or []),
    }


def list_orchestration_workflows_impl(runtime: Any, *, limit: int = 20) -> tuple[list[str], int]:
    try:
        services = runtime_services(runtime)
        rows = services.catalog.list_runs()
    except Exception:
        return ([], 0)
    lines: list[str] = []
    max_items = max(1, int(limit))
    for row in rows[:max_items]:
        run_id = str(row.get("run_id") or "").strip()
        if not run_id:
            continue
        bundle = services.storage.load_run_bundle(run_id)
        run = bundle.get("run") if isinstance(bundle, dict) else None
        if not isinstance(run, ComplexTaskRun):
            continue
        view = build_workflows_view(bundle)
        lines.append(workflow_line(run, view))
    return (lines, len(lines))

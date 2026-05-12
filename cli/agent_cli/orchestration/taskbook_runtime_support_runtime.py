from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cli.agent_cli.background_tasks import build_background_task_adapter
from cli.agent_cli.orchestration import (
    taskbook_runtime_support_helpers_runtime as support_helpers_runtime,
)
from cli.agent_cli.orchestration import (
    taskbook_runtime_support_projection_runtime as support_projection_runtime,
)
from cli.agent_cli.orchestration.taskbook_catalog import TaskbookCatalog
from cli.agent_cli.orchestration.taskbook_models import (
    ComplexTaskRun,
    OrchestrationEvent,
    TaskCardState,
    utc_now_iso,
)
from cli.agent_cli.orchestration.taskbook_projection import write_projections
from cli.agent_cli.orchestration.taskbook_state import (
    CardResultStatus,
    ComplexTaskRunStatus,
    TaskCardDependencyStatus,
    TaskCardStatus,
)
from cli.agent_cli.orchestration.taskbook_storage import TaskbookStorage


@dataclass(slots=True)
class OrchestrationRuntimeServices:
    root_dir: Path
    storage: TaskbookStorage
    catalog: TaskbookCatalog


def runtime_root(runtime: Any) -> Path:
    cwd = getattr(runtime, "cwd", None)
    base = Path(cwd) if cwd is not None else Path.cwd()
    try:
        return base.expanduser().resolve(strict=False)
    except OSError:
        return base.expanduser()


def runtime_services(runtime: Any) -> OrchestrationRuntimeServices:
    root_dir = runtime_root(runtime)
    current_root = str(root_dir)
    cached = getattr(runtime, "_orchestration_runtime_services_cache", None)
    cached_root = str(getattr(runtime, "_orchestration_runtime_services_cwd", "") or "").strip()
    if isinstance(cached, OrchestrationRuntimeServices) and cached_root == current_root:
        return cached
    storage = TaskbookStorage.default(root=root_dir)
    catalog = TaskbookCatalog.default(root=storage.root_dir)
    services = OrchestrationRuntimeServices(
        root_dir=root_dir,
        storage=storage,
        catalog=catalog,
    )
    runtime._orchestration_runtime_services_cache = services
    runtime._orchestration_runtime_services_cwd = current_root
    return services


def _compact_text_list(values: list[str]) -> list[str]:
    return support_helpers_runtime.compact_text_list(values)


def _replan_followup_summary(
    *,
    replan_contract_version: int,
    replan_candidates: list[dict[str, Any]],
    replan_pending: list[dict[str, Any]],
    replan_pending_card_ids: list[str],
    operator_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    return support_helpers_runtime.replan_followup_summary(
        replan_contract_version=replan_contract_version,
        replan_candidates=replan_candidates,
        replan_pending=replan_pending,
        replan_pending_card_ids=replan_pending_card_ids,
        operator_actions=operator_actions,
    )


def run_payload(
    services: OrchestrationRuntimeServices,
    run: ComplexTaskRun,
    *,
    routing_mode: str,
    routing_reasons: list[str],
    taskbook_source: str,
    selected_card_ids: list[str] | None = None,
    dispatched_card_ids: list[str] | None = None,
    dispatch_refs: list[str] | None = None,
    synced_card_ids: list[str] | None = None,
    accepted_card_ids: list[str] | None = None,
    unlocked_card_ids: list[str] | None = None,
    replan_candidates: list[dict[str, Any]] | None = None,
    replan_pending: list[dict[str, Any]] | None = None,
    replan_pending_card_ids: list[str] | None = None,
    replan_contract_version: int | None = None,
    replan_operator_action_ids: list[str] | None = None,
    operator_actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return support_helpers_runtime.run_payload(
        services,
        run,
        routing_mode=routing_mode,
        routing_reasons=routing_reasons,
        taskbook_source=taskbook_source,
        selected_card_ids=selected_card_ids,
        dispatched_card_ids=dispatched_card_ids,
        dispatch_refs=dispatch_refs,
        synced_card_ids=synced_card_ids,
        accepted_card_ids=accepted_card_ids,
        unlocked_card_ids=unlocked_card_ids,
        replan_candidates=replan_candidates,
        replan_pending=replan_pending,
        replan_pending_card_ids=replan_pending_card_ids,
        replan_contract_version=replan_contract_version,
        replan_operator_action_ids=replan_operator_action_ids,
        operator_actions=operator_actions,
    )


def progress_payload_mutated(payload: dict[str, Any]) -> bool:
    return any(
        bool(payload.get(key))
        for key in (
            "synced_card_ids",
            "accepted_card_ids",
            "unlocked_card_ids",
            "selected_card_ids",
            "dispatched_card_ids",
            "dispatch_refs",
        )
    )


def extend_unique(target: list[str], values: Any) -> None:
    support_helpers_runtime.extend_unique(target, values)


def workflow_line(run: ComplexTaskRun, view: dict[str, Any]) -> str:
    return support_projection_runtime.workflow_line(run, view)


def taskbook_summary_label(run: ComplexTaskRun, view: dict[str, Any]) -> str:
    return support_projection_runtime.taskbook_summary_label(run, view)


def projection_summary_label(view: dict[str, Any]) -> str:
    return support_projection_runtime.projection_summary_label(view)


def current_card_label(run: ComplexTaskRun, view: dict[str, Any]) -> str:
    return support_projection_runtime.current_card_label(run, view)


def blocker_label(view: dict[str, Any]) -> str:
    return support_projection_runtime.blocker_label(view)


def latest_outcome_label(view: dict[str, Any]) -> str:
    return support_projection_runtime.latest_outcome_label(view)


def latest_acceptance_label(view: dict[str, Any]) -> str:
    return support_projection_runtime.latest_acceptance_label(view)


def review_reason_label(view: dict[str, Any]) -> str:
    return support_projection_runtime.review_reason_label(view)


def current_card_latest_result_hint(run: ComplexTaskRun, view: dict[str, Any]) -> str:
    return support_projection_runtime.current_card_latest_result_hint(run, view)


def dispatch_ref_label(card_id: str, state: TaskCardState) -> str:
    return support_projection_runtime.dispatch_ref_label(card_id, state)


def append_event(
    services: OrchestrationRuntimeServices,
    run: ComplexTaskRun,
    *,
    event_type: str,
    actor_type: str,
    from_status: str = "",
    to_status: str = "",
    payload: dict[str, Any] | None = None,
) -> None:
    run.latest_event_seq = max(0, int(run.latest_event_seq)) + 1
    event = OrchestrationEvent(
        seq=run.latest_event_seq,
        run_id=run.run_id,
        event_type=event_type,
        actor_type=actor_type,
        from_status=from_status,
        to_status=to_status,
        payload=dict(payload or {}),
    )
    services.storage.append_event(event)
    services.storage.save_run(run)


def normalized_initial_state(state: TaskCardState) -> TaskCardState:
    updated = TaskCardState.from_dict(state.to_dict())
    if updated.dependency_status is TaskCardDependencyStatus.SATISFIED:
        updated.status = TaskCardStatus.READY
        updated.last_scheduler_decision = "intake_ready"
    else:
        updated.status = TaskCardStatus.DRAFT
        updated.last_scheduler_decision = "intake_waiting_dependencies"
    updated.updated_at = utc_now_iso()
    return updated


def background_adapter_for_progress(runtime: Any) -> Any | None:
    try:
        return build_background_task_adapter(cwd=getattr(runtime, "cwd", None))
    except Exception:
        return None


def delegated_snapshot_index(runtime: Any) -> dict[str, dict[str, Any]]:
    return support_helpers_runtime.delegated_snapshot_index(runtime)


def refresh_run_status(run: ComplexTaskRun, card_states: dict[str, TaskCardState]) -> None:
    ready = list(run.ready_card_ids or [])
    running = list(run.running_card_ids or [])
    blocked = list(run.blocked_card_ids or [])
    completed = list(run.completed_card_ids or [])
    review = [
        card_id
        for card_id, state in sorted(card_states.items())
        if state.status is TaskCardStatus.REVIEW
    ]
    if card_states and len(completed) == len(card_states):
        run.status = ComplexTaskRunStatus.COMPLETED
        run.current_phase = "taskbook_completed"
        run.final_summary = run.final_summary or "all cards accepted"
        return
    if review:
        run.status = ComplexTaskRunStatus.REVIEW
        run.current_phase = "card_review_pending"
        return
    if running:
        run.status = ComplexTaskRunStatus.RUNNING
        run.current_phase = "cards_running"
        return
    if ready:
        run.status = ComplexTaskRunStatus.READY
        run.current_phase = "taskbook_ready"
        return
    if blocked:
        run.status = ComplexTaskRunStatus.BLOCKED
        run.current_phase = "taskbook_blocked"
        return
    run.status = ComplexTaskRunStatus.DRAFT
    run.current_phase = "taskbook_draft"


def result_id(card_id: str, attempt: int, execution_ref: Any, fingerprint: str) -> str:
    return support_projection_runtime.result_id(card_id, attempt, execution_ref, fingerprint)


def acceptance_id(card_id: str, result_id_value: str, decision: str) -> str:
    return support_projection_runtime.acceptance_id(card_id, result_id_value, decision)


def string_list(value: Any) -> list[str]:
    return support_projection_runtime.string_list(value)


def selector_value(value: Any) -> str:
    return support_projection_runtime.selector_value(value)


def planner_identity(runtime: Any) -> tuple[str, str, str]:
    return support_helpers_runtime.planner_identity(runtime, selector_value_fn=selector_value)


def refresh_operator_views(services: OrchestrationRuntimeServices, run_id: str) -> None:
    try:
        write_projections(services.storage, run_id)
    except Exception:
        pass
    services.catalog.rebuild_run_index(services.storage, run_id)


def looks_like_taskbook_markdown(text: str) -> bool:
    return support_projection_runtime.looks_like_taskbook_markdown(text)


def looks_like_checklist(text: str) -> bool:
    return support_projection_runtime.looks_like_checklist(text)


def test_commands(commands: list[str]) -> list[str]:
    return support_projection_runtime.test_commands(commands)


def result_reported_at(payload: dict[str, Any]) -> str:
    return support_projection_runtime.result_reported_at(payload, utc_now_iso_fn=utc_now_iso)


def delegated_terminal_result_status(
    snapshot: dict[str, Any], *, result_contract: dict[str, Any]
) -> CardResultStatus | None:
    return support_projection_runtime.delegated_terminal_result_status(
        snapshot, result_contract=result_contract
    )


def background_terminal_result_status(
    payload: dict[str, Any], *, artifact: dict[str, Any]
) -> CardResultStatus | None:
    return support_projection_runtime.background_terminal_result_status(payload, artifact=artifact)


def visible_child_task_run_snapshots(runtime: Any) -> list[dict[str, Any]]:
    backend = getattr(runtime, "visible_child_tab_backend", None)
    snapshot_fn = getattr(backend, "visible_child_task_run_snapshots", None)
    if not callable(snapshot_fn):
        return []
    parent_tab_id = str(getattr(runtime, "visible_child_parent_tab_id", "") or "").strip()
    if not parent_tab_id:
        parent_tab_id = str(getattr(backend, "active_tab_id", "") or "").strip()
    try:
        return [
            dict(item) for item in list(snapshot_fn(parent_tab_id) or []) if isinstance(item, dict)
        ]
    except Exception:
        return []


def visible_child_terminal_result_status(snapshot: dict[str, Any]) -> CardResultStatus | None:
    terminal_state = selector_value(snapshot.get("terminal_state")).lower()
    state = selector_value(snapshot.get("state")).lower()
    if terminal_state == "completed":
        return CardResultStatus.COMPLETED
    if terminal_state == "failed":
        return CardResultStatus.FAILED
    if terminal_state == "cancelled":
        return CardResultStatus.CANCELLED
    if terminal_state == "timed_out":
        return CardResultStatus.TIMED_OUT
    if terminal_state == "interrupted":
        return CardResultStatus.CANCELLED
    if state in {"queued", "running", "waiting_approval", "waiting_input"}:
        return None
    return None

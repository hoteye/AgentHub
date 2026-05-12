from __future__ import annotations

from typing import Any

from cli.agent_cli.orchestration.taskbook_models import (
    ComplexTaskRun,
    TaskCardState,
    new_orchestration_id,
    utc_now_iso,
)
from cli.agent_cli.orchestration.taskbook_scheduler import select_ready_cards
from cli.agent_cli.orchestration.taskbook_state import TaskCardStatus

from . import taskbook_runtime_ops_helpers_runtime
from .taskbook_runtime_results_runtime import (
    apply_progress_acceptance,
    dispatch_selected_cards,
    ingest_progress_results,
)
from .taskbook_runtime_support_runtime import (
    append_event,
    background_adapter_for_progress,
    delegated_snapshot_index,
    refresh_operator_views,
    refresh_run_status,
    run_payload,
    runtime_services,
)


def preview_orchestration_run(
    runtime: Any,
    source_text: str,
    *,
    planning_adjustments: dict[str, Any] | None = None,
    relaxed_taskbook: bool = False,
) -> dict[str, Any]:
    return taskbook_runtime_ops_helpers_runtime.preview_orchestration_run_impl(
        runtime,
        source_text,
        run_id=new_orchestration_id("preview"),
        planning_adjustments=planning_adjustments,
        relaxed_taskbook=relaxed_taskbook,
    )


def create_orchestration_run(
    runtime: Any,
    source_text: str,
    *,
    planning_adjustments: dict[str, Any] | None = None,
    relaxed_taskbook: bool = False,
) -> dict[str, Any]:
    return taskbook_runtime_ops_helpers_runtime.create_orchestration_run_impl(
        runtime,
        source_text,
        run_id=new_orchestration_id("run"),
        planning_adjustments=planning_adjustments,
        relaxed_taskbook=relaxed_taskbook,
    )


def _build_planned_orchestration_bundle(
    runtime: Any,
    source_text: str,
    *,
    run_id: str,
    planning_adjustments: dict[str, Any] | None = None,
    relaxed_taskbook: bool = False,
) -> dict[str, Any]:
    return taskbook_runtime_ops_helpers_runtime.build_planned_orchestration_bundle(
        runtime,
        source_text,
        run_id=run_id,
        planning_adjustments=planning_adjustments,
        relaxed_taskbook=relaxed_taskbook,
    )


def dispatch_orchestration_run(runtime: Any, run_id: str) -> dict[str, Any]:
    resolved_run_id = str(run_id or "").strip()
    if not resolved_run_id:
        raise ValueError("orchestrate_dispatch requires a run_id")
    services = runtime_services(runtime)
    bundle = services.storage.load_run_bundle(resolved_run_id)
    run = bundle.get("run") if isinstance(bundle, dict) else None
    if not isinstance(run, ComplexTaskRun):
        raise ValueError(f"unknown orchestration run: {resolved_run_id}")
    card_specs = dict(bundle.get("card_specs") or {})
    card_states = dict(bundle.get("card_states") or {})
    selection = select_ready_cards(run, card_specs=card_specs, card_states=card_states)
    updated_run, updated_states, dispatched_cards, dispatch_refs = dispatch_selected_cards(
        runtime,
        run=selection.run,
        card_specs=card_specs,
        card_states=selection.card_states,
        selected_card_ids=selection.selected_card_ids,
    )
    if dispatched_cards:
        updated_run.current_phase = "cards_dispatched"
    updated_run.updated_at = utc_now_iso()
    services.storage.save_run(updated_run)
    for state in updated_states.values():
        services.storage.save_card_state(updated_run.run_id, state)
    append_event(
        services,
        updated_run,
        event_type="cards_dispatched",
        actor_type="runtime",
        from_status=run.status.value,
        to_status=updated_run.status.value,
        payload={
            "selected_card_ids": list(selection.selected_card_ids),
            "dispatched_card_ids": list(dispatched_cards),
            "blocked_card_ids": list(selection.blocked_card_ids),
            "skipped_card_ids": list(selection.skipped_card_ids),
        },
    )
    refresh_operator_views(services, updated_run.run_id)
    return run_payload(
        services,
        updated_run,
        routing_mode="orchestrated",
        routing_reasons=[],
        taskbook_source="dispatch",
        selected_card_ids=selection.selected_card_ids,
        dispatched_card_ids=dispatched_cards,
        dispatch_refs=dispatch_refs,
    )


def progress_orchestration_run(runtime: Any, run_id: str, *, dispatch_ready: bool = True) -> dict[str, Any]:
    resolved_run_id = str(run_id or "").strip()
    if not resolved_run_id:
        raise ValueError("orchestrate_progress requires a run_id")
    services = runtime_services(runtime)
    bundle = services.storage.load_run_bundle(resolved_run_id)
    run = bundle.get("run") if isinstance(bundle, dict) else None
    if not isinstance(run, ComplexTaskRun):
        raise ValueError(f"unknown orchestration run: {resolved_run_id}")
    card_specs = dict(bundle.get("card_specs") or {})
    card_states = dict(bundle.get("card_states") or {})
    delegated_index = delegated_snapshot_index(runtime)
    from . import taskbook_runtime as taskbook_runtime_module

    background_builder = getattr(taskbook_runtime_module, "build_background_task_adapter", None)
    if callable(background_builder):
        try:
            background_adapter = background_builder(cwd=getattr(runtime, "cwd", None))
        except Exception:
            background_adapter = None
    else:
        background_adapter = background_adapter_for_progress(runtime)
    updated_run, updated_states, synced_results = ingest_progress_results(
        runtime,
        services=services,
        run=run,
        card_specs=card_specs,
        card_states=card_states,
        delegated_index=delegated_index,
        background_adapter=background_adapter,
    )
    updated_run, updated_states, accepted_cards, blocked_cards, unlocked_cards, acceptance_followups = apply_progress_acceptance(
        runtime,
        services=services,
        run=updated_run,
        card_specs=card_specs,
        card_states=updated_states,
    )
    selected_card_ids: list[str] = []
    dispatched_card_ids: list[str] = []
    dispatch_refs: list[str] = []
    if dispatch_ready:
        states_before_selection = {
            card_id: TaskCardState.from_dict(state.to_dict())
            for card_id, state in updated_states.items()
        }
        selection = select_ready_cards(updated_run, card_specs=card_specs, card_states=updated_states)
        updated_run = selection.run
        updated_states = selection.card_states
        selected_card_ids = list(selection.selected_card_ids)
        deferred_card_ids = [
            card_id
            for card_id in selected_card_ids
            if _defer_progress_auto_dispatch(states_before_selection.get(card_id))
        ]
        if deferred_card_ids:
            deferred_card_id_set = set(deferred_card_ids)
            selected_card_ids = [card_id for card_id in selected_card_ids if card_id not in deferred_card_id_set]
            for card_id in deferred_card_ids:
                state = updated_states.get(card_id)
                if not isinstance(state, TaskCardState):
                    continue
                state.status = TaskCardStatus.READY
                state.last_scheduler_decision = "deferred_after_progress_acceptance"
                state.updated_at = utc_now_iso()
            updated_run.running_card_ids = [
                card_id
                for card_id in list(updated_run.running_card_ids or [])
                if card_id not in deferred_card_id_set
            ]
            ready_card_ids = list(updated_run.ready_card_ids or [])
            for card_id in deferred_card_ids:
                if card_id not in ready_card_ids:
                    ready_card_ids.append(card_id)
            updated_run.ready_card_ids = sorted(ready_card_ids)
        updated_run, updated_states, dispatched_card_ids, dispatch_refs = dispatch_selected_cards(
            runtime,
            run=updated_run,
            card_specs=card_specs,
            card_states=updated_states,
            selected_card_ids=selected_card_ids,
        )
        if dispatched_card_ids:
            append_event(
                services,
                updated_run,
                event_type="cards_dispatched_after_progress",
                actor_type="runtime",
                from_status=run.status.value,
                to_status=updated_run.status.value,
                payload={
                    "selected_card_ids": list(selected_card_ids),
                    "dispatched_card_ids": list(dispatched_card_ids),
                },
            )
    refresh_run_status(updated_run, updated_states)
    updated_run.updated_at = utc_now_iso()
    services.storage.save_run(updated_run)
    for state in updated_states.values():
        services.storage.save_card_state(updated_run.run_id, state)
    refresh_operator_views(services, updated_run.run_id)
    return run_payload(
        services,
        updated_run,
        routing_mode="orchestrated",
        routing_reasons=[],
        taskbook_source="progress",
        selected_card_ids=selected_card_ids,
        dispatched_card_ids=dispatched_card_ids,
        dispatch_refs=dispatch_refs,
        synced_card_ids=synced_results,
        accepted_card_ids=accepted_cards,
        unlocked_card_ids=sorted(set(unlocked_cards)),
        replan_candidates=list(acceptance_followups.get("replan_candidates") or []),
        replan_pending=list(acceptance_followups.get("replan_pending") or []),
        replan_pending_card_ids=list(acceptance_followups.get("replan_pending_card_ids") or []),
        replan_contract_version=int(acceptance_followups.get("replan_contract_version") or 0),
        replan_operator_action_ids=list(acceptance_followups.get("replan_operator_action_ids") or []),
        operator_actions=list(acceptance_followups.get("operator_actions") or []),
    )


def _payload_card_ids(payload: dict[str, Any], key: str) -> list[str]:
    return taskbook_runtime_ops_helpers_runtime.payload_card_ids(payload, key)


def _defer_progress_auto_dispatch(state: TaskCardState | None) -> bool:
    return taskbook_runtime_ops_helpers_runtime.defer_progress_auto_dispatch(state)


def _continue_pass_summary(pass_index: int, payload: dict[str, Any]) -> dict[str, Any]:
    return taskbook_runtime_ops_helpers_runtime.continue_pass_summary(pass_index, payload)


def continue_orchestration_run(
    runtime: Any,
    run_id: str,
    *,
    max_passes: int = 8,
    dispatch_ready: bool = True,
) -> dict[str, Any]:
    return taskbook_runtime_ops_helpers_runtime.continue_orchestration_run_impl(
        runtime,
        run_id,
        max_passes=max_passes,
        dispatch_ready=dispatch_ready,
        progress_orchestration_run_fn=progress_orchestration_run,
    )


def _load_orchestration_bundle(runtime: Any, run_id: str) -> tuple[Any, ComplexTaskRun, dict[str, Any], dict[str, TaskCardState]]:
    return taskbook_runtime_ops_helpers_runtime.load_orchestration_bundle(runtime, run_id)


def _background_review_adapter(runtime: Any) -> Any:
    return taskbook_runtime_ops_helpers_runtime.background_review_adapter(runtime)


def _resolve_background_review_target(runtime: Any, run_id: str, card_id: str) -> tuple[Any, ComplexTaskRun, str]:
    return taskbook_runtime_ops_helpers_runtime.resolve_background_review_target(runtime, run_id, card_id)


def _review_orchestration_card(runtime: Any, run_id: str, card_id: str, *, action: str) -> dict[str, Any]:
    return taskbook_runtime_ops_helpers_runtime.review_orchestration_card(
        runtime,
        run_id,
        card_id,
        action=action,
        progress_orchestration_run_fn=progress_orchestration_run,
    )


def apply_orchestration_card(runtime: Any, run_id: str, card_id: str) -> dict[str, Any]:
    return _review_orchestration_card(runtime, run_id, card_id, action="apply")


def reject_orchestration_card(runtime: Any, run_id: str, card_id: str) -> dict[str, Any]:
    return _review_orchestration_card(runtime, run_id, card_id, action="reject")


def list_orchestration_workflows(runtime: Any, *, limit: int = 20) -> tuple[list[str], int]:
    return taskbook_runtime_ops_helpers_runtime.list_orchestration_workflows_impl(runtime, limit=limit)

from __future__ import annotations

from typing import Any

from cli.agent_cli.orchestration.taskbook_acceptance import (
    apply_acceptance_decision,
    ingest_card_result,
)
from cli.agent_cli.orchestration.taskbook_dispatch import dispatch_task_card
from cli.agent_cli.orchestration.taskbook_models import (
    CardAcceptance,
    CardResult,
    ComplexTaskRun,
    ExecutionRef,
    TaskCard,
    TaskCardState,
    utc_now_iso,
)
from cli.agent_cli.orchestration.taskbook_state import (
    ExecutionRefKind,
)

from . import (
    taskbook_runtime_results_assembly_runtime,
    taskbook_runtime_results_helper_runtime,
    taskbook_runtime_results_progress_runtime,
)
from .taskbook_runtime_support_runtime import (
    acceptance_id,
    append_event,
    background_terminal_result_status,
    dispatch_ref_label,
    planner_identity,
    refresh_run_status,
    result_id,
    result_reported_at,
    runtime_root,
    selector_value,
    string_list,
    test_commands,
    visible_child_task_run_snapshots,
    visible_child_terminal_result_status,
)


def _replan_followup_contract_payload(
    followup: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], str, dict[str, Any]]:
    return taskbook_runtime_results_assembly_runtime.replan_followup_contract_payload(followup)


def _replan_followup_progress_summary(
    *,
    contract_version: int,
    candidates: list[dict[str, Any]],
    pending: list[dict[str, Any]],
    pending_card_ids: list[str],
    operator_actions: list[dict[str, Any]],
) -> dict[str, Any]:
    return taskbook_runtime_results_assembly_runtime.replan_followup_progress_summary(
        contract_version=contract_version,
        candidates=candidates,
        pending=pending,
        pending_card_ids=pending_card_ids,
        operator_actions=operator_actions,
    )


def dispatch_selected_cards(
    runtime: Any,
    *,
    run: ComplexTaskRun,
    card_specs: dict[str, TaskCard],
    card_states: dict[str, TaskCardState],
    selected_card_ids: list[str],
) -> tuple[ComplexTaskRun, dict[str, TaskCardState], list[str], list[str]]:
    planner_provider, planner_model, planner_reasoning_effort = planner_identity(runtime)
    from cli.agent_cli.background_tasks import build_background_task_adapter

    background_adapter = build_background_task_adapter(cwd=getattr(runtime, "cwd", None))
    if not bool(getattr(getattr(background_adapter, "config", None), "enabled", False)):
        background_adapter = None
    updated_run = ComplexTaskRun.from_dict(run.to_dict())
    updated_states = {
        card_id: TaskCardState.from_dict(state.to_dict()) for card_id, state in card_states.items()
    }
    dispatched_cards: list[str] = []
    dispatch_refs: list[str] = []
    for card_id in selected_card_ids:
        card = card_specs.get(card_id)
        state = updated_states.get(card_id)
        if not isinstance(card, TaskCard) or not isinstance(state, TaskCardState):
            continue
        dispatch = dispatch_task_card(
            updated_run,
            card,
            state,
            runtime=runtime,
            background_adapter=background_adapter,
            provider=planner_provider or None,
            model=planner_model or None,
            reasoning_effort=planner_reasoning_effort or None,
            cwd=str(getattr(runtime, "cwd", "") or "").strip() or None,
        )
        updated_states[card_id] = dispatch.state
        dispatched_cards.append(card_id)
        dispatch_refs.append(dispatch_ref_label(card_id, dispatch.state))
    refresh_run_status(updated_run, updated_states)
    return (updated_run, updated_states, dispatched_cards, dispatch_refs)


def latest_execution_ref(state: TaskCardState) -> ExecutionRef | None:
    refs = list(state.execution_refs or [])
    if not refs:
        return None
    return refs[-1]


def relative_paths(runtime: Any, value: Any) -> list[str]:
    return taskbook_runtime_results_helper_runtime.relative_paths(
        runtime_root(runtime),
        value,
        string_list_fn=string_list,
    )


def delegated_commands(snapshot: dict[str, Any]) -> list[str]:
    return taskbook_runtime_results_helper_runtime.delegated_commands(
        snapshot,
        selector_value_fn=selector_value,
    )


def delegated_card_result(
    runtime: Any,
    *,
    run: ComplexTaskRun,
    card: TaskCard,
    state: TaskCardState,
    execution_ref: ExecutionRef,
    delegated_index: dict[str, dict[str, Any]],
    delegated_terminal_result_status_fn: Any,
) -> CardResult | None:
    return taskbook_runtime_results_assembly_runtime.delegated_card_result(
        runtime_root_value=runtime_root(runtime),
        run=run,
        card=card,
        state=state,
        execution_ref=execution_ref,
        delegated_index=delegated_index,
        delegated_terminal_result_status_fn=delegated_terminal_result_status_fn,
        result_id_fn=result_id,
        selector_value_fn=selector_value,
        string_list_fn=string_list,
        test_commands_fn=test_commands,
        utc_now_iso_fn=utc_now_iso,
    )


def background_card_result(
    *,
    run: ComplexTaskRun,
    card: TaskCard,
    state: TaskCardState,
    execution_ref: ExecutionRef,
    background_adapter: Any | None,
) -> CardResult | None:
    return taskbook_runtime_results_assembly_runtime.background_card_result(
        run=run,
        card=card,
        state=state,
        execution_ref=execution_ref,
        background_adapter=background_adapter,
        background_terminal_result_status_fn=background_terminal_result_status,
        result_id_fn=result_id,
        result_reported_at_fn=result_reported_at,
        selector_value_fn=selector_value,
        string_list_fn=string_list,
        test_commands_fn=test_commands,
    )


def visible_child_tab_card_result(
    *,
    run: ComplexTaskRun,
    card: TaskCard,
    state: TaskCardState,
    execution_ref: ExecutionRef,
    snapshots: list[dict[str, Any]],
) -> CardResult | None:
    for snapshot in snapshots:
        if str(snapshot.get("tab_id") or "").strip() != str(execution_ref.agent_id or "").strip():
            continue
        terminal_status = visible_child_terminal_result_status(snapshot)
        if terminal_status is None:
            continue
        return taskbook_runtime_results_assembly_runtime.visible_child_tab_card_result(
            run=run,
            card=card,
            state=state,
            execution_ref=execution_ref,
            snapshot=snapshot,
            terminal_status=terminal_status,
            result_id_fn=result_id,
            selector_value_fn=selector_value,
            utc_now_iso_fn=utc_now_iso,
        )
    return None


def sync_card_terminal_result(
    runtime: Any,
    *,
    services: Any,
    run: ComplexTaskRun,
    card: TaskCard,
    state: TaskCardState,
    delegated_index: dict[str, dict[str, Any]],
    background_adapter: Any | None,
    delegated_terminal_result_status_fn: Any,
) -> CardResult | None:
    execution_ref = latest_execution_ref(state)
    if execution_ref is None:
        return None
    if execution_ref.kind is ExecutionRefKind.DELEGATED_SUBAGENT:
        result = delegated_card_result(
            runtime,
            run=run,
            card=card,
            state=state,
            execution_ref=execution_ref,
            delegated_index=delegated_index,
            delegated_terminal_result_status_fn=delegated_terminal_result_status_fn,
        )
    elif execution_ref.kind is ExecutionRefKind.BACKGROUND_TASK:
        result = background_card_result(
            run=run,
            card=card,
            state=state,
            execution_ref=execution_ref,
            background_adapter=background_adapter,
        )
    elif execution_ref.kind is ExecutionRefKind.VISIBLE_CHILD_TAB:
        result = visible_child_tab_card_result(
            run=run,
            card=card,
            state=state,
            execution_ref=execution_ref,
            snapshots=visible_child_task_run_snapshots(runtime),
        )
    else:
        result = None
    if result is None:
        return None
    latest_result = services.storage.latest_card_result(run.run_id, card.card_id)
    if latest_result is not None and latest_result.result_id == result.result_id:
        return None
    services.storage.append_card_result(result)
    return result


def auto_acceptance_for_result(
    run: ComplexTaskRun,
    *,
    card: TaskCard,
    state: TaskCardState,
    result: CardResult,
    reviewer_provider: str,
    reviewer_model: str,
    latest_acceptance: CardAcceptance | None = None,
) -> CardAcceptance | None:
    if (
        isinstance(latest_acceptance, CardAcceptance)
        and latest_acceptance.result_id == result.result_id
    ):
        return None
    decision, reason, accepted_facts = (
        taskbook_runtime_results_helper_runtime.auto_acceptance_decision(
            result,
            card=card,
            state=state,
            reviewer_policy=run.reviewer_policy,
        )
    )
    followup_actions = taskbook_runtime_results_helper_runtime.replan_followup_actions(
        result=result,
        decision=decision,
        reason=reason,
        card=card,
        state=state,
        reviewer_policy=run.reviewer_policy,
    )
    return taskbook_runtime_results_helper_runtime.build_acceptance(
        acceptance_id_value=acceptance_id(card.card_id, result.result_id, decision.value),
        run_id=run.run_id,
        card_id=card.card_id,
        result_id=result.result_id,
        decision=decision,
        reason=reason,
        accepted_facts_delta=accepted_facts,
        reviewer_provider=reviewer_provider,
        reviewer_model=reviewer_model,
        followup_actions=followup_actions,
    )


def _result_from_state_ref(services: Any, run_id: str, state: TaskCardState) -> CardResult | None:
    return taskbook_runtime_results_helper_runtime.item_from_state_ref(
        str(state.latest_result_ref or ""),
        services.storage.list_card_results(run_id, state.card_id),
        id_attr="result_id",
    )


def _acceptance_from_state_ref(
    services: Any, run_id: str, state: TaskCardState
) -> CardAcceptance | None:
    return taskbook_runtime_results_helper_runtime.item_from_state_ref(
        str(state.latest_acceptance_ref or ""),
        services.storage.list_card_acceptance(run_id, state.card_id),
        id_attr="acceptance_id",
    )


def ingest_progress_results(
    runtime: Any,
    *,
    services: Any,
    run: ComplexTaskRun,
    card_specs: dict[str, TaskCard],
    card_states: dict[str, TaskCardState],
    delegated_index: dict[str, dict[str, Any]],
    background_adapter: Any | None,
) -> tuple[ComplexTaskRun, dict[str, TaskCardState], list[str]]:
    delegated_terminal_result_status_fn = __import__(
        "cli.agent_cli.orchestration.taskbook_runtime_support_runtime",
        fromlist=[""],
    ).delegated_terminal_result_status
    return taskbook_runtime_results_progress_runtime.ingest_progress_results_runtime(
        runtime=runtime,
        services=services,
        run=run,
        card_specs=card_specs,
        card_states=card_states,
        delegated_index=delegated_index,
        background_adapter=background_adapter,
        sync_card_terminal_result_fn=sync_card_terminal_result,
        ingest_card_result_fn=ingest_card_result,
        append_event_fn=append_event,
        delegated_terminal_result_status_fn=delegated_terminal_result_status_fn,
    )


def apply_progress_acceptance(
    runtime: Any,
    *,
    services: Any,
    run: ComplexTaskRun,
    card_specs: dict[str, TaskCard],
    card_states: dict[str, TaskCardState],
) -> tuple[
    ComplexTaskRun, dict[str, TaskCardState], list[str], list[str], list[str], dict[str, Any]
]:
    planner_provider, planner_model, _ = planner_identity(runtime)
    return taskbook_runtime_results_progress_runtime.apply_progress_acceptance_runtime(
        runtime=runtime,
        services=services,
        run=run,
        card_specs=card_specs,
        card_states=card_states,
        planner_provider=planner_provider,
        planner_model=planner_model,
        result_from_state_ref_fn=_result_from_state_ref,
        acceptance_from_state_ref_fn=_acceptance_from_state_ref,
        auto_acceptance_for_result_fn=auto_acceptance_for_result,
        apply_acceptance_decision_fn=apply_acceptance_decision,
        replan_followup_contract_payload_fn=_replan_followup_contract_payload,
        replan_followup_progress_summary_fn=_replan_followup_progress_summary,
        append_event_fn=append_event,
    )

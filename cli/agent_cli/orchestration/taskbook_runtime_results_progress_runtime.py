from __future__ import annotations

from typing import Any

from cli.agent_cli.orchestration.taskbook_models import (
    ComplexTaskRun,
    TaskCard,
    TaskCardState,
)
from cli.agent_cli.orchestration.taskbook_state import CardAcceptanceDecision


def ingest_progress_results_runtime(
    *,
    runtime: Any,
    services: Any,
    run: ComplexTaskRun,
    card_specs: dict[str, TaskCard],
    card_states: dict[str, TaskCardState],
    delegated_index: dict[str, dict[str, Any]],
    background_adapter: Any | None,
    sync_card_terminal_result_fn: Any,
    ingest_card_result_fn: Any,
    append_event_fn: Any,
    delegated_terminal_result_status_fn: Any,
) -> tuple[ComplexTaskRun, dict[str, TaskCardState], list[str]]:
    updated_run = ComplexTaskRun.from_dict(run.to_dict())
    updated_states = {card_id: TaskCardState.from_dict(state.to_dict()) for card_id, state in card_states.items()}
    synced_results: list[str] = []
    for card_id, card in sorted(card_specs.items()):
        state = updated_states.get(card_id)
        if not isinstance(state, TaskCardState):
            continue
        result = sync_card_terminal_result_fn(
            runtime,
            services=services,
            run=updated_run,
            card=card,
            state=state,
            delegated_index=delegated_index,
            background_adapter=background_adapter,
            delegated_terminal_result_status_fn=delegated_terminal_result_status_fn,
        )
        if result is None:
            continue
        synced_results.append(card_id)
        updated_states[card_id] = ingest_card_result_fn(state, result)
        services.storage.save_card_state(updated_run.run_id, updated_states[card_id])
        append_event_fn(
            services,
            updated_run,
            event_type="card_result_ingested",
            actor_type="runtime",
            from_status=run.status.value,
            to_status=updated_run.status.value,
            payload={
                "card_id": card_id,
                "result_id": result.result_id,
                "result_status": result.status.value,
            },
        )
    return updated_run, updated_states, synced_results


def apply_progress_acceptance_runtime(
    *,
    runtime: Any,
    services: Any,
    run: ComplexTaskRun,
    card_specs: dict[str, TaskCard],
    card_states: dict[str, TaskCardState],
    planner_provider: str,
    planner_model: str,
    result_from_state_ref_fn: Any,
    acceptance_from_state_ref_fn: Any,
    auto_acceptance_for_result_fn: Any,
    apply_acceptance_decision_fn: Any,
    replan_followup_contract_payload_fn: Any,
    replan_followup_progress_summary_fn: Any,
    append_event_fn: Any,
) -> tuple[ComplexTaskRun, dict[str, TaskCardState], list[str], list[str], list[str], dict[str, Any]]:
    updated_run = ComplexTaskRun.from_dict(run.to_dict())
    updated_states = {card_id: TaskCardState.from_dict(state.to_dict()) for card_id, state in card_states.items()}
    accepted_cards: list[str] = []
    blocked_cards: list[str] = []
    unlocked_cards: list[str] = []
    replan_candidates: list[dict[str, Any]] = []
    replan_pending: list[dict[str, Any]] = []
    operator_actions: list[dict[str, Any]] = []
    pending_card_ids: list[str] = []
    operator_action_ids: list[str] = []
    for card_id, card in sorted(card_specs.items()):
        state = updated_states.get(card_id)
        if not isinstance(state, TaskCardState):
            continue
        latest_result = result_from_state_ref_fn(services, updated_run.run_id, state) or services.storage.latest_card_result(
            updated_run.run_id,
            card_id,
        )
        latest_acceptance = acceptance_from_state_ref_fn(
            services,
            updated_run.run_id,
            state,
        ) or services.storage.latest_card_acceptance(updated_run.run_id, card_id)
        if latest_result is None:
            continue
        acceptance = auto_acceptance_for_result_fn(
            updated_run,
            card=card,
            state=state,
            result=latest_result,
            reviewer_provider=planner_provider,
            reviewer_model=planner_model,
            latest_acceptance=latest_acceptance,
        )
        if acceptance is None:
            continue
        services.storage.append_card_acceptance(acceptance)
        outcome = apply_acceptance_decision_fn(
            updated_run,
            cards=card_specs,
            card_states=updated_states,
            acceptance=acceptance,
        )
        updated_run = outcome.run
        updated_states = outcome.card_states
        if acceptance.decision is CardAcceptanceDecision.ACCEPT:
            accepted_cards.append(card_id)
            unlocked_cards.extend(outcome.unlocked_card_ids)
        elif acceptance.decision is CardAcceptanceDecision.BLOCK:
            blocked_cards.append(card_id)
        followup_actions = [dict(item) for item in list(acceptance.followup_actions or []) if isinstance(item, dict)]
        for followup in followup_actions:
            if str(followup.get("action") or "").strip() != "replan_candidate":
                continue
            candidate, pending, action_id, operator_action = replan_followup_contract_payload_fn(followup)
            replan_candidates.append(candidate)
            replan_pending.append(pending)
            pending_card_id = str(candidate.get("card_id") or "").strip()
            if pending_card_id and pending_card_id not in pending_card_ids:
                pending_card_ids.append(pending_card_id)
            operator_actions.append(operator_action)
            if action_id and action_id not in operator_action_ids:
                operator_action_ids.append(action_id)
        append_event_fn(
            services,
            updated_run,
            event_type="card_acceptance_applied",
            actor_type="runtime",
            from_status=run.status.value,
            to_status=updated_run.status.value,
            payload={
                "card_id": card_id,
                "result_id": latest_result.result_id,
                "acceptance_id": acceptance.acceptance_id,
                "decision": acceptance.decision.value,
                "unlocked_card_ids": list(outcome.unlocked_card_ids),
                "followup_actions": followup_actions,
            },
        )
    return (
        updated_run,
        updated_states,
        accepted_cards,
        blocked_cards,
        unlocked_cards,
        {
            "replan_contract_version": 1,
            "replan_candidates": replan_candidates,
            "replan_pending": replan_pending,
            "replan_pending_card_ids": pending_card_ids,
            "replan_operator_action_ids": operator_action_ids,
            "operator_actions": operator_actions,
            "replan_followup_summary": replan_followup_progress_summary_fn(
                contract_version=1,
                candidates=replan_candidates,
                pending=replan_pending,
                pending_card_ids=pending_card_ids,
                operator_actions=operator_actions,
            ),
        },
    )

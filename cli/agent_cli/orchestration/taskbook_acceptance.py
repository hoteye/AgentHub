from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from cli.agent_cli.orchestration.taskbook_models import (
    CardAcceptance,
    CardResult,
    ComplexTaskRun,
    TaskCard,
    TaskCardState,
    utc_now_iso,
)
from cli.agent_cli.orchestration.taskbook_state import (
    CardAcceptanceDecision,
    TaskCardStatus,
    TaskDependencyStatus,
)


@dataclass(slots=True)
class AcceptanceOutcome:
    run: ComplexTaskRun
    card_states: Dict[str, TaskCardState]
    unlocked_card_ids: list[str]


def ingest_card_result(state: TaskCardState, result: CardResult) -> TaskCardState:
    updated_state = TaskCardState.from_dict(state.to_dict())
    updated_state.latest_result_ref = result.result_id
    updated_state.status = TaskCardStatus.REVIEW
    updated_state.updated_at = str(result.reported_at or utc_now_iso())
    updated_state.finished_at = str(result.reported_at or utc_now_iso())
    return updated_state


def apply_acceptance_decision(
    run: ComplexTaskRun,
    *,
    cards: Dict[str, TaskCard],
    card_states: Dict[str, TaskCardState],
    acceptance: CardAcceptance,
) -> AcceptanceOutcome:
    updated_run = ComplexTaskRun.from_dict(run.to_dict())
    updated_states = {card_id: TaskCardState.from_dict(state.to_dict()) for card_id, state in card_states.items()}
    target_state = updated_states[acceptance.card_id]
    target_state.latest_acceptance_ref = acceptance.acceptance_id
    target_state.updated_at = str(acceptance.reviewed_at or utc_now_iso())
    acceptance_reason = _normalized_acceptance_reason(acceptance)
    unlocked: list[str] = []

    if acceptance.decision is CardAcceptanceDecision.ACCEPT:
        target_state.status = TaskCardStatus.ACCEPTED
        target_state.last_error = ""
        target_state.last_scheduler_decision = "accepted_by_reviewer"
        for fact in acceptance.accepted_facts_delta:
            if fact not in updated_run.accepted_facts:
                updated_run.accepted_facts.append(fact)
        for card_id, card in cards.items():
            if acceptance.card_id not in card.depends_on:
                continue
            candidate_state = updated_states.get(card_id)
            if candidate_state is None:
                continue
            if _dependencies_satisfied(card, updated_states):
                candidate_state.dependency_status = TaskDependencyStatus.SATISFIED
                if candidate_state.status in {TaskCardStatus.DRAFT, TaskCardStatus.REWORK, TaskCardStatus.BLOCKED}:
                    candidate_state.status = TaskCardStatus.READY
                candidate_state.last_scheduler_decision = "dependencies_satisfied_after_acceptance"
                unlocked.append(card_id)
    elif acceptance.decision is CardAcceptanceDecision.REWORK:
        target_state.status = TaskCardStatus.READY
        target_state.attempt += 1
        target_state.last_error = f"rework_required:{acceptance_reason}"
        target_state.last_scheduler_decision = "rework_requested_by_acceptance"
    elif acceptance.decision is CardAcceptanceDecision.BLOCK:
        target_state.status = TaskCardStatus.BLOCKED
        target_state.last_error = f"blocked:{acceptance_reason}"
        target_state.last_scheduler_decision = (
            "blocked_by_rework_escalation"
            if _is_rework_escalation_reason(acceptance_reason)
            else "blocked_by_acceptance_review"
        )
    else:
        target_state.status = TaskCardStatus.READY
        target_state.attempt += 1
        target_state.last_error = f"rejected:{acceptance_reason}"
        target_state.last_scheduler_decision = "rejected_requires_new_attempt"

    _recompute_run_views(updated_run, updated_states)
    return AcceptanceOutcome(
        run=updated_run,
        card_states=updated_states,
        unlocked_card_ids=sorted(set(unlocked)),
    )


def _normalized_acceptance_reason(acceptance: CardAcceptance) -> str:
    reason = str(acceptance.reason or "").strip()
    if reason:
        return reason
    if acceptance.decision is CardAcceptanceDecision.REWORK:
        return "reviewer_requested_rework"
    if acceptance.decision is CardAcceptanceDecision.BLOCK:
        return "reviewer_blocked_progress"
    if acceptance.decision is CardAcceptanceDecision.REJECT:
        return "reviewer_rejected_result"
    return "reviewer_accepted_result"


def _is_rework_escalation_reason(reason: str) -> bool:
    return str(reason or "").strip().endswith("_escalated_after_retries")


def _dependencies_satisfied(card: TaskCard, card_states: Dict[str, TaskCardState]) -> bool:
    for dependency_id in card.depends_on:
        dependency_state = card_states.get(dependency_id)
        if dependency_state is None or dependency_state.status is not TaskCardStatus.ACCEPTED:
            return False
    return True


def _recompute_run_views(run: ComplexTaskRun, card_states: Dict[str, TaskCardState]) -> None:
    ready: list[str] = []
    running: list[str] = []
    blocked: list[str] = []
    completed: list[str] = []
    for card_id, state in sorted(card_states.items()):
        if state.status is TaskCardStatus.ACCEPTED:
            completed.append(card_id)
        elif state.status in {TaskCardStatus.RUNNING, TaskCardStatus.QUEUED, TaskCardStatus.REVIEW}:
            running.append(card_id)
        elif state.status in {TaskCardStatus.BLOCKED, TaskCardStatus.REWORK}:
            blocked.append(card_id)
        elif state.status in {TaskCardStatus.READY, TaskCardStatus.DRAFT}:
            if state.dependency_status is TaskDependencyStatus.SATISFIED:
                ready.append(card_id)
            else:
                blocked.append(card_id)
    run.ready_card_ids = ready
    run.running_card_ids = running
    run.blocked_card_ids = blocked
    run.completed_card_ids = completed

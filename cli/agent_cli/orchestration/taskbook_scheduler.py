from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Tuple

from cli.agent_cli.orchestration.taskbook_models import ComplexTaskRun, TaskCard, TaskCardState
from cli.agent_cli.orchestration.taskbook_state import (
    TaskCardKind,
    TaskCardStatus,
    TaskDependencyStatus,
)


@dataclass(slots=True)
class SchedulerSelection:
    run: ComplexTaskRun
    card_states: Dict[str, TaskCardState]
    selected_card_ids: list[str]
    blocked_card_ids: list[str]
    skipped_card_ids: list[str]


def _clone_run(run: ComplexTaskRun) -> ComplexTaskRun:
    return ComplexTaskRun.from_dict(run.to_dict())


def _clone_state(state: TaskCardState) -> TaskCardState:
    return TaskCardState.from_dict(state.to_dict())


def _dependencies_satisfied(card: TaskCard, card_states: Dict[str, TaskCardState]) -> bool:
    for dependency_id in card.depends_on:
        dependency_state = card_states.get(dependency_id)
        if dependency_state is None or dependency_state.status is not TaskCardStatus.ACCEPTED:
            return False
    return True


def _budget_bucket(card: TaskCard) -> str:
    if card.kind is TaskCardKind.CONTEXT_SENSITIVE:
        return "context_sensitive"
    if card.kind is TaskCardKind.WORKSPACE_MUTATING:
        return "workspace_write"
    if card.kind is TaskCardKind.LONG_RUNNING and card.owned_files:
        return "workspace_write"
    return "read_only"


def _normalized_owned_files(card: TaskCard) -> set[str]:
    return {str(path).strip() for path in card.owned_files if str(path).strip()}


def _conflicts_with_running_write(
    card: TaskCard,
    *,
    running_write_cards: Iterable[TaskCard],
    selected_write_cards: Iterable[TaskCard],
) -> bool:
    candidate_files = _normalized_owned_files(card)
    if not candidate_files:
        return False
    for other in list(running_write_cards) + list(selected_write_cards):
        if candidate_files.intersection(_normalized_owned_files(other)):
            return True
    return False


def select_ready_cards(
    run: ComplexTaskRun,
    *,
    card_specs: Dict[str, TaskCard],
    card_states: Dict[str, TaskCardState],
    max_parallel_read_only: int = 3,
    max_parallel_workspace_write: int = 1,
) -> SchedulerSelection:
    updated_run = _clone_run(run)
    updated_states = {card_id: _clone_state(state) for card_id, state in card_states.items()}
    selected: list[str] = []
    blocked: list[str] = []
    skipped: list[str] = []

    running_read_only = 0
    running_write_cards: list[TaskCard] = []
    for card_id, state in updated_states.items():
        if state.status not in {TaskCardStatus.QUEUED, TaskCardStatus.RUNNING}:
            continue
        card = card_specs.get(card_id)
        if card is None:
            continue
        bucket = _budget_bucket(card)
        if bucket == "read_only":
            running_read_only += 1
        elif bucket == "workspace_write":
            running_write_cards.append(card)

    selected_read_only = 0
    selected_write_cards: list[TaskCard] = []

    for card_id in sorted(card_specs):
        card = card_specs[card_id]
        state = updated_states.setdefault(card_id, TaskCardState(card_id=card_id))

        if state.status in {
            TaskCardStatus.ACCEPTED,
            TaskCardStatus.CANCELLED,
            TaskCardStatus.FAILED,
            TaskCardStatus.RUNNING,
            TaskCardStatus.QUEUED,
            TaskCardStatus.REVIEW,
            TaskCardStatus.BLOCKED,
        }:
            continue

        if not _dependencies_satisfied(card, updated_states):
            state.dependency_status = TaskDependencyStatus.PENDING
            state.last_scheduler_decision = "dependency_not_satisfied"
            blocked.append(card_id)
            continue

        state.dependency_status = TaskDependencyStatus.SATISFIED
        bucket = _budget_bucket(card)
        if bucket == "context_sensitive":
            state.last_scheduler_decision = "context_sensitive_stays_local"
            skipped.append(card_id)
            continue

        if bucket == "workspace_write":
            if len(running_write_cards) + len(selected_write_cards) >= max_parallel_workspace_write:
                state.status = TaskCardStatus.READY
                state.last_scheduler_decision = "workspace_write_budget_exhausted"
                skipped.append(card_id)
                continue
            if _conflicts_with_running_write(
                card,
                running_write_cards=running_write_cards,
                selected_write_cards=selected_write_cards,
            ):
                state.status = TaskCardStatus.READY
                state.last_scheduler_decision = "owned_files_conflict"
                blocked.append(card_id)
                continue
            selected_write_cards.append(card)
        else:
            if running_read_only + selected_read_only >= max_parallel_read_only:
                state.status = TaskCardStatus.READY
                state.last_scheduler_decision = "read_only_budget_exhausted"
                skipped.append(card_id)
                continue
            selected_read_only += 1

        state.status = TaskCardStatus.QUEUED
        state.last_scheduler_decision = "selected_as_ready_card"
        selected.append(card_id)

    ready_card_ids: list[str] = []
    running_card_ids: list[str] = []
    blocked_card_ids: list[str] = []
    completed_card_ids: list[str] = []
    for card_id, state in sorted(updated_states.items()):
        if state.status is TaskCardStatus.ACCEPTED:
            completed_card_ids.append(card_id)
        elif state.status in {TaskCardStatus.RUNNING, TaskCardStatus.QUEUED}:
            running_card_ids.append(card_id)
        elif state.status in {TaskCardStatus.BLOCKED, TaskCardStatus.REWORK}:
            blocked_card_ids.append(card_id)
        elif state.status in {TaskCardStatus.READY, TaskCardStatus.DRAFT}:
            if state.dependency_status is TaskDependencyStatus.SATISFIED:
                ready_card_ids.append(card_id)
            else:
                blocked_card_ids.append(card_id)

    for card_id in blocked:
        if card_id not in blocked_card_ids:
            blocked_card_ids.append(card_id)

    updated_run.ready_card_ids = sorted(ready_card_ids)
    updated_run.running_card_ids = sorted(running_card_ids)
    updated_run.blocked_card_ids = sorted(set(blocked_card_ids))
    updated_run.completed_card_ids = sorted(completed_card_ids)
    return SchedulerSelection(
        run=updated_run,
        card_states=updated_states,
        selected_card_ids=selected,
        blocked_card_ids=sorted(set(blocked)),
        skipped_card_ids=sorted(set(skipped)),
    )


def summarize_dependency_graph(cards: Dict[str, TaskCard]) -> Dict[str, Tuple[str, ...]]:
    return {card_id: tuple(card.depends_on) for card_id, card in sorted(cards.items())}

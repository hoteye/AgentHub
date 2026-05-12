from __future__ import annotations

from cli.agent_cli.orchestration.taskbook_models import ComplexTaskRun, TaskCard, TaskCardState
from cli.agent_cli.orchestration.taskbook_scheduler import select_ready_cards
from cli.agent_cli.orchestration.taskbook_state import (
    ComplexTaskRunStatus,
    TaskCardKind,
    TaskCardStatus,
)


def _card(card_id: str, *, kind: TaskCardKind = TaskCardKind.READ_ONLY, depends_on: list[str] | None = None, owned_files: list[str] | None = None) -> TaskCard:
    return TaskCard(
        card_id=card_id,
        taskbook_version=1,
        title=card_id,
        goal=f"goal:{card_id}",
        kind=kind,
        depends_on=list(depends_on or []),
        owned_files=list(owned_files or []),
        acceptance_criteria=["done"],
    )


def test_scheduler_selects_dependency_free_card() -> None:
    run = ComplexTaskRun(run_id="ctrun_sched_1", status=ComplexTaskRunStatus.READY)
    cards = {"CARD-001": _card("CARD-001")}
    states = {"CARD-001": TaskCardState(card_id="CARD-001", status=TaskCardStatus.DRAFT)}

    selection = select_ready_cards(run, card_specs=cards, card_states=states)

    assert selection.selected_card_ids == ["CARD-001"]
    assert selection.card_states["CARD-001"].status is TaskCardStatus.QUEUED
    assert selection.run.running_card_ids == ["CARD-001"]


def test_scheduler_keeps_dependency_blocked_until_parent_accepted() -> None:
    run = ComplexTaskRun(run_id="ctrun_sched_2", status=ComplexTaskRunStatus.READY)
    cards = {
        "CARD-001": _card("CARD-001"),
        "CARD-002": _card("CARD-002", depends_on=["CARD-001"]),
    }
    states = {
        "CARD-001": TaskCardState(card_id="CARD-001", status=TaskCardStatus.READY),
        "CARD-002": TaskCardState(card_id="CARD-002", status=TaskCardStatus.DRAFT),
    }

    selection = select_ready_cards(run, card_specs=cards, card_states=states)

    assert selection.selected_card_ids == ["CARD-001"]
    assert selection.card_states["CARD-002"].last_scheduler_decision == "dependency_not_satisfied"
    assert "CARD-002" in selection.run.blocked_card_ids


def test_scheduler_blocks_conflicting_workspace_write_cards() -> None:
    run = ComplexTaskRun(run_id="ctrun_sched_3", status=ComplexTaskRunStatus.READY)
    cards = {
        "CARD-001": _card(
            "CARD-001",
            kind=TaskCardKind.WORKSPACE_MUTATING,
            owned_files=["cli/agent_cli/runtime.py"],
        ),
        "CARD-002": _card(
            "CARD-002",
            kind=TaskCardKind.WORKSPACE_MUTATING,
            owned_files=["cli/agent_cli/runtime.py"],
        ),
    }
    states = {
        "CARD-001": TaskCardState(card_id="CARD-001", status=TaskCardStatus.READY),
        "CARD-002": TaskCardState(card_id="CARD-002", status=TaskCardStatus.READY),
    }

    selection = select_ready_cards(
        run,
        card_specs=cards,
        card_states=states,
        max_parallel_workspace_write=2,
    )

    assert selection.selected_card_ids == ["CARD-001"]
    assert selection.card_states["CARD-002"].last_scheduler_decision == "owned_files_conflict"


def test_scheduler_respects_read_only_parallel_budget() -> None:
    run = ComplexTaskRun(run_id="ctrun_sched_4", status=ComplexTaskRunStatus.READY)
    cards = {
        "CARD-001": _card("CARD-001"),
        "CARD-002": _card("CARD-002"),
        "CARD-003": _card("CARD-003"),
    }
    states = {
        "CARD-001": TaskCardState(card_id="CARD-001", status=TaskCardStatus.READY),
        "CARD-002": TaskCardState(card_id="CARD-002", status=TaskCardStatus.READY),
        "CARD-003": TaskCardState(card_id="CARD-003", status=TaskCardStatus.READY),
    }

    selection = select_ready_cards(
        run,
        card_specs=cards,
        card_states=states,
        max_parallel_read_only=2,
    )

    assert selection.selected_card_ids == ["CARD-001", "CARD-002"]
    assert selection.card_states["CARD-003"].last_scheduler_decision == "read_only_budget_exhausted"
    assert selection.run.running_card_ids == ["CARD-001", "CARD-002"]

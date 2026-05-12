from __future__ import annotations

import pytest

from cli.agent_cli.orchestration.taskbook_models import (
    CardAcceptance,
    CardResult,
    ComplexTaskRun,
    ExecutionRef,
    OrchestrationEvent,
    TaskCard,
    TaskCardState,
    TaskbookSnapshot,
)
from cli.agent_cli.orchestration.taskbook_state import (
    CardAcceptanceDecision,
    CardResultStatus,
    ComplexTaskMode,
    ComplexTaskRunStatus,
    ExecutionRefKind,
    TaskCardDependencyStatus,
    TaskCardKind,
    TaskCardStatus,
)


def test_complex_task_run_round_trip_preserves_lists_and_mode() -> None:
    run = ComplexTaskRun(
        run_id="ctrun_1",
        thread_id="thread_1",
        objective="Implement orchestration",
        mode=ComplexTaskMode.ORCHESTRATED,
        status=ComplexTaskRunStatus.RUNNING,
        accepted_facts=["schema frozen"],
        ready_card_ids=["CARD-002"],
        running_card_ids=["CARD-001"],
        blocked_card_ids=["CARD-004"],
        completed_card_ids=["CARD-000"],
        latest_event_seq=12,
    )

    restored = ComplexTaskRun.from_dict(run.to_dict())

    assert restored.to_dict() == run.to_dict()


def test_task_card_state_round_trip_preserves_execution_refs() -> None:
    state = TaskCardState(
        card_id="CARD-002",
        status=TaskCardStatus.RUNNING,
        attempt=1,
        execution_refs=[
            ExecutionRef(
                kind=ExecutionRefKind.BACKGROUND_TASK,
                task_id="bg_123",
                dispatch_id=1,
                provider_name="openai",
                model="gpt-5.4",
                route_label="executor",
            )
        ],
        dependency_status=TaskCardDependencyStatus.SATISFIED,
        owned_file_lock=True,
        last_scheduler_decision="selected",
    )

    restored = TaskCardState.from_dict(state.to_dict())

    assert restored.to_dict() == state.to_dict()


def test_invalid_status_values_raise_value_error() -> None:
    with pytest.raises(ValueError, match="task_card_state.status"):
        TaskCardState.from_dict({"card_id": "CARD-001", "status": "not_real"})

    with pytest.raises(ValueError, match="execution_ref.kind"):
        ExecutionRef.from_dict({"kind": "not_real"})


def test_other_models_round_trip_with_nested_and_list_fields() -> None:
    taskbook = TaskbookSnapshot(
        taskbook_id="tb_1",
        run_id="ctrun_1",
        version=2,
        derived_from_version=1,
        success_definition=["ship it"],
        critical_path=["CARD-001"],
        cards=["CARD-001", "CARD-002"],
    )
    card = TaskCard(
        card_id="CARD-001",
        taskbook_version=2,
        title="Freeze schema",
        goal="Define runtime models",
        kind=TaskCardKind.WORKSPACE_MUTATING,
        owned_files=["cli/agent_cli/orchestration/taskbook_models.py"],
        depends_on=["CARD-000"],
        acceptance_criteria=["round-trip works"],
        test_requirements=["pytest -q cli/tests/test_taskbook_models.py"],
    )
    result = CardResult(
        result_id="result_1",
        run_id="ctrun_1",
        card_id="CARD-001",
        attempt=1,
        status=CardResultStatus.COMPLETED,
        summary="done",
        modified_files=["cli/agent_cli/orchestration/taskbook_models.py"],
        commands=["pytest -q cli/tests/test_taskbook_models.py"],
        execution_ref=ExecutionRef(kind=ExecutionRefKind.LOCAL),
    )
    acceptance = CardAcceptance(
        acceptance_id="accept_1",
        run_id="ctrun_1",
        card_id="CARD-001",
        result_id="result_1",
        decision=CardAcceptanceDecision.ACCEPT,
        accepted_facts_delta=["schema frozen"],
        followup_actions=[{"action": "unlock", "card_id": "CARD-002"}],
    )
    event = OrchestrationEvent(
        seq=7,
        run_id="ctrun_1",
        card_id="CARD-001",
        event_type="card_accepted",
        actor_type="orchestrator",
        payload={"acceptance_id": "accept_1"},
    )

    assert TaskbookSnapshot.from_dict(taskbook.to_dict()).to_dict() == taskbook.to_dict()
    assert TaskCard.from_dict(card.to_dict()).to_dict() == card.to_dict()
    assert CardResult.from_dict(result.to_dict()).to_dict() == result.to_dict()
    assert CardAcceptance.from_dict(acceptance.to_dict()).to_dict() == acceptance.to_dict()
    assert OrchestrationEvent.from_dict(event.to_dict()).to_dict() == event.to_dict()

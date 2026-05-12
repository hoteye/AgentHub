from __future__ import annotations

from pathlib import Path

from cli.agent_cli.orchestration.taskbook_models import (
    CardAcceptance,
    CardResult,
    ComplexTaskRun,
    OrchestrationEvent,
    TaskCard,
    TaskCardState,
    TaskbookSnapshot,
)
from cli.agent_cli.orchestration.taskbook_state import (
    CardAcceptanceDecision,
    CardResultStatus,
    ComplexTaskRunStatus,
    TaskCardDependencyStatus,
    TaskCardKind,
    TaskCardStatus,
)
from cli.agent_cli.orchestration.taskbook_storage import TaskbookStorage


def _sample_run() -> ComplexTaskRun:
    return ComplexTaskRun(
        run_id="ctrun_storage_1",
        thread_id="thread_storage_1",
        objective="Test storage",
        status=ComplexTaskRunStatus.RUNNING,
        taskbook_version_current=2,
        ready_card_ids=["CARD-002"],
        running_card_ids=["CARD-001"],
    )


def _sample_taskbook(version: int) -> TaskbookSnapshot:
    return TaskbookSnapshot(
        taskbook_id="tb_storage_1",
        run_id="ctrun_storage_1",
        version=version,
        derived_from_version=max(0, version - 1),
        goal=f"Goal v{version}",
        cards=["CARD-001", "CARD-002"],
    )


def test_storage_writes_and_reads_standard_layout(tmp_path: Path) -> None:
    storage = TaskbookStorage(tmp_path / "orchestration")

    run = _sample_run()
    taskbook = _sample_taskbook(1)
    card = TaskCard(
        card_id="CARD-001",
        taskbook_version=1,
        title="Schema",
        goal="Freeze models",
        kind=TaskCardKind.WORKSPACE_MUTATING,
        owned_files=["cli/agent_cli/orchestration/taskbook_models.py"],
        acceptance_criteria=["round-trip works"],
    )
    state = TaskCardState(
        card_id="CARD-001",
        status=TaskCardStatus.RUNNING,
        attempt=1,
        dependency_status=TaskCardDependencyStatus.SATISFIED,
    )
    result = CardResult(
        result_id="result_0001",
        run_id=run.run_id,
        card_id=card.card_id,
        attempt=1,
        status=CardResultStatus.COMPLETED,
        summary="done",
    )
    acceptance = CardAcceptance(
        acceptance_id="decision_0001",
        run_id=run.run_id,
        card_id=card.card_id,
        result_id=result.result_id,
        decision=CardAcceptanceDecision.ACCEPT,
        reason="looks good",
    )
    event = OrchestrationEvent(
        seq=1,
        run_id=run.run_id,
        card_id=card.card_id,
        event_type="card_completed",
        actor_type="background_task",
    )

    storage.write_run(run)
    storage.append_taskbook(taskbook)
    storage.write_card_spec(run.run_id, card)
    storage.write_card_state(run.run_id, state)
    storage.append_card_result(result)
    storage.append_card_acceptance(acceptance)
    storage.append_event(event)

    assert storage.run_file_path(run.run_id).exists()
    assert storage.taskbook_file_path(run.run_id, taskbook.version).exists()
    assert storage.card_spec_path(run.run_id, card.card_id).exists()
    assert storage.card_state_path(run.run_id, card.card_id).exists()
    assert storage.card_result_path(run.run_id, card.card_id, result.result_id).exists()
    assert storage.card_acceptance_path(run.run_id, card.card_id, acceptance.acceptance_id).exists()
    assert storage.event_file_path(run.run_id, event.seq, event.event_type).exists()

    assert storage.read_run(run.run_id).to_dict() == run.to_dict()
    assert storage.read_taskbook(run.run_id, 1).to_dict() == taskbook.to_dict()
    assert storage.read_card_spec(run.run_id, card.card_id).to_dict() == card.to_dict()
    assert storage.read_card_state(run.run_id, card.card_id).to_dict() == state.to_dict()
    assert storage.latest_card_result(run.run_id, card.card_id).to_dict() == result.to_dict()
    assert storage.latest_card_acceptance(run.run_id, card.card_id).to_dict() == acceptance.to_dict()
    assert [item.to_dict() for item in storage.list_events(run.run_id)] == [event.to_dict()]


def test_storage_preserves_append_only_taskbook_versions_and_bundle_recovery(tmp_path: Path) -> None:
    storage = TaskbookStorage(tmp_path / "orchestration")
    run = _sample_run()
    taskbook_v1 = _sample_taskbook(1)
    taskbook_v2 = _sample_taskbook(2)
    state = TaskCardState(card_id="CARD-002", status=TaskCardStatus.READY)

    storage.write_run(run)
    storage.append_taskbook(taskbook_v1)
    storage.append_taskbook(taskbook_v2)
    storage.write_card_state(run.run_id, state)

    taskbooks = storage.list_taskbooks(run.run_id)
    bundle = storage.load_run_bundle(run.run_id)

    assert [item.version for item in taskbooks] == [1, 2]
    assert storage.latest_taskbook(run.run_id).version == 2
    assert storage.list_run_ids() == [run.run_id]
    assert bundle["run"].run_id == run.run_id
    assert bundle["card_states"]["CARD-002"].status == TaskCardStatus.READY

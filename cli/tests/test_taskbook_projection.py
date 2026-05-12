from __future__ import annotations

from pathlib import Path

from cli.agent_cli.orchestration.taskbook_models import (
    CardAcceptance,
    CardResult,
    ComplexTaskRun,
    TaskCard,
    TaskCardState,
    TaskbookSnapshot,
)
from cli.agent_cli.orchestration.taskbook_projection import (
    build_workflows_view,
    render_card_projection,
    render_taskbook_projection,
    write_projections,
)
from cli.agent_cli.orchestration.taskbook_state import (
    CardAcceptanceDecision,
    CardResultStatus,
    ComplexTaskRunStatus,
    TaskCardKind,
    TaskCardStatus,
)
from cli.agent_cli.orchestration.taskbook_storage import TaskbookStorage


def _seed_storage(tmp_path: Path) -> TaskbookStorage:
    storage = TaskbookStorage(base_dir=tmp_path / "orchestration")
    run = ComplexTaskRun(
        run_id="ctrun_projection_1",
        objective="projection demo",
        status=ComplexTaskRunStatus.RUNNING,
        taskbook_version_current=1,
        accepted_facts=["schema_ready"],
    )
    taskbook = TaskbookSnapshot(
        taskbook_id="tb_projection_1",
        run_id=run.run_id,
        version=1,
        goal="projection demo",
        cards=["CARD-001"],
    )
    card = TaskCard(
        card_id="CARD-001",
        taskbook_version=1,
        title="Freeze schema",
        goal="Define schema",
        kind=TaskCardKind.WORKSPACE_MUTATING,
        owned_files=["cli/agent_cli/orchestration/taskbook_models.py"],
        acceptance_criteria=["tests pass"],
    )
    state = TaskCardState(card_id="CARD-001", status=TaskCardStatus.REVIEW, last_scheduler_decision="selected")
    result = CardResult(
        result_id="result_001",
        run_id=run.run_id,
        card_id=card.card_id,
        attempt=1,
        status=CardResultStatus.COMPLETED,
        summary="schema done",
        modified_files=["cli/agent_cli/orchestration/taskbook_models.py"],
        test_commands=["pytest -q cli/tests/test_taskbook_projection.py"],
    )
    acceptance = CardAcceptance(
        acceptance_id="accept_001",
        run_id=run.run_id,
        card_id=card.card_id,
        result_id=result.result_id,
        decision=CardAcceptanceDecision.ACCEPT,
        reason="good",
        reviewer_provider="openai",
        reviewer_model="gpt-5.4",
    )
    storage.write_run(run)
    storage.append_taskbook(taskbook)
    storage.write_card_spec(run.run_id, card)
    storage.write_card_state(run.run_id, state)
    storage.append_card_result(result)
    storage.append_card_acceptance(acceptance)
    return storage


def test_render_projection_text_and_workflows_view(tmp_path: Path) -> None:
    storage = _seed_storage(tmp_path)
    bundle = storage.load_run_bundle("ctrun_projection_1")
    assert bundle is not None

    taskbook_text = render_taskbook_projection(bundle)
    card_text = render_card_projection(
        bundle["card_specs"]["CARD-001"],
        state=bundle["card_states"]["CARD-001"],
        latest_result=bundle["card_results"]["CARD-001"][-1],
        latest_acceptance=bundle["card_acceptance"]["CARD-001"][-1],
    )
    view = build_workflows_view(bundle)

    assert "# projection demo" in taskbook_text
    assert "- cards_total: 1" in taskbook_text
    assert "- cards_ready: 0" in taskbook_text
    assert "- cards_running: 0" in taskbook_text
    assert "- cards_blocked: 0" in taskbook_text
    assert "- cards_completed: 0" in taskbook_text
    assert "- accepted_facts: schema_ready" in taskbook_text
    assert "- latest_result: CARD-001:result_001 | completed | schema done" in taskbook_text
    assert "- latest_acceptance: CARD-001:accept_001 | accept | good" in taskbook_text
    assert "### CARD-001: Freeze schema" in taskbook_text
    assert "- latest_result: result_001 | completed | schema done" in taskbook_text
    assert "- latest_acceptance: accept_001 | accept | good" in taskbook_text
    assert "latest_result: result_001 | completed | schema done" in card_text
    assert "latest_result_modified_files: cli/agent_cli/orchestration/taskbook_models.py" in card_text
    assert "latest_result_test_commands: pytest -q cli/tests/test_taskbook_projection.py" in card_text
    assert "latest_result_blockers: -" in card_text
    assert "latest_acceptance_reviewer: openai | gpt-5.4" in card_text
    assert view["run_id"] == "ctrun_projection_1"
    assert view["cards"][0]["card_id"] == "CARD-001"
    assert view["cards"][0]["latest_acceptance"]["decision"] == "accept"


def test_write_projections_generates_markdown_files(tmp_path: Path) -> None:
    storage = _seed_storage(tmp_path)

    paths = write_projections(storage, "ctrun_projection_1")

    assert paths["taskbook"].exists()
    assert paths["card:CARD-001"].exists()
    assert "Freeze schema" in paths["card:CARD-001"].read_text(encoding="utf-8")

from __future__ import annotations

from cli.agent_cli.orchestration.taskbook_models import ComplexTaskRun
from cli.agent_cli.orchestration.taskbook_runtime_support_runtime import workflow_line
from cli.agent_cli.orchestration.taskbook_state import ComplexTaskRunStatus


def test_workflow_line_includes_taskbook_and_projection_summary() -> None:
    run = ComplexTaskRun(
        run_id="run_001",
        status=ComplexTaskRunStatus.RUNNING,
        current_phase="cards_running",
        taskbook_version_current=3,
        ready_card_ids=["CARD-004"],
        running_card_ids=["CARD-001"],
        blocked_card_ids=["CARD-003"],
        completed_card_ids=["CARD-002"],
    )
    view = {
        "taskbook_version_current": 3,
        "accepted_facts": ["fact_1", "fact_2"],
        "cards": [
            {
                "card_id": "CARD-001",
                "status": "running",
                "latest_result": {"status": "completed", "reported_at": "2026-04-06T08:00:00Z"},
                "latest_acceptance": None,
            },
            {
                "card_id": "CARD-002",
                "status": "accepted",
                "latest_result": {"status": "completed", "reported_at": "2026-04-06T08:01:00Z"},
                "latest_acceptance": {"decision": "accept", "reviewed_at": "2026-04-06T08:02:00Z"},
            },
            {
                "card_id": "CARD-003",
                "status": "rework",
                "latest_result": {"status": "completed", "reported_at": "2026-04-06T08:03:00Z"},
                "latest_acceptance": {"decision": "rework", "reviewed_at": "2026-04-06T08:04:00Z"},
            },
            {
                "card_id": "CARD-004",
                "status": "failed",
                "latest_result": {"status": "failed", "reported_at": "2026-04-06T08:05:00Z"},
                "latest_acceptance": {"decision": "block", "reviewed_at": "2026-04-06T08:06:00Z"},
            },
        ],
    }

    line = workflow_line(run, view)

    assert "taskbook=v3,facts=2" in line
    assert "projection=accept=1,pending=1,rework=1,blocked=1,failed=1" in line


def test_workflow_line_omits_projection_summary_when_cards_missing() -> None:
    run = ComplexTaskRun(
        run_id="run_002",
        status=ComplexTaskRunStatus.READY,
        current_phase="taskbook_ready",
        taskbook_version_current=0,
    )
    view = {
        "cards": [],
        "accepted_facts": [],
        "taskbook_version_current": 0,
    }

    line = workflow_line(run, view)

    assert "taskbook=" not in line
    assert "projection=" not in line

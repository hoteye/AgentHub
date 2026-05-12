from __future__ import annotations

from cli.agent_cli.orchestration.taskbook_projection_runtime import normalize_join_result_state
from cli.agent_cli.runtime_core.background_task_commands_summary_runtime import workflows_text
from cli.agent_cli.ui.transcript_controller_projection_runtime import operator_workflow_detail_lines


def test_workflows_top_counters_keep_operator_visibility_regression_guard() -> None:
    text = workflows_text(
        delegated_lines=[
            "- delegated | ag_01 | completed | role=teammate | workflow=completed | completion=ready_to_adopt | result_state=pending_review",
            "- delegated | ag_02 | completed | role=subagent | workflow=completed | completion=adopted | result_state=adopted",
        ],
        orchestration_lines=[
            "- orchestration | run_ready_001 | running | workflow=running | phase=cards_dispatched | cards=3 | ready=0 | running=1 | blocked=0 | accepted=1",
            (
                "- orchestration | run_review_001 | blocked | workflow=blocked | phase=review_pending"
                " | cards=4 | ready=0 | running=0 | blocked=1 | accepted=2"
                " | taskbook=v4,facts=6"
                " | projection=accept=2,pending=1,rework=1,blocked=1,failed=0"
                " | latest_acceptance=CARD-004:block"
                " | review_reason=CARD-004:manual_review_required"
                " | current_result=CARD-004:completed:awaiting operator review"
            ),
        ],
        background_lines=[
            "- background | bg_01 | completed | review required | result_state=pending_review | review=pending",
            "- background | bg_02 | completed | adopted | result_state=adopted | notify=foreground_adopted",
        ],
        orchestration_count=2,
        mirrored_count=1,
        background_enabled=True,
    )

    assert "workflows=6" in text
    assert "delegated_workflows=2" in text
    assert "orchestration_runs=2" in text
    assert "orchestration_running=1" in text
    assert "orchestration_blocked=1" in text
    assert "orchestration_review_pending=1" in text
    assert "background_tasks=2" in text
    assert "mirrored_background_tasks=1" in text
    assert "delegated_result_returned=0" in text
    assert "delegated_result_adopted=1" in text
    assert "delegated_result_pending_review=1" in text
    assert "background_result_returned=0" in text
    assert "background_result_adopted=1" in text
    assert "background_result_pending_review=1" in text
    assert "taskbook=v4,facts=6" in text
    assert "projection=accept=2,pending=1,rework=1,blocked=1,failed=0" in text
    assert "latest_acceptance=CARD-004:block" in text
    assert "review_reason=CARD-004:manual_review_required" in text
    assert "current_result=CARD-004:completed:awaiting operator review" in text


def test_workflow_detail_projection_preserves_new_orchestration_segments() -> None:
    assistant_text = (
        "workflows=1\n"
        "delegated_workflows=0\n"
        "orchestration_runs=1\n"
        "- orchestration | run_review_001 | blocked | workflow=blocked | phase=review_pending"
        " | cards=4 | ready=0 | running=0 | blocked=1 | accepted=2"
        " | taskbook=v4,facts=6"
        " | projection=accept=2,pending=1,rework=1,blocked=1,failed=0"
        " | latest_acceptance=CARD-004:block"
        " | review_reason=CARD-004:manual_review_required"
        " | current_result=CARD-004:completed:awaiting operator review"
    )

    details = operator_workflow_detail_lines(assistant_text)

    assert len(details) == 1
    line = details[0]
    assert "orchestration run_review_001 blocked" in line
    assert "workflow blocked" in line
    assert "phase review_pending" in line
    assert "taskbook v4,facts=6" in line
    assert "projection accept=2,pending=1,rework=1,blocked=1,failed=0" in line
    assert "acceptance CARD-004:block" in line
    assert "review CARD-004:manual_review_required" in line
    assert "current result CARD-004:completed:awaiting operator review" in line


def test_join_state_normalization_prefers_blocked_over_foreground_adopted_hint() -> None:
    result_state = normalize_join_result_state(
        terminal_status="completed",
        explicit_state="adopted",
        final_apply_state="blocked",
        notification_state="foreground_adopted",
    )

    assert result_state == "blocked"

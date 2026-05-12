from __future__ import annotations

from cli.agent_cli.orchestration.taskbook_projection_runtime import (
    normalize_join_next_action,
    normalize_join_result_state,
)
from types import SimpleNamespace

from cli.agent_cli.runtime_core.background_task_commands_summary_runtime import (
    execution_projection_counts,
    workflows_text,
)


def test_workflows_text_includes_orchestration_summary_counters() -> None:
    text = workflows_text(
        delegated_lines=[],
        orchestration_lines=[
            "- orchestration | run_ready_001 | ready | workflow=ready | phase=taskbook_ready | cards=2 | ready=1 | running=0 | blocked=1",
            "- orchestration | run_running_001 | running | workflow=running | phase=cards_dispatched | cards=1 | ready=0 | running=1 | blocked=0",
            "- orchestration | run_review_001 | blocked | workflow=blocked | phase=review_pending | latest_acceptance=CARD-002:block | review_reason=CARD-002:manual_review_required | current=CARD-002:result_ready",
        ],
        background_lines=[],
        orchestration_count=3,
        mirrored_count=0,
        background_enabled=True,
    )

    assert "orchestration_runs=3" in text
    assert "orchestration_ready=1" in text
    assert "orchestration_running=1" in text
    assert "orchestration_blocked=1" in text
    assert "orchestration_review_pending=1" in text


def test_workflows_text_orchestration_counters_default_to_zero() -> None:
    text = workflows_text(
        delegated_lines=[],
        orchestration_lines=[],
        background_lines=[],
        orchestration_count=2,
        mirrored_count=0,
        background_enabled=False,
    )

    assert "orchestration_runs=2" in text
    assert "orchestration_ready=0" in text
    assert "orchestration_running=0" in text
    assert "orchestration_blocked=0" in text
    assert "orchestration_review_pending=0" in text


def test_workflows_text_includes_execution_projection_counters() -> None:
    text = workflows_text(
        delegated_lines=[],
        orchestration_lines=[],
        background_lines=[],
        orchestration_count=0,
        mirrored_count=0,
        background_enabled=False,
        execution_projection_counts={
            "total": 4,
            "running": 1,
            "completed": 1,
            "failed": 1,
            "cancelled": 0,
            "timed_out": 1,
        },
    )

    assert "execution_projection_runs=4" in text
    assert "execution_projection_running=1" in text
    assert "execution_projection_completed=1" in text
    assert "execution_projection_failed=1" in text
    assert "execution_projection_terminal=3" in text
    assert "execution_projection_attention=2" in text
    assert "execution_projection_timed_out=1" in text


def test_workflows_text_includes_action_required_counter() -> None:
    text = workflows_text(
        delegated_lines=[
            "- delegated | ag001 | completed | role=teammate | workflow=completed | completion=ready_to_adopt | result_state=pending_review"
        ],
        orchestration_lines=[
            "- orchestration | run001 | blocked | workflow=blocked | phase=review_pending | latest_acceptance=CARD-001:block"
        ],
        background_lines=[
            "- background | bg001 | completed | review required | result_state=pending_review | review=pending"
        ],
        orchestration_count=1,
        mirrored_count=0,
        background_enabled=True,
    )

    assert "workflow_action_required=3" in text


def test_workflows_text_includes_policy_surface_counters() -> None:
    text = workflows_text(
        delegated_lines=[
            "- delegated | ag001 | completed | role=teammate | workflow=completed | policy=checked",
            "- delegated | ag002 | completed | role=teammate | workflow=completed | policy=rewrite",
        ],
        orchestration_lines=[],
        background_lines=[
            "- background | bg001 | failed | policy denied | policy=denied | review=pending"
        ],
        orchestration_count=0,
        mirrored_count=0,
        background_enabled=True,
    )

    assert "workflow_policy_denied=1" in text
    assert "workflow_policy_rewrite=1" in text
    assert "workflow_policy_checked=1" in text


def test_workflows_text_ignores_zero_command_policy_count_for_checked_counter() -> None:
    text = workflows_text(
        delegated_lines=[
            "- delegated | ag001 | completed | role=teammate | workflow=completed | command_policies_count=0"
        ],
        orchestration_lines=[],
        background_lines=[],
        orchestration_count=0,
        mirrored_count=0,
        background_enabled=True,
    )

    assert "workflow_policy_checked=" not in text


def test_execution_projection_counts_ignores_turn_runs_and_counts_terminal_statuses() -> None:
    counts = execution_projection_counts(
        [
            SimpleNamespace(kind="turn", status="completed"),
            SimpleNamespace(kind="task", status="running"),
            SimpleNamespace(kind="workflow", status="completed"),
            SimpleNamespace(kind="background", status="failed"),
            SimpleNamespace(kind="custom", status="timed_out"),
        ]
    )

    assert counts == {
        "total": 4,
        "running": 1,
        "completed": 1,
        "failed": 1,
        "cancelled": 0,
        "timed_out": 1,
    }


def test_join_state_normalization_prefers_pending_review_over_adopted_signal() -> None:
    result_state = normalize_join_result_state(
        terminal_status="completed",
        explicit_state="adopted",
        completion_state="ready_to_adopt",
    )
    next_action = normalize_join_next_action(
        next_action="",
        result_state=result_state,
        completion_state="ready_to_adopt",
    )

    assert result_state == "pending_review"
    assert next_action == "review_or_adopt_teammate_result"

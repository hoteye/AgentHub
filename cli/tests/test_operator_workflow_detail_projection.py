from __future__ import annotations

from cli.agent_cli.ui import transcript_controller_projection_runtime


def test_operator_workflow_detail_lines_project_taskbook_projection_and_review_reason() -> None:
    assistant_text = (
        "- orchestration | ctrun_demo_1 | blocked | workflow=blocked | phase=review_pending"
        " | cards=4 | ready=0 | running=1 | blocked=1 | accepted=2"
        " | taskbook=v3,facts=5"
        " | projection=accept=2,pending=1,rework=1,blocked=0,failed=0"
        " | review_reason=acceptance:block"
        " | current=CARD-002:running"
        " | latest=CARD-001:completed"
    )

    lines = transcript_controller_projection_runtime.operator_workflow_detail_lines(assistant_text)

    assert len(lines) == 1
    line = lines[0]
    assert "orchestration ctrun_demo_1 blocked" in line
    assert "taskbook v3,facts=5" in line
    assert "projection accept=2,pending=1,rework=1,blocked=0,failed=0" in line
    assert "review acceptance:block" in line
    assert "current CARD-002:running" in line
    assert "latest CARD-001:completed" in line


def test_operator_workflow_detail_lines_project_acceptance_and_current_result() -> None:
    assistant_text = (
        "- orchestration | ctrun_demo_2 | running | workflow=running | phase=dispatching"
        " | latest_acceptance=CARD-001:accept"
        " | current_result=CARD-002:result_ready"
    )

    lines = transcript_controller_projection_runtime.operator_workflow_detail_lines(assistant_text)

    assert len(lines) == 1
    line = lines[0]
    assert "acceptance CARD-001:accept" in line
    assert "current result CARD-002:result_ready" in line


def test_operator_workflow_detail_lines_project_run_card_task_action_details() -> None:
    assistant_text = (
        "- orchestration | run_demo_42 | review | workflow=review | phase=card_review_pending"
        " | current=CARD-007:review"
        " | dispatch_ref=CARD-007:background_task:bg_teammate_007"
        " | review_action=apply"
    )

    lines = transcript_controller_projection_runtime.operator_workflow_detail_lines(assistant_text)

    assert len(lines) == 1
    line = lines[0]
    assert "orchestration run_demo_42 review" in line
    assert "run run_demo_42" in line
    assert "card CARD-007" in line
    assert "task bg_teammate_007" in line
    assert "action apply" in line
    assert "next op /orchestrate_apply run_demo_42 CARD-007" in line


def test_operator_workflow_detail_lines_project_next_op_for_reject() -> None:
    assistant_text = (
        "- orchestration | run_demo_43 | review | workflow=review | phase=card_review_pending"
        " | current=CARD-008:review"
        " | review_action=reject"
    )

    lines = transcript_controller_projection_runtime.operator_workflow_detail_lines(assistant_text)

    assert len(lines) == 1
    line = lines[0]
    assert "run run_demo_43" in line
    assert "card CARD-008" in line
    assert "action reject" in line
    assert "next op /orchestrate_reject run_demo_43 CARD-008" in line


def test_operator_workflow_detail_lines_project_next_op_for_background_apply() -> None:
    assistant_text = (
        "- background | bg_task_101 | review_pending | summary"
        " | task=bg_task_101"
        " | action=apply"
    )

    lines = transcript_controller_projection_runtime.operator_workflow_detail_lines(assistant_text)

    assert len(lines) == 1
    line = lines[0]
    assert "background bg_task_101 review_pending" in line
    assert "task bg_task_101" in line
    assert "action apply" in line
    assert "next op /background_task_apply bg_task_101" in line


def test_operator_workflow_detail_lines_project_next_op_for_delegated_wait() -> None:
    assistant_text = (
        "- delegated | agent_778 | running | role=teammate | workflow=running"
        " | task=agent_778"
        " | action=wait"
    )

    lines = transcript_controller_projection_runtime.operator_workflow_detail_lines(assistant_text)

    assert len(lines) == 1
    line = lines[0]
    assert "delegated agent_778 running" in line
    assert "task agent_778" in line
    assert "action wait" in line
    assert "next op /wait_agent agent_778" in line


def test_operator_workflow_detail_lines_project_next_op_for_background_timeout() -> None:
    assistant_text = (
        "- background | bg_task_102 | timed_out | summary"
        " | task=bg_task_102"
    )

    lines = transcript_controller_projection_runtime.operator_workflow_detail_lines(assistant_text)

    assert len(lines) == 1
    line = lines[0]
    assert "background bg_task_102 timed_out" in line
    assert "next op /background_task_retry bg_task_102" in line


def test_operator_workflow_detail_lines_project_next_op_for_delegated_orphaned() -> None:
    assistant_text = (
        "- delegated | agent_779 | orphaned | role=teammate | workflow=orphaned"
        " | task=agent_779"
    )

    lines = transcript_controller_projection_runtime.operator_workflow_detail_lines(assistant_text)

    assert len(lines) == 1
    line = lines[0]
    assert "delegated agent_779 orphaned" in line
    assert "next op /resume_agent agent_779" in line


def test_operator_workflow_detail_lines_project_replan_surface_from_nested_progress_payload() -> None:
    assistant_text = (
        "- orchestration | run_nested_001 | blocked | workflow=blocked | phase=review_pending"
        " | current=CARD-009:result_failed"
        " | progress_payload={\"replan_candidates\":[{\"action\":\"replan_candidate\",\"card_id\":\"CARD-009\"}],"
        "\"replan_pending\":[{\"card_id\":\"CARD-009\",\"pending_state\":\"awaiting_operator_action\"}],"
        "\"replan_pending_card_ids\":[\"CARD-009\"],"
        "\"operator_actions\":[{\"action\":\"replan_taskbook\",\"status\":\"pending\",\"card_id\":\"CARD-009\","
        "\"command_name\":\"/orchestrate_confirm\","
        "\"command\":\"/orchestrate_confirm <updated taskbook markdown>\"}]}"
    )

    lines = transcript_controller_projection_runtime.operator_workflow_detail_lines(assistant_text)

    assert len(lines) == 1
    line = lines[0]
    assert "orchestration run_nested_001 blocked" in line
    assert "replan candidates 1" in line
    assert "replan pending 1" in line
    assert "replan cards CARD-009" in line
    assert "operator actions 1" in line
    assert "operator next /orchestrate_confirm" in line


def test_operator_workflow_detail_lines_project_replan_followup_actions_summary() -> None:
    assistant_text = (
        "- orchestration | run_followup_001 | blocked | workflow=blocked | phase=review_pending"
        " | current=CARD-010:result_failed"
        " | replan_followup_actions=[{\"action\":\"replan_candidate\",\"scope\":\"card\","
        "\"trigger\":\"rework_escalated_after_retries\",\"card_id\":\"CARD-010\"}]"
    )

    lines = transcript_controller_projection_runtime.operator_workflow_detail_lines(assistant_text)

    assert len(lines) == 1
    line = lines[0]
    assert "orchestration run_followup_001 blocked" in line
    assert "replan followup 1" in line
    assert "replan scope card" in line
    assert "replan trigger rework_escalated_after_retries" in line

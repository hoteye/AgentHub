from __future__ import annotations

from cli.agent_cli.runtime_core.orchestration_commands import handle_orchestration_command


class _RuntimeStub:
    def continue_orchestration_run(
        self, run_id: str, *, max_passes: int = 8, dispatch_ready: bool = True
    ) -> dict[str, object]:
        assert max_passes == 8
        assert dispatch_ready is True
        if run_id == "run_continue_paused":
            return {
                "run_id": run_id,
                "status": "running",
                "current_phase": "cards_running",
                "max_passes": 8,
                "pass_count": 1,
                "stop_pass": 1,
                "mutated_pass_count": 0,
                "last_mutated_pass": 0,
                "stopped_reason": "waiting_on_running_cards",
                "pass_summaries": [
                    {
                        "pass": 1,
                        "status": "running",
                        "current_phase": "cards_running",
                        "mutated": False,
                        "stop_candidate": "waiting_on_running_cards",
                    },
                ],
                "synced_card_ids": [],
                "accepted_card_ids": [],
                "unlocked_card_ids": [],
                "selected_card_ids": [],
                "dispatched_card_ids": [],
                "dispatch_refs": [],
                "ready_card_ids": [],
                "running_card_ids": ["CARD-001", "CARD-002"],
                "blocked_card_ids": [],
                "completed_card_ids": [],
            }
        assert run_id == "run_continue_001"
        return {
            "run_id": run_id,
            "status": "completed",
            "current_phase": "taskbook_completed",
            "max_passes": 8,
            "pass_count": 3,
            "stop_pass": 3,
            "mutated_pass_count": 2,
            "last_mutated_pass": 2,
            "stopped_reason": "terminal:completed",
            "pass_summaries": [
                {
                    "pass": 1,
                    "status": "running",
                    "current_phase": "cards_running",
                    "mutated": True,
                    "stop_candidate": "continue",
                },
                {
                    "pass": 2,
                    "status": "running",
                    "current_phase": "cards_running",
                    "mutated": True,
                    "stop_candidate": "continue",
                },
                {
                    "pass": 3,
                    "status": "completed",
                    "current_phase": "taskbook_completed",
                    "mutated": False,
                    "stop_candidate": "terminal:completed",
                },
            ],
            "synced_card_ids": ["CARD-001", "CARD-002"],
            "accepted_card_ids": ["CARD-001", "CARD-002"],
            "unlocked_card_ids": [],
            "selected_card_ids": [],
            "dispatched_card_ids": [],
            "dispatch_refs": [],
            "ready_card_ids": [],
            "running_card_ids": [],
            "blocked_card_ids": [],
            "completed_card_ids": ["CARD-001", "CARD-002"],
        }

    def progress_orchestration_run(self, run_id: str) -> dict[str, object]:
        assert run_id == "run_progress_001"
        return {
            "run_id": run_id,
            "status": "running",
            "current_phase": "review_pending",
            "synced_card_ids": ["CARD-001", "CARD-002"],
            "accepted_card_ids": ["CARD-001"],
            "unlocked_card_ids": ["CARD-003"],
            "selected_card_ids": [],
            "dispatched_card_ids": [],
            "dispatch_refs": [],
            "ready_card_ids": ["CARD-003"],
            "running_card_ids": [],
            "blocked_card_ids": ["CARD-002"],
            "completed_card_ids": ["CARD-001"],
        }

    def apply_orchestration_card(self, run_id: str, card_id: str) -> dict[str, object]:
        assert run_id == "run_review_001"
        assert card_id == "CARD-010"
        return {
            "run_id": run_id,
            "card_id": card_id,
            "review_action": "apply",
            "task_id": "bg_010",
            "task_status": "completed",
            "final_apply_state": "applied",
            "applied_files": ["src/demo.py"],
            "status": "running",
            "current_phase": "cards_dispatched",
            "synced_card_ids": ["CARD-010"],
            "accepted_card_ids": ["CARD-010"],
            "unlocked_card_ids": ["CARD-011"],
            "selected_card_ids": ["CARD-011"],
            "dispatched_card_ids": ["CARD-011"],
            "dispatch_refs": ["CARD-011:delegated_subagent:ag_orch_011"],
            "ready_card_ids": [],
            "running_card_ids": ["CARD-011"],
            "blocked_card_ids": [],
            "completed_card_ids": ["CARD-010"],
        }

    def reject_orchestration_card(self, run_id: str, card_id: str) -> dict[str, object]:
        assert run_id == "run_review_002"
        assert card_id == "CARD-020"
        return {
            "run_id": run_id,
            "card_id": card_id,
            "review_action": "reject",
            "task_id": "bg_020",
            "task_status": "completed",
            "final_apply_state": "rejected",
            "status": "blocked",
            "current_phase": "review_pending",
            "synced_card_ids": ["CARD-020"],
            "accepted_card_ids": [],
            "unlocked_card_ids": [],
            "selected_card_ids": [],
            "dispatched_card_ids": [],
            "dispatch_refs": [],
            "ready_card_ids": [],
            "running_card_ids": [],
            "blocked_card_ids": ["CARD-020"],
            "completed_card_ids": [],
        }

    @staticmethod
    def _parse_args(arg_text: str) -> tuple[list[str], dict[str, str]]:
        return [item for item in str(arg_text or "").split() if item], {}


def test_orchestrate_progress_text_includes_acceptance_review_summary() -> None:
    text, _ = handle_orchestration_command(
        _RuntimeStub(),
        name="orchestrate_progress",
        arg_text="run_progress_001",
    ) or ("", [])

    assert "orchestration progress updated" in text
    assert "acceptance_applied_count=1" in text
    assert "review_pending_count=1" in text
    assert "review_pending_cards=CARD-002" in text
    assert "acceptance_unlocked_count=1" in text


def test_orchestrate_continue_text_includes_pass_telemetry_summary() -> None:
    text, _ = handle_orchestration_command(
        _RuntimeStub(),
        name="orchestrate_continue",
        arg_text="run_continue_001",
    ) or ("", [])

    assert "orchestration continue finished" in text
    assert "passes=3" in text
    assert "max_passes=8" in text
    assert "stop_pass=3" in text
    assert "mutated_passes=2" in text
    assert "last_mutated_pass=2" in text
    assert "stopped_reason=terminal:completed" in text
    assert (
        "pass_summaries=1:running/cards_running:mutated;2:running/cards_running:mutated;3:completed/taskbook_completed:noop:terminal:completed"
        in text
    )


def test_orchestrate_continue_text_reports_paused_when_children_are_still_running() -> None:
    text, _ = handle_orchestration_command(
        _RuntimeStub(),
        name="orchestrate_continue",
        arg_text="run_continue_paused",
    ) or ("", [])

    assert "orchestration continue paused" in text
    assert "stopped_reason=waiting_on_running_cards" in text
    assert "running_cards=2" in text
    assert "next_action=wait for running cards, then run /orchestrate_continue again" in text


def test_orchestrate_apply_text_includes_review_acceptance_state() -> None:
    text, _ = handle_orchestration_command(
        _RuntimeStub(),
        name="orchestrate_apply",
        arg_text="run_review_001 CARD-010",
    ) or ("", [])

    assert "orchestration staged changes applied" in text
    assert "review_action=apply" in text
    assert "card_acceptance_state=accepted" in text
    assert "card_acceptance_applied=true" in text
    assert "review_pending_count=0" in text
    assert "review_pending_cards=-" in text


def test_orchestrate_reject_text_includes_review_acceptance_state() -> None:
    text, _ = handle_orchestration_command(
        _RuntimeStub(),
        name="orchestrate_reject",
        arg_text="run_review_002 CARD-020",
    ) or ("", [])

    assert "orchestration staged changes rejected" in text
    assert "review_action=reject" in text
    assert "card_acceptance_state=rejected" in text
    assert "card_acceptance_applied=false" in text
    assert "review_pending_count=1" in text
    assert "review_pending_cards=CARD-020" in text

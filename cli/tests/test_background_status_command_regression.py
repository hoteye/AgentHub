from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cli.agent_cli.runtime_core.command_dispatch import run_command_text_result
from cli.agent_cli.runtime_core.command_parsing import parse_args


class _Runtime:
    def __init__(self) -> None:
        self.cwd = Path("/tmp/demo")

    @staticmethod
    def _parse_args(arg_text: str):
        return parse_args(arg_text)


def _background_task_status_text(payload: dict[str, object], *, task_id: str) -> str:
    runtime = _Runtime()
    normalized_payload = dict(payload)
    fake_adapter = SimpleNamespace(
        get_status=lambda requested_task_id: dict(normalized_payload, task_id=requested_task_id)
    )

    with patch("cli.agent_cli.background_tasks.build_background_task_adapter", return_value=fake_adapter):
        result = run_command_text_result(runtime, f"/background_task_status {task_id}")

    return result.assistant_text


def test_background_task_status_command_surfaces_lifecycle_and_queue_source_of_truth() -> None:
    runtime = _Runtime()
    fake_adapter = SimpleNamespace(
        get_status=lambda task_id: {
            "task_id": task_id,
            "status": "running",
            "queue_state": "running",
            "dispatch_id": 77,
            "artifact": {
                "queue_source_of_truth": "dispatch",
                "queue_provider": "huey",
            },
            "lifecycle": {
                "queue_source_of_truth": "dispatch_table",
                "queue_provider": "huey",
                "queue_state": "running",
                "dispatch_id": 77,
                "last_event": "cleanup_requeue",
                "cleanup_count": 2,
                "restore_count": 1,
                "stale_requeue_count": 3,
            },
        }
    )

    with patch("cli.agent_cli.background_tasks.build_background_task_adapter", return_value=fake_adapter):
        result = run_command_text_result(runtime, "/background_task_status bg_lifecycle")

    text = result.assistant_text
    assert "background task status" in text
    assert "task_id=bg_lifecycle" in text
    assert "queue_source_of_truth=dispatch" in text
    assert "queue_provider=huey" in text
    assert "lifecycle_queue_source_of_truth=dispatch_table" in text
    assert "lifecycle_queue_provider=huey" in text
    assert "lifecycle_queue_state=running" in text
    assert "lifecycle_dispatch_id=77" in text
    assert "lifecycle_last_event=cleanup_requeue" in text
    assert "lifecycle_cleanup_count=2" in text
    assert "lifecycle_restore_count=1" in text
    assert "lifecycle_stale_requeue_count=3" in text


def test_background_task_status_command_reads_structured_lifecycle_states_without_artifact() -> None:
    text = _background_task_status_text(
        {
            "status": "completed",
            "summary": "legacy summary should not be the state source",
            "lifecycle": {
                "completion_state": "ready_to_adopt",
                "result_state": "pending_review",
                "adoption_expectation": "review_or_adopt_teammate_result",
                "notification_state": "ready",
                "final_apply_pending": True,
                "adopted": False,
            },
        },
        task_id="bg_teammate_ready",
    )

    assert "background task status" in text
    assert "task_id=bg_teammate_ready" in text
    assert "completion_state=ready_to_adopt" in text
    assert "result_state=pending_review" in text
    assert "adoption_expectation=review_or_adopt_teammate_result" in text
    assert "notification_state=ready" in text
    assert "final_apply_state=pending" in text
    assert "adopted=false" in text
    assert "evidence_result_state=pending_review" in text


def test_background_task_status_command_surfaces_shell_returned_evidence_from_structured_fields() -> None:
    text = _background_task_status_text(
        {
            "status": "completed",
            "task_type": "shell",
            "summary": "background shell result adopted",
            "lifecycle": {
                "completion_state": "ready_to_adopt",
                "adoption_expectation": "resume_agent_to_continue",
                "notification_state": "ready",
                "adopted": False,
            },
        },
        task_id="sh_bg_1",
    )

    assert "task_id=sh_bg_1" in text
    assert "task_type=shell" in text
    assert "summary=background shell result adopted" in text
    assert "completion_state=ready_to_adopt" in text
    assert "adoption_expectation=resume_agent_to_continue" in text
    assert "adopted=false" in text
    assert "evidence_result_state=returned" in text


def test_background_task_status_command_prefers_blocked_evidence_over_adopted_review_text() -> None:
    text = _background_task_status_text(
        {
            "status": "completed",
            "summary": "background shell result adopted",
            "lifecycle": {
                "completion_state": "adopted",
                "result_state": "adopted",
                "notification_state": "foreground_adopted",
                "adopted": True,
            },
            "artifact": {
                "final_apply_state": "blocked",
            },
        },
        task_id="bg_apply_review",
    )

    assert "task_id=bg_apply_review" in text
    assert "summary=background shell result adopted" in text
    assert "completion_state=adopted" in text
    assert "result_state=adopted" in text
    assert "notification_state=foreground_adopted" in text
    assert "final_apply_state=blocked" in text
    assert "adopted=true" in text
    assert "evidence_result_state=blocked" in text

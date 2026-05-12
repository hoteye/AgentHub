from __future__ import annotations

from cli.agent_cli.runtime_core import (
    background_task_commands_summary_runtime,
    background_task_commands_text_runtime,
    background_task_commands_worker_runtime,
)


def test_background_worker_status_text_includes_version_fields() -> None:
    text = background_task_commands_worker_runtime.background_worker_status_text(
        enabled=True,
        provider="huey",
        queue_provider_label="huey",
        payload={
            "health": "healthy",
            "status": "busy",
            "worker_pid": 1234,
            "worker_code_version": "sig:old",
            "current_worker_code_version": "sig:new",
            "worker_code_version_match": False,
        },
    )
    assert "worker_code_version=sig:old" in text
    assert "current_worker_code_version=sig:new" in text
    assert "worker_code_version_match=false" in text


def test_background_task_status_text_includes_running_snapshot_policy_and_lifecycle_fields() -> None:
    text = background_task_commands_text_runtime.background_task_status_text(
        {
            "status": "running",
            "queue_state": "running",
            "result_state": "pending_review",
            "dispatch_id": 42,
            "lifecycle": {
                "queue_source_of_truth": "dispatch_table",
                "queue_provider": "huey",
                "queue_state": "running",
                "dispatch_id": 42,
                "last_event": "cleanup_requeue",
                "cleanup_count": 2,
                "restore_count": 1,
                "stale_requeue_count": 3,
            },
            "artifact": {
                "running_snapshot_path": "/tmp/bg_running.json",
                "queue_source_of_truth": "dispatch",
                "queue_provider": "huey",
                "worker_pid": 5678,
                "result_state": "pending_review",
                "lifecycle_cleanup_count": 9,
                "lifecycle_restore_count": 9,
                "stale_requeue_count": 9,
                "command_policies": [
                    {
                        "command": "pytest -q tests/test_demo.py",
                        "effective_command": "python /tmp/lock.py -- pytest -q tests/test_demo.py",
                        "policy_denied": False,
                    }
                ],
            },
        },
        task_id="bg_test_status",
    )
    assert "running_snapshot_path=/tmp/bg_running.json" in text
    assert "queue_source_of_truth=dispatch" in text
    assert "queue_provider=huey" in text
    assert "worker_pid=5678" in text
    assert "result_state=pending_review" in text
    assert "command_policies=" in text
    assert "lifecycle_queue_source_of_truth=dispatch_table" in text
    assert "lifecycle_queue_provider=huey" in text
    assert "lifecycle_queue_state=running" in text
    assert "lifecycle_dispatch_id=42" in text
    assert "lifecycle_last_event=cleanup_requeue" in text
    assert "lifecycle_cleanup_count=2" in text
    assert "lifecycle_restore_count=1" in text
    assert "lifecycle_stale_requeue_count=3" in text


def test_background_task_status_text_includes_tenant_scope_visibility() -> None:
    text = background_task_commands_text_runtime.background_task_status_text(
        {
            "status": "running",
            "lifecycle": {
                "tenant_id": "tenant_lifecycle",
                "workspace_scope": "workspace_lifecycle",
            },
            "artifact": {
                "tenant_id": "tenant_artifact",
                "workspace_scope": "workspace_artifact",
            },
        },
        task_id="bg_tenant_scope",
    )
    assert "tenant_id=tenant_lifecycle" in text
    assert "workspace_scope=workspace_lifecycle" in text
    assert "tenant_scope_profile=isolated" in text
    assert "tenant_id=tenant_artifact" not in text
    assert "workspace_scope=workspace_artifact" not in text


def test_background_task_status_text_includes_default_tenant_scope_profile() -> None:
    text = background_task_commands_text_runtime.background_task_status_text(
        {
            "status": "queued",
            "tenant_id": "default",
            "workspace_scope": "default",
        },
        task_id="bg_default_scope",
    )
    assert "tenant_id=default" in text
    assert "workspace_scope=default" in text
    assert "tenant_scope_profile=default" in text


def test_background_task_status_text_surfaces_shell_lifecycle_fields_without_artifact() -> None:
    text = background_task_commands_text_runtime.background_task_status_text(
        {
            "status": "completed",
            "summary": "legacy shell summary",
            "lifecycle": {
                "completion_state": "ready_to_adopt",
                "result_state": "returned",
                "adoption_expectation": "resume_agent_to_continue",
                "notification_state": "ready",
                "adopted": False,
            },
        },
        task_id="sh_bg_1",
    )

    assert "completion_state=ready_to_adopt" in text
    assert "result_state=returned" in text
    assert "adoption_expectation=resume_agent_to_continue" in text
    assert "notification_state=ready" in text
    assert "adopted=false" in text


def test_background_task_status_text_surfaces_teammate_review_from_lifecycle() -> None:
    text = background_task_commands_text_runtime.background_task_status_text(
        {
            "status": "completed",
            "summary": "legacy teammate summary",
            "lifecycle": {
                "completion_state": "ready_to_adopt",
                "result_state": "pending_review",
                "adoption_expectation": "review_or_adopt_teammate_result",
                "final_apply_pending": True,
            },
        },
        task_id="bg_teammate_ready",
    )

    assert "completion_state=ready_to_adopt" in text
    assert "result_state=pending_review" in text
    assert "adoption_expectation=review_or_adopt_teammate_result" in text
    assert "final_apply_state=pending" in text


def test_background_result_state_counts_prefers_structured_fields() -> None:
    returned, adopted, pending_review = background_task_commands_summary_runtime._background_result_state_counts(
        [
            "- background | bg_1 | completed | done | result_state=returned | terminal_state=completed",
            "- background | bg_2 | completed | adopted | result_state=adopted | notify=foreground_adopted",
            "- background | bg_3 | completed | review required | result_state=pending_review | review=pending",
        ]
    )

    assert returned == 1
    assert adopted == 1
    assert pending_review == 1


def test_background_result_state_counts_normalize_shell_teammate_and_final_apply_review() -> None:
    returned, adopted, pending_review = background_task_commands_summary_runtime._background_result_state_counts(
        [
            (
                "- background | sh_bg_1 | completed | legacy shell text"
                " | completion_state=ready_to_adopt"
                " | result_state=returned"
                " | adoption_expectation=resume_agent_to_continue"
                " | notification_state=ready"
            ),
            (
                "- background | bg_teammate_1 | completed | legacy teammate text"
                " | type=teammate"
                " | completion=ready_to_adopt"
                " | next=review_or_adopt_teammate_result"
            ),
            (
                "- background | bg_apply_1 | completed | adopted"
                " | result_state=adopted"
                " | notify=foreground_adopted"
                " | final_apply_state=blocked"
            ),
            (
                "- background | bg_adopted_1 | completed | returned"
                " | completion_state=adopted"
                " | adoption_expectation=already_adopted"
            ),
        ]
    )

    assert returned == 1
    assert adopted == 1
    assert pending_review == 2

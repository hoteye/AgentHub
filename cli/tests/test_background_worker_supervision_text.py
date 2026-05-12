from __future__ import annotations

from cli.agent_cli.runtime_core import background_task_commands_worker_runtime


def test_background_worker_status_text_includes_operator_supervision_hints() -> None:
    text = background_task_commands_worker_runtime.background_worker_status_text(
        enabled=True,
        provider="huey",
        queue_provider_label="huey",
        payload={
            "status": "running",
            "worker_code_version": "sig:old",
            "current_worker_code_version": "sig:new",
            "worker_code_version_match": False,
            "worker_code_signature_source": "worker_code_version_files",
            "worker_code_signature_algorithm": "sha256",
            "worker_code_signature_file_count": 10,
            "restart_reason": "code_version_mismatch",
            "active_task_id": "bg_123",
            "active_task_type": "teammate",
            "last_cleanup_count": 2,
            "last_cleanup_task_ids": ["bg_orphan_1", "bg_orphan_2"],
        },
    )

    assert "supervision_restart_required=true" in text
    assert "supervision_code_version_mismatch=true" in text
    assert "supervision_code_version=sig:old->sig:new" in text
    assert "supervision_signature_source=worker_code_version_files" in text
    assert "supervision_signature_algorithm=sha256" in text
    assert "supervision_signature_file_count=10" in text
    assert "supervision_restart_hint=restart_worker:code_version_mismatch" in text
    assert "supervision_active_task=bg_123:teammate" in text
    assert "supervision_cleanup_count=2" in text
    assert 'supervision_cleanup_task_ids=["bg_orphan_1", "bg_orphan_2"]' in text


def test_background_worker_status_text_supervision_defaults_when_idle() -> None:
    text = background_task_commands_worker_runtime.background_worker_status_text(
        enabled=True,
        provider="huey",
        queue_provider_label="huey",
        payload={
            "status": "idle",
            "worker_code_version": "sig:same",
            "current_worker_code_version": "sig:same",
            "worker_code_version_match": True,
        },
    )

    assert "supervision_restart_required=false" in text
    assert "supervision_code_version_mismatch=false" in text
    assert "supervision_restart_hint=no_restart_needed" in text
    assert "supervision_active_task=none" in text
    assert "supervision_cleanup=none" in text


def test_background_worker_status_text_always_shows_core_supervision_fields() -> None:
    text = background_task_commands_worker_runtime.background_worker_status_text(
        enabled=True,
        provider="huey",
        queue_provider_label="huey",
        payload={
            "status": "idle",
        },
    )

    assert "started_at=-" in text
    assert "worker_code_version=-" in text
    assert "current_worker_code_version=-" in text
    assert "worker_code_version_match=-" in text
    assert "restart_required=-" in text


def test_background_worker_start_text_surfaces_restart_required_supervision() -> None:
    text = background_task_commands_worker_runtime.background_worker_start_text(
        max_jobs=4,
        poll_interval=0.5,
        stale_after_seconds=90.0,
        payload={
            "started": False,
            "reason": "code_version_mismatch",
            "worker_code_version": "sig:old",
            "current_worker_code_version": "sig:new",
            "restart_required": True,
        },
    )

    assert "restart_required=true" in text
    assert "supervision_restart_required=true" in text
    assert "supervision_code_version_mismatch=true" in text

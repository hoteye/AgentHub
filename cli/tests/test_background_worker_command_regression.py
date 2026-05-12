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


def test_background_worker_status_command_surfaces_supervision_hints() -> None:
    runtime = _Runtime()
    fake_adapter = SimpleNamespace(
        config=SimpleNamespace(enabled=True, provider="huey"),
        queue=SimpleNamespace(provider_label="huey"),
        worker_status=lambda: {
            "health": "stale",
            "status": "running",
            "mode": "detached",
            "worker_pid": 4567,
            "active_task_id": "bg_123",
            "active_task_type": "teammate",
            "stop_reason": "version_mismatch_requires_restart",
            "worker_code_version": "sig:old",
            "current_worker_code_version": "sig:new",
            "worker_code_version_match": False,
            "restart_required": True,
            "restart_reason": "code_version_mismatch",
            "worker_code_signature_source": "worker_code_version_files",
            "worker_code_signature_algorithm": "sha256",
            "worker_code_signature_file_count": 10,
            "last_cleanup_count": 1,
            "last_cleanup_task_ids": ["bg_orphan_1"],
        },
    )

    with patch("cli.agent_cli.background_tasks.build_background_task_adapter", return_value=fake_adapter):
        result = run_command_text_result(runtime, "/background_worker_status")

    text = result.assistant_text
    assert "background worker status" in text
    assert "health=stale" in text
    assert "status=running" in text
    assert "mode=detached" in text
    assert "worker_pid=4567" in text
    assert "active_task_id=bg_123" in text
    assert "active_task_type=teammate" in text
    assert "stop_reason=version_mismatch_requires_restart" in text
    assert "supervision_restart_required=true" in text
    assert "supervision_code_version_mismatch=true" in text
    assert "supervision_code_version=sig:old->sig:new" in text
    assert "supervision_signature_source=worker_code_version_files" in text
    assert "supervision_signature_algorithm=sha256" in text
    assert "supervision_signature_file_count=10" in text
    assert "supervision_restart_hint=restart_worker:code_version_mismatch" in text
    assert "supervision_active_task=bg_123:teammate" in text
    assert "supervision_cleanup_count=1" in text
    assert 'supervision_cleanup_task_ids=["bg_orphan_1"]' in text


def test_background_worker_status_command_shows_supervision_defaults_when_idle() -> None:
    runtime = _Runtime()
    fake_adapter = SimpleNamespace(
        config=SimpleNamespace(enabled=True, provider="huey"),
        queue=SimpleNamespace(provider_label="huey"),
        worker_status=lambda: {
            "health": "healthy",
            "status": "idle",
            "worker_code_version": "sig:same",
            "current_worker_code_version": "sig:same",
            "worker_code_version_match": True,
            "restart_required": False,
        },
    )

    with patch("cli.agent_cli.background_tasks.build_background_task_adapter", return_value=fake_adapter):
        result = run_command_text_result(runtime, "/background_worker_status")

    text = result.assistant_text
    assert "health=healthy" in text
    assert "status=idle" in text
    assert "supervision_restart_required=false" in text
    assert "supervision_code_version_mismatch=false" in text
    assert "supervision_restart_hint=no_restart_needed" in text
    assert "supervision_active_task=none" in text
    assert "supervision_cleanup=none" in text

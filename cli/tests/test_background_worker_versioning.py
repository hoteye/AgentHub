from __future__ import annotations

from pathlib import Path

from cli.agent_cli.background_tasks.adapter import build_background_task_adapter
from cli.agent_cli.background_tasks.config import BackgroundTasksConfig, HueyConfig
from cli.agent_cli.background_tasks.worker_entry import run_worker_once, start_worker_process
from cli.agent_cli.background_tasks.worker_state import (
    background_worker_status,
    current_worker_code_version,
    read_worker_state,
    write_worker_state,
)
from cli.agent_cli.runtime_core.background_task_commands_worker_runtime import background_worker_status_text


class _DummyAdapter:
    def __init__(self, *, config: BackgroundTasksConfig, status_payload: dict[str, object]) -> None:
        self.config = config
        self._status_payload = dict(status_payload)

    def worker_status(self) -> dict[str, object]:
        return dict(self._status_payload)


def _config(tmp_path: Path) -> BackgroundTasksConfig:
    return BackgroundTasksConfig(
        enabled=True,
        provider="huey",
        huey=HueyConfig(
            backend="sqlite",
            path=tmp_path / "background_tasks.sqlite3",
            results_dir=tmp_path / "results",
            worker_count=1,
            immediate=False,
        ),
    )


def test_background_worker_status_exposes_worker_code_version(monkeypatch, tmp_path: Path) -> None:
    config = _config(tmp_path)
    version = current_worker_code_version()
    monkeypatch.setattr("cli.agent_cli.background_tasks.worker_state._pid_is_running", lambda pid: True)
    write_worker_state(
        config,
        {
            "status": "idle",
            "mode": "loop",
            "worker_pid": 1234,
            "worker_code_version": version,
        },
    )

    status = background_worker_status(config, queue_provider="huey")

    assert status["worker_code_version"] == version
    assert status["current_worker_code_version"] == version
    assert status["worker_code_version_match"] is True
    assert status["worker_code_signature_source"] == "worker_code_version_files"
    assert status["worker_code_signature_algorithm"] == "sha256"
    assert status["worker_code_signature_file_count"] > 0
    assert status["restart_required"] is False


def test_background_worker_status_marks_restart_required_on_version_mismatch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    write_worker_state(
        config,
        {
            "status": "idle",
            "mode": "loop",
            "worker_pid": 1234,
            "worker_code_version": "sig:old_worker",
        },
    )
    monkeypatch.setattr(
        "cli.agent_cli.background_tasks.worker_state.current_worker_code_version",
        lambda: "sig:new_worker",
    )

    status = background_worker_status(config, queue_provider="huey")

    assert status["worker_code_version"] == "sig:old_worker"
    assert status["current_worker_code_version"] == "sig:new_worker"
    assert status["worker_code_version_match"] is False
    assert status["worker_code_signature_source"] == "worker_code_version_files"
    assert status["restart_required"] is True
    assert status["restart_reason"] == "code_version_mismatch"


def test_background_worker_status_marks_restart_required_on_stale_pid(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    version = current_worker_code_version()
    write_worker_state(
        config,
        {
            "status": "running",
            "mode": "loop",
            "worker_pid": 43210,
            "worker_code_version": version,
        },
    )
    monkeypatch.setattr("cli.agent_cli.background_tasks.worker_state._pid_is_running", lambda pid: False)

    status = background_worker_status(config, queue_provider="huey")

    assert status["worker_code_version_match"] is True
    assert status["restart_required"] is True
    assert status["restart_reason"] == "worker_pid_stale"


def test_start_worker_process_returns_version_mismatch_for_healthy_worker(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    adapter = _DummyAdapter(
        config=config,
        status_payload={
            "health": "healthy",
            "worker_pid": 777,
            "state_path": str(config.huey.results_dir / "worker_state.json"),
            "worker_code_version": "sig:old_worker",
        },
    )
    monkeypatch.setattr("cli.agent_cli.background_tasks.worker_entry.build_background_task_adapter", lambda cwd=None: adapter)
    monkeypatch.setattr("cli.agent_cli.background_tasks.worker_entry.current_worker_code_version", lambda: "sig:new_worker")

    payload = start_worker_process(cwd=tmp_path)

    assert payload["started"] is False
    assert payload["reason"] == "worker_version_mismatch"
    assert payload["restart_required"] is True
    assert payload["restart_reason"] == "code_version_mismatch"
    assert payload["worker_code_version"] == "sig:old_worker"
    assert payload["current_worker_code_version"] == "sig:new_worker"
    assert payload["worker_code_version_match"] is False
    assert payload["worker_code_signature_source"] == "worker_code_version_files"
    assert payload["worker_code_signature_algorithm"] == "sha256"
    assert payload["worker_code_signature_file_count"] > 0


def test_start_worker_process_returns_already_healthy_when_version_matches(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config = _config(tmp_path)
    adapter = _DummyAdapter(
        config=config,
        status_payload={
            "health": "healthy",
            "worker_pid": 888,
            "state_path": str(config.huey.results_dir / "worker_state.json"),
            "worker_code_version": "sig:same_worker",
        },
    )
    monkeypatch.setattr("cli.agent_cli.background_tasks.worker_entry.build_background_task_adapter", lambda cwd=None: adapter)
    monkeypatch.setattr("cli.agent_cli.background_tasks.worker_entry.current_worker_code_version", lambda: "sig:same_worker")

    payload = start_worker_process(cwd=tmp_path)

    assert payload["started"] is False
    assert payload["reason"] == "worker_already_healthy"
    assert payload["worker_code_version"] == "sig:same_worker"
    assert payload["current_worker_code_version"] == "sig:same_worker"
    assert payload["worker_code_version_match"] is True
    assert payload["worker_code_signature_source"] == "worker_code_version_files"
    assert payload["restart_required"] is False


def test_run_worker_once_persists_worker_code_version(monkeypatch, tmp_path: Path) -> None:
    adapter = build_background_task_adapter(config=_config(tmp_path))
    monkeypatch.setattr("cli.agent_cli.background_tasks.worker_entry.build_background_task_adapter", lambda cwd=None: adapter)
    monkeypatch.setattr(
        "cli.agent_cli.background_tasks.adapter.BackgroundTaskAdapter.cleanup_stale_tasks",
        lambda self, max_age_seconds: [],
    )
    monkeypatch.setattr(
        "cli.agent_cli.background_tasks.adapter.BackgroundTaskAdapter.run_pending",
        lambda self, max_jobs, perform_maintenance=False: 0,
    )

    run_worker_once(cwd=tmp_path, max_jobs=1)

    worker_state = read_worker_state(adapter.config)
    status = background_worker_status(adapter.config, queue_provider=adapter.queue.provider_label)
    assert worker_state["worker_code_version"] == current_worker_code_version()
    assert status["worker_code_version"] == current_worker_code_version()
    assert status["worker_code_version_match"] is True


def test_background_worker_status_exposes_active_task_and_stop_reason(tmp_path: Path) -> None:
    config = _config(tmp_path)
    write_worker_state(
        config,
        {
            "status": "busy",
            "mode": "loop",
            "worker_pid": 1234,
            "worker_code_version": current_worker_code_version(),
            "active_task_id": "bg_task_001",
            "active_task_type": "teammate",
            "active_runner_pid": 5678,
            "stop_reason": "worker_stopped",
        },
    )

    status = background_worker_status(config, queue_provider="huey")

    assert status["active_task_id"] == "bg_task_001"
    assert status["active_task_type"] == "teammate"
    assert status["active_runner_pid"] == 5678
    assert status["stop_reason"] == "worker_stopped"


def test_background_worker_status_text_includes_supervision_fields() -> None:
    text = background_worker_status_text(
        enabled=True,
        provider="huey",
        queue_provider_label="huey",
        payload={
            "health": "healthy",
            "status": "busy",
            "worker_pid": 1234,
            "active_task_id": "bg_task_001",
            "active_task_type": "teammate",
            "active_runner_pid": 5678,
            "stop_reason": "worker_stopped",
        },
    )

    assert "active_task_id=bg_task_001" in text
    assert "active_task_type=teammate" in text
    assert "active_runner_pid=5678" in text
    assert "stop_reason=worker_stopped" in text

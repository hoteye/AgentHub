from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cli.agent_cli.background_tasks.adapter import build_background_task_adapter, enqueue_background_task
from cli.agent_cli.background_tasks.config import BackgroundTasksConfig, HueyConfig
from cli.agent_cli.background_tasks.models import (
    BackgroundTaskPriority,
    BackgroundTaskStatus,
    BackgroundTaskType,
    TaskEnvelope,
    TaskMetadata,
    TaskResult,
    utc_now_iso,
)
from cli.agent_cli.background_tasks import worker_entry_state_runtime
from cli.agent_cli.background_tasks.worker_entry import run_worker_once, stop_worker_process
from cli.agent_cli.background_tasks.worker_state import read_worker_state, touch_worker_state_results_dir, write_worker_state

def test_run_worker_once_consumes_one_queued_task(monkeypatch, tmp_path: Path) -> None:
    adapter = build_background_task_adapter(
        config=BackgroundTasksConfig(
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
    )
    handle = enqueue_background_task(
        task_type="smoke",
        payload={"kind": "multi_llm"},
        source="cli",
        adapter=adapter,
    )

    seen: list[str] = []

    def _fake_execute(envelope, *, storage, runner_token="", claimed=False):
        seen.append(envelope.task_id)
        storage.complete_dispatch(
            envelope.task_id,
            dispatch_id=envelope.dispatch_id,
            queue_state=BackgroundTaskStatus.COMPLETED.value,
            runner_token=runner_token,
        )
        result = TaskResult(
            task_id=envelope.task_id,
            status=BackgroundTaskStatus.COMPLETED,
            started_at=utc_now_iso(),
            finished_at=utc_now_iso(),
            summary="worker completed",
        )
        storage.upsert_result(result)
        return result

    monkeypatch.setattr("cli.agent_cli.background_tasks.adapter.execute_background_task", _fake_execute)
    monkeypatch.setattr("cli.agent_cli.background_tasks.worker_entry.build_background_task_adapter", lambda cwd=None: adapter)

    processed = run_worker_once(max_jobs=1)

    assert processed == 1
    assert seen == [handle.task_id]
    status = adapter.get_status(handle.task_id)
    assert status is not None
    assert status["status"] == "completed"
    worker_state = read_worker_state(adapter.config)
    assert worker_state["status"] == "stopped"
    assert worker_state["mode"] == "once"
    assert worker_state["worker_pid"] > 0
    assert worker_state["last_processed_count"] == 1
    assert worker_state["queue_provider"] == adapter.queue.provider_label
    assert worker_state["last_cleanup_count"] == 0


def test_loop_iteration_state_returns_idle_after_processed_batch() -> None:
    state = worker_entry_state_runtime.loop_iteration_state(
        {
            "mode": "loop",
            "worker_pid": 1234,
            "cwd": "/tmp/demo",
            "started_at": "2026-04-06T10:00:00+00:00",
            "max_jobs": 1,
            "poll_interval": 1.0,
            "provider": "huey",
            "queue_provider": "huey",
            "huey_available": True,
            "stale_after_seconds": 30.0,
            "worker_code_version": "sig:test",
        },
        heartbeat_at="2026-04-06T10:00:10+00:00",
        processed=1,
        last_processed_at="2026-04-06T10:00:10+00:00",
        last_cleanup_count=0,
        last_cleanup_at="",
        last_cleanup_task_ids=[],
    )

    assert state["status"] == "idle"
    assert state["last_processed_count"] == 1

def test_run_worker_once_requeues_stale_running_task_before_processing(monkeypatch, tmp_path: Path) -> None:
    adapter = build_background_task_adapter(
        config=BackgroundTasksConfig(
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
    )
    handle = enqueue_background_task(
        task_type="teammate",
        payload={"task": "repair repo"},
        source="cli",
        adapter=adapter,
    )
    claimed = adapter.storage.claim_next_queued(runner_token="runner_stale")
    assert claimed is not None

    stale_timestamp = (datetime.now(timezone.utc) - timedelta(seconds=120)).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(adapter.storage.db_path) as conn:
        conn.execute(
            """
            UPDATE background_task_dispatches
            SET updated_at = ?, runner_pid = 0
            WHERE task_id = ?
            """,
            (stale_timestamp, handle.task_id),
        )
        conn.commit()

    seen: list[str] = []

    def _fake_execute(envelope, *, storage, runner_token="", claimed=False):
        seen.append(envelope.task_id)
        storage.complete_dispatch(
            envelope.task_id,
            dispatch_id=envelope.dispatch_id,
            queue_state=BackgroundTaskStatus.COMPLETED.value,
            runner_token=runner_token,
        )
        result = TaskResult(
            task_id=envelope.task_id,
            status=BackgroundTaskStatus.COMPLETED,
            started_at=utc_now_iso(),
            finished_at=utc_now_iso(),
            summary="worker recovered stale task",
        )
        storage.upsert_result(result)
        return result

    monkeypatch.setattr("cli.agent_cli.background_tasks.adapter.execute_background_task", _fake_execute)
    monkeypatch.setattr("cli.agent_cli.background_tasks.worker_entry.build_background_task_adapter", lambda cwd=None: adapter)

    processed = run_worker_once(max_jobs=1, stale_after_seconds=30)

    assert processed == 1
    assert seen == [handle.task_id]
    worker_state = read_worker_state(adapter.config)
    assert worker_state["last_cleanup_count"] == 1
    assert worker_state["last_cleanup_task_ids"] == [handle.task_id]


def test_run_worker_once_only_consumes_default_scope_queue(monkeypatch, tmp_path: Path) -> None:
    adapter = build_background_task_adapter(
        config=BackgroundTasksConfig(
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
    )
    default_handle = enqueue_background_task(
        task_type="smoke",
        payload={"kind": "default_scope"},
        source="cli",
        adapter=adapter,
    )
    adapter.enqueue(
        TaskEnvelope(
            task_id="bg_scoped_worker_entry_task",
            task_type=BackgroundTaskType.SMOKE,
            source="cli",
            priority=BackgroundTaskPriority.LOW,
            payload={"kind": "scoped_only"},
            metadata=TaskMetadata(),
            tenant_id="tenant_beta",
            workspace_scope="workspace_beta",
        )
    )

    seen: list[str] = []

    def _fake_execute(envelope, *, storage, runner_token="", claimed=False):
        seen.append(envelope.task_id)
        storage.complete_dispatch(
            envelope.task_id,
            dispatch_id=envelope.dispatch_id,
            queue_state=BackgroundTaskStatus.COMPLETED.value,
            runner_token=runner_token,
        )
        result = TaskResult(
            task_id=envelope.task_id,
            status=BackgroundTaskStatus.COMPLETED,
            started_at=utc_now_iso(),
            finished_at=utc_now_iso(),
            summary="worker completed default scope task",
        )
        storage.upsert_result(result)
        return result

    monkeypatch.setattr("cli.agent_cli.background_tasks.adapter.execute_background_task", _fake_execute)
    monkeypatch.setattr("cli.agent_cli.background_tasks.worker_entry.build_background_task_adapter", lambda cwd=None: adapter)

    processed = run_worker_once(max_jobs=2)

    assert processed == 1
    assert seen == [default_handle.task_id]
    default_status = adapter.get_status(default_handle.task_id)
    scoped_status = adapter.get_status("bg_scoped_worker_entry_task")
    assert default_status is not None and default_status["status"] == "completed"
    assert scoped_status is not None and scoped_status["status"] == "queued"
    assert scoped_status["control"]["tenant_id"] == "tenant_beta"
    assert scoped_status["control"]["workspace_scope"] == "workspace_beta"

def test_stop_worker_process_updates_worker_state(monkeypatch, tmp_path: Path) -> None:
    adapter = build_background_task_adapter(
        config=BackgroundTasksConfig(
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
    )
    write_worker_state(
        adapter.config,
        {
            "status": "idle",
            "mode": "loop",
            "worker_pid": 4321,
            "cwd": str(tmp_path),
            "last_heartbeat_at": utc_now_iso(),
        },
    )
    monkeypatch.setattr("cli.agent_cli.background_tasks.worker_entry.build_background_task_adapter", lambda cwd=None: adapter)
    running_states = iter([True, False])
    monkeypatch.setattr(
        "cli.agent_cli.background_tasks.worker_entry._pid_is_running",
        lambda pid: next(running_states),
    )
    seen: list[tuple[int, int]] = []
    monkeypatch.setattr(
        "cli.agent_cli.background_tasks.worker_entry.os.kill",
        lambda pid, sig: seen.append((pid, int(sig))),
    )

    payload = stop_worker_process(cwd=tmp_path)

    assert payload["stopped"] is True
    assert payload["worker_pid"] == 4321
    assert seen and seen[0][0] == 4321
    worker_state = read_worker_state(adapter.config)
    assert worker_state["status"] == "stopped"
    assert worker_state["stop_reason"] == "worker_stopped"


def test_stop_worker_process_marks_not_running_worker_as_stopped(monkeypatch, tmp_path: Path) -> None:
    adapter = build_background_task_adapter(
        config=BackgroundTasksConfig(
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
    )
    write_worker_state(
        adapter.config,
        {
            "status": "running",
            "mode": "loop",
            "worker_pid": 4321,
            "cwd": str(tmp_path),
            "last_heartbeat_at": utc_now_iso(),
        },
    )
    monkeypatch.setattr("cli.agent_cli.background_tasks.worker_entry.build_background_task_adapter", lambda cwd=None: adapter)
    monkeypatch.setattr("cli.agent_cli.background_tasks.worker_entry._pid_is_running", lambda pid: False)

    payload = stop_worker_process(cwd=tmp_path)

    assert payload["stopped"] is True
    assert payload["reason"] == "worker_not_running"
    worker_state = read_worker_state(adapter.config)
    assert worker_state["status"] == "stopped"
    assert worker_state["stop_reason"] == "worker_not_running"


def test_stop_worker_process_treats_stopped_state_as_success_when_pid_stays_running(
    monkeypatch,
    tmp_path: Path,
) -> None:
    adapter = build_background_task_adapter(
        config=BackgroundTasksConfig(
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
    )
    write_worker_state(
        adapter.config,
        {
            "status": "running",
            "mode": "loop",
            "worker_pid": 4321,
            "cwd": str(tmp_path),
            "last_heartbeat_at": utc_now_iso(),
        },
    )
    monkeypatch.setattr("cli.agent_cli.background_tasks.worker_entry.build_background_task_adapter", lambda cwd=None: adapter)
    monkeypatch.setattr("cli.agent_cli.background_tasks.worker_entry._pid_is_running", lambda pid: True)
    seen: list[tuple[int, int]] = []
    monkeypatch.setattr(
        "cli.agent_cli.background_tasks.worker_entry.os.kill",
        lambda pid, sig: seen.append((pid, int(sig))),
    )

    states = iter(
        [
            {
                "status": "running",
                "mode": "loop",
                "worker_pid": 4321,
            },
            {
                "status": "stopped",
                "mode": "loop",
                "worker_pid": 4321,
                "stopped_at": utc_now_iso(),
            },
        ]
    )
    monkeypatch.setattr(
        "cli.agent_cli.background_tasks.worker_entry.read_worker_state",
        lambda config: next(states, {"status": "stopped", "worker_pid": 4321}),
    )

    payload = stop_worker_process(cwd=tmp_path, wait_timeout_seconds=0.1)

    assert payload["stopped"] is True
    assert payload["reason"] == "worker_stopped_state"
    assert seen and seen[0][0] == 4321


def test_touch_worker_state_results_dir_refreshes_loop_heartbeat(tmp_path: Path) -> None:
    adapter = build_background_task_adapter(
        config=BackgroundTasksConfig(
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
    )
    write_worker_state(
        adapter.config,
        {
            "status": "idle",
            "mode": "loop",
            "worker_pid": 9876,
            "cwd": str(tmp_path),
            "last_heartbeat_at": "2026-04-05T00:00:00+00:00",
        },
    )

    touch_worker_state_results_dir(
        adapter.config.huey.results_dir,
        status="busy",
        active_task_id="bg_live_1",
        active_task_type="teammate",
    )

    worker_state = read_worker_state(adapter.config)
    assert worker_state["status"] == "busy"
    assert worker_state["active_task_id"] == "bg_live_1"
    assert worker_state["active_task_type"] == "teammate"
    assert worker_state["last_heartbeat_at"] != "2026-04-05T00:00:00+00:00"


def test_touch_worker_state_results_dir_ignores_foreign_runner_for_active_loop_worker(
    monkeypatch,
    tmp_path: Path,
) -> None:
    adapter = build_background_task_adapter(
        config=BackgroundTasksConfig(
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
    )
    write_worker_state(
        adapter.config,
        {
            "status": "idle",
            "mode": "loop",
            "worker_pid": 9876,
            "cwd": str(tmp_path),
            "last_heartbeat_at": "2026-04-05T00:00:00+00:00",
        },
    )
    monkeypatch.setattr("cli.agent_cli.background_tasks.worker_state._pid_is_running", lambda pid: pid == 9876)

    touch_worker_state_results_dir(
        adapter.config.huey.results_dir,
        status="busy",
        active_task_id="bg_foreign_1",
        active_task_type="teammate",
        runner_pid=1234,
    )

    worker_state = read_worker_state(adapter.config)
    assert worker_state["status"] == "idle"
    assert worker_state["worker_pid"] == 9876
    assert worker_state.get("active_task_id") in (None, "")
    assert worker_state["last_heartbeat_at"] == "2026-04-05T00:00:00+00:00"


def test_run_worker_once_does_not_clobber_active_loop_worker_state(monkeypatch, tmp_path: Path) -> None:
    adapter = build_background_task_adapter(
        config=BackgroundTasksConfig(
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
    )
    write_worker_state(
        adapter.config,
        {
            "status": "idle",
            "mode": "loop",
            "worker_pid": 4321,
            "cwd": str(tmp_path),
            "last_heartbeat_at": utc_now_iso(),
        },
    )
    monkeypatch.setattr("cli.agent_cli.background_tasks.worker_entry.build_background_task_adapter", lambda cwd=None: adapter)
    monkeypatch.setattr("cli.agent_cli.background_tasks.worker_entry._pid_is_running", lambda pid: pid == 4321)
    monkeypatch.setattr("cli.agent_cli.background_tasks.adapter.BackgroundTaskAdapter.cleanup_stale_tasks", lambda self, max_age_seconds: [])
    monkeypatch.setattr(
        "cli.agent_cli.background_tasks.adapter.BackgroundTaskAdapter.run_pending",
        lambda self, max_jobs, perform_maintenance=False: 0,
    )

    processed = run_worker_once(max_jobs=1)

    assert processed == 0
    worker_state = read_worker_state(adapter.config)
    assert worker_state["mode"] == "loop"
    assert worker_state["status"] == "idle"
    assert worker_state["worker_pid"] == 4321

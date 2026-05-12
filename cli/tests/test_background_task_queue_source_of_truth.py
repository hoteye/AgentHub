from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from cli.agent_cli.background_tasks.adapter import BackgroundTaskAdapter
from cli.agent_cli.background_tasks.config import BackgroundTasksConfig, HueyConfig
from cli.agent_cli.background_tasks.models import (
    BackgroundTaskType,
    QueueHandle,
    TaskEnvelope,
)
from cli.agent_cli.background_tasks.queue import create_queue
from cli.agent_cli.background_tasks.storage import BackgroundTaskStorage


def _test_config(tmp_path: Path) -> BackgroundTasksConfig:
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


def test_huey_queue_enqueue_does_not_push_business_task_into_huey_task_table(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import cli.agent_cli.background_tasks.queue as queue_module

    observed = {"runner_calls": 0}

    class _FakeSqliteHuey:
        def __init__(self, *args, **kwargs) -> None:
            self._args = args
            self._kwargs = kwargs

        def task(self):
            def decorator(fn):
                def wrapped(payload):
                    observed["runner_calls"] += 1
                    return SimpleNamespace(id="fake-job")

                return wrapped

            return decorator

    monkeypatch.setattr(queue_module, "SqliteHuey", _FakeSqliteHuey)

    queue_obj = create_queue(
        config={
            "enabled": True,
            "provider": "huey",
            "huey": {
                "backend": "sqlite",
                "path": str(tmp_path / "agenthub_huey.db"),
                "results_dir": str(tmp_path / "results"),
                "worker_count": 1,
                "immediate": False,
            },
        },
        executor=lambda envelope: envelope,
    )

    handle = queue_obj.enqueue(
        {
            "task_id": "bg_queue_truth_1",
            "task_type": "smoke",
            "source": "test",
            "payload": {"kind": "multi_llm"},
        }
    )

    assert isinstance(handle, QueueHandle)
    assert handle.status == "queued"
    assert handle.task_id == "bg_queue_truth_1"
    assert observed["runner_calls"] == 0


def test_adapter_run_pending_consumes_dispatch_queue_even_if_provider_returns_completed_count(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import cli.agent_cli.background_tasks.adapter as adapter_module

    class _FakeQueue:
        provider_label = "huey"
        immediate = False

        def __init__(self) -> None:
            self.enqueued: list[str] = []
            self.run_pending_calls: list[int] = []

        def enqueue(self, envelope):
            task = envelope if isinstance(envelope, TaskEnvelope) else TaskEnvelope.from_dict(envelope)
            self.enqueued.append(task.task_id)
            return QueueHandle(task_id=task.task_id, status="queued", job_id="fake-job", provider=self.provider_label)

        def run_pending(self, *, max_jobs: int = 1) -> int:
            self.run_pending_calls.append(max_jobs)
            return 99

        def huey_instance(self):
            return None

    storage = BackgroundTaskStorage(
        results_dir=tmp_path / "results",
        db_path=tmp_path / "background_tasks.sqlite3",
    )
    queue = _FakeQueue()
    adapter = BackgroundTaskAdapter(config=_test_config(tmp_path), storage=storage, queue=queue)

    envelope = TaskEnvelope(
        task_id="bg_queue_truth_2",
        task_type=BackgroundTaskType.SMOKE,
        source="test",
        payload={"kind": "multi_llm"},
    )
    adapter.enqueue(envelope)

    executed: list[str] = []

    def _fake_execute(task_envelope, *, storage, runner_token, claimed):
        del storage, runner_token, claimed
        executed.append(task_envelope.task_id)
        return None

    monkeypatch.setattr(adapter_module, "execute_background_task", _fake_execute)

    processed = adapter.run_pending(max_jobs=1, perform_maintenance=False)

    assert queue.run_pending_calls == [1]
    assert processed == 1
    assert executed == ["bg_queue_truth_2"]


def test_adapter_status_and_artifact_report_dispatch_as_queue_source_of_truth(tmp_path: Path) -> None:
    class _NoopQueue:
        provider_label = "huey"
        immediate = False

        def enqueue(self, envelope):
            task = envelope if isinstance(envelope, TaskEnvelope) else TaskEnvelope.from_dict(envelope)
            return QueueHandle(task_id=task.task_id, status="queued", job_id=task.task_id, provider=self.provider_label)

        def run_pending(self, *, max_jobs: int = 1) -> int:
            _ = max_jobs
            return 0

        def huey_instance(self):
            return None

    storage = BackgroundTaskStorage(
        results_dir=tmp_path / "results",
        db_path=tmp_path / "background_tasks.sqlite3",
    )
    adapter = BackgroundTaskAdapter(config=_test_config(tmp_path), storage=storage, queue=_NoopQueue())
    envelope = TaskEnvelope(
        task_id="bg_queue_truth_3",
        task_type=BackgroundTaskType.BENCHMARK,
        source="test",
        payload={"case": "openai:gpt_54"},
    )
    adapter.enqueue(envelope)

    status = adapter.get_status(envelope.task_id)
    assert status is not None
    assert status["queue_source_of_truth"] == "dispatch"
    assert status["queue_provider"] == "huey"
    assert status["artifact"]["queue_source_of_truth"] == "dispatch"

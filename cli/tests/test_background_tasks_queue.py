from __future__ import annotations

import importlib
import inspect
from pathlib import Path

import pytest

def _import_queue_module():
    try:
        return importlib.import_module("cli.agent_cli.background_tasks.queue")
    except ModuleNotFoundError:
        pytest.skip("background_tasks.queue not implemented yet")

def _pick_callable(module, *names):
    for name in names:
        candidate = getattr(module, name, None)
        if callable(candidate):
            return candidate
    pytest.skip(f"queue factory not found, tried {names}")

def _lookup_value(obj, key):
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)

def _build_queue(factory, tmp_path: Path, *, immediate: bool):
    params = inspect.signature(factory).parameters
    kwargs = {}
    if "immediate" in params:
        kwargs["immediate"] = immediate
    if "config" in params:
        kwargs["config"] = {
            "enabled": True,
            "provider": "huey",
            "huey": {
                "backend": "sqlite",
                "path": str(tmp_path / "agenthub_huey.db"),
                "results_dir": str(tmp_path / "results"),
                "worker_count": 1,
                "immediate": immediate,
            },
        }
    if "sqlite_path" in params:
        kwargs["sqlite_path"] = tmp_path / "agenthub_huey.db"
    if "results_dir" in params:
        kwargs["results_dir"] = tmp_path / "results"
    return factory(**kwargs)

def _enqueue(queue_obj, envelope: dict):
    enqueue_fn = None
    for name in ("enqueue", "submit", "put", "enqueue_task"):
        candidate = getattr(queue_obj, name, None)
        if callable(candidate):
            enqueue_fn = candidate
            break
    if enqueue_fn is None:
        pytest.skip("no enqueue-like API found on queue object")
    params = inspect.signature(enqueue_fn).parameters
    if "envelope" in params:
        return enqueue_fn(envelope=envelope)
    if "task" in params:
        return enqueue_fn(task=envelope)
    return enqueue_fn(envelope)

def test_queue_factory_accepts_immediate_mode(tmp_path: Path) -> None:
    module = _import_queue_module()
    factory = _pick_callable(module, "build_queue", "create_queue", "build_background_queue")
    queue_obj = _build_queue(factory, tmp_path, immediate=True)

    assert queue_obj is not None
    explicit_flag = _lookup_value(queue_obj, "immediate")
    if explicit_flag is None:
        explicit_flag = _lookup_value(queue_obj, "is_immediate")
    if explicit_flag is not None:
        assert bool(explicit_flag) is True

def test_immediate_mode_enqueue_has_synchronous_result_or_job_id(tmp_path: Path) -> None:
    module = _import_queue_module()
    factory = _pick_callable(module, "build_queue", "create_queue", "build_background_queue")
    queue_obj = _build_queue(factory, tmp_path, immediate=True)
    envelope = {
        "task_id": "bg_queue_immediate",
        "task_type": "benchmark",
        "source": "cli",
        "payload": {"models": ["claude-sonnet-4-6"]},
    }

    result = _enqueue(queue_obj, envelope)
    assert result is not None
    # Contract-level assertion: enqueue should at least return a handle, task id, or status-shaped result.
    if isinstance(result, (str, int)):
        assert str(result)
        return
    status = _lookup_value(result, "status")
    task_id = _lookup_value(result, "task_id")
    job_id = _lookup_value(result, "job_id")
    assert status is not None or task_id is not None or job_id is not None

def test_huey_unavailable_queue_enqueue_does_not_execute_synchronously(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _import_queue_module()
    factory = _pick_callable(module, "build_queue", "create_queue", "build_background_queue")
    seen: list[str] = []

    monkeypatch.setattr(module, "SqliteHuey", None)
    queue_obj = factory(
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
        executor=lambda envelope: seen.append(_lookup_value(envelope, "task_id")) or envelope,
    )

    result = _enqueue(
        queue_obj,
        {
            "task_id": "bg_queue_async",
            "task_type": "smoke",
            "source": "cli",
            "payload": {"kind": "multi_llm"},
        },
    )

    assert seen == []
    assert _lookup_value(result, "status") == "queued"


def test_queue_runtime_task_artifact_exposes_dispatch_lifecycle_event() -> None:
    from cli.agent_cli.background_tasks.models import BackgroundTaskType, TaskEnvelope
    from cli.agent_cli.background_tasks.queue_runtime import _task_artifact

    artifact = _task_artifact(
        TaskEnvelope(
            task_id="bg_queue_lifecycle_1",
            task_type=BackgroundTaskType.SMOKE,
            source="test",
            payload={"kind": "multi_llm"},
        ),
        queue_state="running",
        cancel_requested=False,
    )

    assert artifact["queue_source_of_truth"] == "dispatch"
    assert artifact["lifecycle_last_event"] == "dispatch_claimed"


def test_queue_runtime_task_artifact_exposes_cancel_requested_lifecycle_event() -> None:
    from cli.agent_cli.background_tasks.models import BackgroundTaskType, TaskEnvelope
    from cli.agent_cli.background_tasks.queue_runtime import _task_artifact

    artifact = _task_artifact(
        TaskEnvelope(
            task_id="bg_queue_lifecycle_2",
            task_type=BackgroundTaskType.SMOKE,
            source="test",
            payload={"kind": "multi_llm"},
        ),
        queue_state="",
        cancel_requested=True,
    )

    assert artifact["queue_source_of_truth"] == "dispatch"
    assert artifact["lifecycle_last_event"] == "cancel_requested"

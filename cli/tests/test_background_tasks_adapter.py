from __future__ import annotations

import importlib
import inspect
import json
from pathlib import Path

import pytest

from cli.agent_cli.background_tasks.models import (
    BackgroundTaskPriority,
    BackgroundTaskStatus,
    BackgroundTaskType,
    TaskEnvelope,
    TaskMetadata,
    TaskResult,
)

def _import_adapter_module():
    try:
        return importlib.import_module("cli.agent_cli.background_tasks.adapter")
    except ModuleNotFoundError:
        pytest.skip("background_tasks.adapter not implemented yet")

def _pick_callable(module, *names):
    for name in names:
        candidate = getattr(module, name, None)
        if callable(candidate):
            return candidate
    pytest.skip(f"adapter API not found, tried {names}")

def _lookup_value(obj, key):
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)

def test_adapter_normalizes_minimal_envelope_fields() -> None:
    module = _import_adapter_module()
    normalize = _pick_callable(
        module,
        "normalize_task_request",
        "normalize_envelope",
        "build_task_envelope",
    )
    params = inspect.signature(normalize).parameters
    kwargs = {}
    if "task_type" in params:
        kwargs["task_type"] = "benchmark"
    if "source" in params:
        kwargs["source"] = "cli"
    if "payload" in params:
        kwargs["payload"] = {"models": ["claude-haiku-4-5-20251001"]}
    if "metadata" in params:
        kwargs["metadata"] = {"provider_name": "anthropic", "model": "claude-haiku-4-5-20251001"}

    envelope = normalize(**kwargs)

    assert envelope is not None
    assert _lookup_value(envelope, "task_type") == "benchmark"
    assert _lookup_value(envelope, "source") == "cli"
    assert _lookup_value(envelope, "payload") is not None
    assert _lookup_value(envelope, "task_id") is not None

def test_adapter_enqueue_returns_task_handle_shape() -> None:
    module = _import_adapter_module()
    enqueue = _pick_callable(
        module,
        "enqueue_background_task",
        "submit_background_task",
    )
    params = inspect.signature(enqueue).parameters
    kwargs = {}

    if "task_type" in params:
        kwargs["task_type"] = "smoke"
    if "payload" in params:
        kwargs["payload"] = {"suite": "policy_helper_live"}
    if "source" in params:
        kwargs["source"] = "cli"
    if "priority" in params:
        kwargs["priority"] = "low"
    if "metadata" in params:
        kwargs["metadata"] = {"reason": "manual verification"}

    if not kwargs:
        pytest.skip("enqueue adapter signature not stable yet")

    result = enqueue(**kwargs)
    assert result is not None
    assert (
        _lookup_value(result, "task_id") is not None
        or _lookup_value(result, "job_id") is not None
        or _lookup_value(result, "status") is not None
    )

def test_adapter_cancel_and_retry_roundtrip(tmp_path: Path) -> None:
    module = _import_adapter_module()
    if not all(hasattr(module, name) for name in ("BackgroundTaskAdapter", "build_background_task_adapter")):
        pytest.skip("background task adapter class not implemented yet")

    from cli.agent_cli.background_tasks.config import BackgroundTasksConfig, HueyConfig

    adapter = module.build_background_task_adapter(
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

    handle = module.enqueue_background_task(
        task_type="smoke",
        payload={"kind": "multi_llm"},
        source="cli",
        adapter=adapter,
    )
    status = adapter.get_status(handle.task_id)
    assert status is not None
    assert status["status"] == "queued"
    assert status["task_type"] == "smoke"
    assert status["dispatch_id"] == 1

    cancelled = adapter.cancel(handle.task_id)
    assert cancelled is not None
    assert cancelled["status"] == "cancelled"
    assert cancelled["queue_state"] == "cancelled"
    assert cancelled["lifecycle"]["queue_source_of_truth"] == "dispatch"
    assert cancelled["lifecycle"]["queue_state"] == "cancelled"

    retried = adapter.retry(handle.task_id)
    assert retried is not None
    assert retried["status"] == "queued"
    assert retried["dispatch_id"] == 2
    assert retried["retry_count"] == 1
    assert retried["lifecycle"]["last_event"] == "manual_retry_restore"
    assert retried["lifecycle"]["restore_count"] == 1
    assert retried["lifecycle"]["queue_source_of_truth"] == "dispatch"


def test_adapter_get_status_reconciles_terminal_result_with_stale_running_control(tmp_path: Path) -> None:
    module = _import_adapter_module()
    if not all(hasattr(module, name) for name in ("BackgroundTaskAdapter", "build_background_task_adapter")):
        pytest.skip("background task adapter class not implemented yet")

    from cli.agent_cli.background_tasks.config import BackgroundTasksConfig, HueyConfig

    adapter = module.build_background_task_adapter(
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

    handle = module.enqueue_background_task(
        task_type="teammate",
        payload={"task": "repair repo"},
        source="cli",
        adapter=adapter,
    )
    claimed = adapter.storage.claim_next_queued(runner_token="runner_1")
    assert claimed is not None
    adapter.storage.upsert_result(
        TaskResult(
            task_id=handle.task_id,
            status=BackgroundTaskStatus.CANCELLED,
            started_at="2026-04-06T10:00:00+00:00",
            finished_at="2026-04-06T10:00:30+00:00",
            summary="teammate task cancelled",
            artifact={"dispatch_id": 1, "queue_state": "cancelled"},
        )
    )

    status = adapter.get_status(handle.task_id)

    assert status is not None
    assert status["status"] == "cancelled"
    assert status["queue_state"] == "cancelled"
    assert status["cancel_requested"] is False
    assert status["artifact"]["queue_state"] == "cancelled"
    assert status["artifact"]["queue_source_of_truth"] == "dispatch"
    assert status["artifact"]["lifecycle_last_event"] == "dispatch_cancelled"
    control = adapter.storage.control_snapshot(handle.task_id)
    assert control is not None
    assert control["queue_state"] == "cancelled"
    assert control["runner_pid"] == 0
    assert control["runner_token"] == ""


def test_adapter_mark_completed_closes_dispatch_state_machine(tmp_path: Path) -> None:
    module = _import_adapter_module()
    if not all(hasattr(module, name) for name in ("BackgroundTaskAdapter", "build_background_task_adapter")):
        pytest.skip("background task adapter class not implemented yet")

    from cli.agent_cli.background_tasks.config import BackgroundTasksConfig, HueyConfig

    adapter = module.build_background_task_adapter(
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
    handle = module.enqueue_background_task(
        task_type="benchmark",
        payload={"case": "contract"},
        source="cli",
        adapter=adapter,
    )

    result = adapter.mark_completed(
        handle.task_id,
        summary="benchmark finished",
        artifact={"snapshot_path": str(tmp_path / "results" / "bench.json")},
    )
    status = adapter.get_status(handle.task_id)
    control = adapter.storage.control_snapshot(handle.task_id)

    assert result.status == BackgroundTaskStatus.COMPLETED
    assert result.artifact["queue_state"] == "completed"
    assert result.artifact["queue_source_of_truth"] == "dispatch"
    assert result.artifact["lifecycle_last_event"] == "dispatch_completed"
    assert result.artifact["dispatch_id"] == 1
    assert status is not None
    assert status["status"] == "completed"
    assert status["queue_state"] == "completed"
    assert status["artifact"]["queue_state"] == "completed"
    assert status["artifact"]["queue_source_of_truth"] == "dispatch"
    assert status["artifact"]["dispatch_id"] == 1
    assert control is not None
    assert control["queue_state"] == "completed"
    assert control["cancel_requested"] is False


def test_adapter_cancel_is_noop_after_terminal_completion(tmp_path: Path) -> None:
    module = _import_adapter_module()
    if not all(hasattr(module, name) for name in ("BackgroundTaskAdapter", "build_background_task_adapter")):
        pytest.skip("background task adapter class not implemented yet")

    from cli.agent_cli.background_tasks.config import BackgroundTasksConfig, HueyConfig

    adapter = module.build_background_task_adapter(
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
    handle = module.enqueue_background_task(
        task_type="smoke",
        payload={"kind": "multi_llm"},
        source="cli",
        adapter=adapter,
    )
    adapter.mark_completed(handle.task_id, summary="smoke finished")

    cancelled = adapter.cancel(handle.task_id)

    assert cancelled is not None
    assert cancelled["status"] == "completed"
    assert cancelled["queue_state"] == "completed"
    assert cancelled["cancel_requested"] is False
    assert cancelled["artifact"]["queue_state"] == "completed"
    assert cancelled["artifact"]["lifecycle_last_event"] == "dispatch_completed"


def test_adapter_apply_staged_changes_keeps_completed_dispatch_contract(tmp_path: Path) -> None:
    module = _import_adapter_module()
    if not all(hasattr(module, name) for name in ("BackgroundTaskAdapter", "build_background_task_adapter")):
        pytest.skip("background task adapter class not implemented yet")

    from cli.agent_cli.background_tasks.config import BackgroundTasksConfig, HueyConfig

    adapter = module.build_background_task_adapter(
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
    handle = module.enqueue_background_task(
        task_type="teammate",
        payload={"task": "apply staged changes"},
        source="cli",
        adapter=adapter,
    )

    live_cwd = tmp_path / "live"
    stage_cwd = tmp_path / "stage"
    live_cwd.mkdir()
    stage_cwd.mkdir()
    (live_cwd / "demo.txt").write_text("before\n", encoding="utf-8")
    (stage_cwd / "demo.txt").write_text("after\n", encoding="utf-8")
    review_path = tmp_path / "results" / "review_payload.json"
    review_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.write_text(
        json.dumps(
            {
                "live_cwd": str(live_cwd),
                "stage_cwd": str(stage_cwd),
                "changes": [{"path": "demo.txt", "change_type": "modify"}],
                "allowed_paths": ["."],
                "blocked_paths": [".git"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    adapter.mark_completed(
        handle.task_id,
        summary="teammate result ready",
        artifact={
            "staged_workspace": True,
            "final_apply_pending": True,
            "review_path": str(review_path),
            "stage_cwd": str(stage_cwd),
            "live_cwd": str(live_cwd),
            "allowed_paths": ["."],
            "blocked_paths": [".git"],
        },
    )

    adopted = adapter.apply_staged_changes(handle.task_id)

    assert adopted is not None
    assert adopted["status"] == "completed"
    assert adopted["queue_state"] == "completed"
    assert adopted["artifact"]["queue_state"] == "completed"
    assert adopted["artifact"]["queue_source_of_truth"] == "dispatch"
    assert adopted["artifact"]["final_apply_pending"] is False
    assert adopted["artifact"]["final_apply_state"] == "applied"
    assert adopted["artifact"]["applied_files"] == ["demo.txt"]
    assert (live_cwd / "demo.txt").read_text(encoding="utf-8") == "after\n"


def test_adapter_policy_helper_regression_enqueue_helper(tmp_path: Path) -> None:
    module = _import_adapter_module()
    if not all(
        hasattr(module, name)
        for name in (
            "build_background_task_adapter",
            "build_policy_helper_regression_payload",
            "enqueue_policy_helper_regression_task",
        )
    ):
        pytest.skip("policy helper regression entry helpers not implemented yet")

    from cli.agent_cli.background_tasks.config import BackgroundTasksConfig, HueyConfig

    adapter = module.build_background_task_adapter(
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

    payload = module.build_policy_helper_regression_payload(
        payload={"timeout_seconds": 45},
        argv=["--helper-combo", "deepseek_low_latency"],
    )
    assert payload["preset"] == "policy_helper_regression"
    assert payload["timeout_seconds"] == 45
    assert payload["argv"] == ["--helper-combo", "deepseek_low_latency"]

    handle = module.enqueue_policy_helper_regression_task(
        payload={"timeout_seconds": 45},
        argv=["--helper-combo", "deepseek_low_latency"],
        source="cli",
        adapter=adapter,
    )
    envelope = adapter.get_envelope(handle.task_id)
    assert envelope is not None
    assert envelope.task_type.value == "smoke"
    assert envelope.payload["preset"] == "policy_helper_regression"
    assert envelope.payload["timeout_seconds"] == 45
    assert envelope.payload["argv"] == ["--helper-combo", "deepseek_low_latency"]


def test_background_tasks_package_exports_policy_helper_regression_helpers() -> None:
    package = importlib.import_module("cli.agent_cli.background_tasks")
    adapter_module = _import_adapter_module()

    assert hasattr(package, "build_policy_helper_regression_payload")
    assert hasattr(package, "enqueue_policy_helper_regression_task")
    assert package.build_policy_helper_regression_payload is adapter_module.build_policy_helper_regression_payload
    assert package.enqueue_policy_helper_regression_task is adapter_module.enqueue_policy_helper_regression_task
    assert hasattr(package, "enqueue_background_task")


def test_adapter_status_surface_keeps_default_claim_scope(tmp_path: Path) -> None:
    module = _import_adapter_module()
    if not all(hasattr(module, name) for name in ("build_background_task_adapter", "enqueue_background_task")):
        pytest.skip("background task adapter helpers not implemented yet")

    from cli.agent_cli.background_tasks.config import BackgroundTasksConfig, HueyConfig

    adapter = module.build_background_task_adapter(
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
    handle = module.enqueue_background_task(
        task_type="smoke",
        payload={"kind": "default_scope_contract"},
        source="cli",
        adapter=adapter,
    )
    status = adapter.get_status(handle.task_id)

    assert status is not None
    assert status["control"]["tenant_id"] == "default"
    assert status["control"]["workspace_scope"] == "default"
    envelope = status["control"]["envelope"]
    assert _lookup_value(envelope, "tenant_id") == "default"
    assert _lookup_value(envelope, "workspace_scope") == "default"


def test_adapter_enqueue_preserves_non_default_scope_for_claim_contract(tmp_path: Path) -> None:
    module = _import_adapter_module()
    if not hasattr(module, "build_background_task_adapter"):
        pytest.skip("background task adapter helpers not implemented yet")

    from cli.agent_cli.background_tasks.config import BackgroundTasksConfig, HueyConfig

    adapter = module.build_background_task_adapter(
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
    envelope = TaskEnvelope(
        task_id="bg_scope_contract_task",
        task_type=BackgroundTaskType.SMOKE,
        source="cli",
        priority=BackgroundTaskPriority.LOW,
        payload={"kind": "scope_contract"},
        metadata=TaskMetadata(),
        tenant_id="tenant_alpha",
        workspace_scope="workspace_alpha",
    )
    adapter.enqueue(envelope)

    default_claim = adapter.storage.claim_next_queued(runner_token="runner_default")
    scoped_claim = adapter.storage.claim_next_queued(
        runner_token="runner_scoped",
        tenant_id="tenant_alpha",
        workspace_scope="workspace_alpha",
    )
    status = adapter.get_status(envelope.task_id)

    assert default_claim is None
    assert scoped_claim is not None
    assert scoped_claim.task_id == envelope.task_id
    assert status is not None
    assert status["control"]["tenant_id"] == "tenant_alpha"
    assert status["control"]["workspace_scope"] == "workspace_alpha"

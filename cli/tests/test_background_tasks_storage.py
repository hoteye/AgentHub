from __future__ import annotations

import importlib
import inspect
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

def _import_storage_module():
    try:
        return importlib.import_module("cli.agent_cli.background_tasks.storage")
    except ModuleNotFoundError:
        pytest.skip("background_tasks.storage not implemented yet")

def _pick_attr(obj, *names):
    for name in names:
        candidate = getattr(obj, name, None)
        if candidate is not None:
            return candidate
    return None

def _lookup_value(obj, key):
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)

def _build_store(module, results_dir: Path):
    cls = _pick_attr(module, "SnapshotStorage", "BackgroundTaskStorage", "BackgroundTaskSnapshotStore")
    if cls is None:
        return None
    params = inspect.signature(cls).parameters
    kwargs = {}
    if "results_dir" in params:
        kwargs["results_dir"] = results_dir
    elif "base_dir" in params:
        kwargs["base_dir"] = results_dir
    elif "root_dir" in params:
        kwargs["root_dir"] = results_dir
    elif "path" in params:
        kwargs["path"] = results_dir
    return cls(**kwargs)

def _write_snapshot(store, snapshot: dict):
    method = _pick_attr(store, "write_snapshot", "save_snapshot", "upsert_snapshot", "put_snapshot")
    if not callable(method):
        pytest.skip("snapshot write API not found")
    params = inspect.signature(method).parameters
    if "snapshot" in params:
        return method(snapshot=snapshot)
    if "data" in params:
        return method(data=snapshot)
    return method(snapshot)

def _read_snapshot(store, task_id: str):
    method = _pick_attr(store, "read_snapshot", "load_snapshot", "get_snapshot")
    if not callable(method):
        pytest.skip("snapshot read API not found")
    params = inspect.signature(method).parameters
    if "task_id" in params:
        return method(task_id=task_id)
    return method(task_id)

def test_snapshot_roundtrip_minimal_fields(tmp_path: Path) -> None:
    module = _import_storage_module()
    store = _build_store(module, tmp_path / "results")
    if store is None:
        pytest.skip("snapshot storage class not implemented yet")

    task_id = "bg_test_roundtrip"
    snapshot = {
        "task_id": task_id,
        "status": "completed",
        "summary": "benchmark finished",
        "artifact": {"report": "results/bg_test_roundtrip.json"},
        "error": "",
        "retry_count": 0,
    }
    _write_snapshot(store, snapshot)

    loaded = _read_snapshot(store, task_id)
    assert loaded is not None
    assert _lookup_value(loaded, "task_id") == task_id
    assert _lookup_value(loaded, "status") == "completed"
    assert _lookup_value(loaded, "summary") == "benchmark finished"

def test_snapshot_overwrite_keeps_latest_status(tmp_path: Path) -> None:
    module = _import_storage_module()
    store = _build_store(module, tmp_path / "results")
    if store is None:
        pytest.skip("snapshot storage class not implemented yet")

    task_id = "bg_test_overwrite"
    _write_snapshot(store, {"task_id": task_id, "status": "running", "summary": "start"})
    _write_snapshot(store, {"task_id": task_id, "status": "failed", "summary": "network error", "retry_count": 1})

    loaded = _read_snapshot(store, task_id)
    assert loaded is not None
    assert _lookup_value(loaded, "status") == "failed"
    assert _lookup_value(loaded, "summary") == "network error"

def test_storage_control_roundtrip_supports_claim_and_cancel(tmp_path: Path) -> None:
    module = _import_storage_module()
    store = _build_store(module, tmp_path / "results")
    if store is None:
        pytest.skip("snapshot storage class not implemented yet")
    required_names = ("upsert_envelope", "control_snapshot", "claim_next_queued", "request_cancel", "is_cancel_requested")
    if any(not hasattr(store, name) for name in required_names):
        pytest.skip("control plane APIs not found")

    from cli.agent_cli.background_tasks.models import BackgroundTaskType, TaskEnvelope

    envelope = TaskEnvelope(
        task_id="bg_control",
        task_type=BackgroundTaskType.SMOKE,
        payload={"kind": "multi_llm"},
    )
    store.upsert_envelope(envelope)

    control = store.control_snapshot("bg_control")
    assert control is not None
    assert control["task_id"] == "bg_control"
    assert control["queue_state"] == "queued"
    assert control["dispatch_id"] == 1
    assert control["envelope"]["task_type"] == "smoke"

    claimed = store.claim_next_queued(runner_token="runner_1")
    assert claimed is not None
    assert claimed.task_id == "bg_control"
    control = store.control_snapshot("bg_control")
    assert control is not None
    assert control["queue_state"] == "running"
    assert control["runner_token"] == "runner_1"

    assert store.request_cancel("bg_control") is True
    assert store.is_cancel_requested("bg_control", dispatch_id=1) is True
    assert store.complete_dispatch("bg_control", dispatch_id=1, queue_state="cancelled", runner_token="runner_1") is True

    control = store.control_snapshot("bg_control")
    assert control is not None
    assert control["queue_state"] == "cancelled"
    assert control["cancel_requested"] is False

def test_storage_requeues_stale_running_dispatch(tmp_path: Path) -> None:
    module = _import_storage_module()
    store = _build_store(module, tmp_path / "results")
    if store is None:
        pytest.skip("snapshot storage class not implemented yet")
    required_names = ("upsert_envelope", "claim_next_queued", "control_snapshot", "requeue_stale_running")
    if any(not hasattr(store, name) for name in required_names):
        pytest.skip("stale requeue APIs not found")

    from cli.agent_cli.background_tasks.models import BackgroundTaskType, TaskEnvelope

    envelope = TaskEnvelope(
        task_id="bg_stale_requeue",
        task_type=BackgroundTaskType.TEAMMATE,
        payload={"task": "do work"},
    )
    store.upsert_envelope(envelope)
    claimed = store.claim_next_queued(runner_token="runner_stale")
    assert claimed is not None
    assert claimed.task_id == "bg_stale_requeue"

    stale_timestamp = (datetime.now(timezone.utc) - timedelta(seconds=120)).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            """
            UPDATE background_task_dispatches
            SET updated_at = ?, runner_pid = 0
            WHERE task_id = ?
            """,
            (stale_timestamp, "bg_stale_requeue"),
        )
        conn.commit()

    recovered = store.requeue_stale_running(max_age_seconds=30)

    assert len(recovered) == 1
    assert recovered[0]["task_id"] == "bg_stale_requeue"
    assert recovered[0]["dispatch_id"] == 1
    assert recovered[0]["runner_token"] == "runner_stale"
    control = store.control_snapshot("bg_stale_requeue")
    assert control is not None
    assert control["queue_state"] == "queued"
    assert control["runner_token"] == ""

def test_storage_requeue_stale_running_is_idempotent_on_repeat_calls(tmp_path: Path) -> None:
    module = _import_storage_module()
    store = _build_store(module, tmp_path / "results")
    if store is None:
        pytest.skip("snapshot storage class not implemented yet")
    if any(not hasattr(store, name) for name in ("upsert_envelope", "claim_next_queued", "requeue_stale_running", "control_snapshot")):
        pytest.skip("stale requeue APIs not found")

    from cli.agent_cli.background_tasks.models import BackgroundTaskType, TaskEnvelope

    envelope = TaskEnvelope(
        task_id="bg_stale_requeue_idempotent",
        task_type=BackgroundTaskType.TEAMMATE,
    )
    store.upsert_envelope(envelope)
    claimed = store.claim_next_queued(runner_token="runner_stale_once")
    assert claimed is not None
    assert claimed.task_id == "bg_stale_requeue_idempotent"

    stale_timestamp = (datetime.now(timezone.utc) - timedelta(seconds=120)).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            """
            UPDATE background_task_dispatches
            SET updated_at = ?, runner_pid = 0
            WHERE task_id = ?
            """,
            (stale_timestamp, "bg_stale_requeue_idempotent"),
        )
        conn.commit()

    first_recover = store.requeue_stale_running(max_age_seconds=30)
    second_recover = store.requeue_stale_running(max_age_seconds=30)

    assert [item["task_id"] for item in first_recover] == ["bg_stale_requeue_idempotent"]
    assert second_recover == []
    control = store.control_snapshot("bg_stale_requeue_idempotent")
    assert control is not None
    assert control["queue_state"] == "queued"
    assert control["runner_token"] == ""


def test_storage_claim_next_queued_respects_tenant_and_workspace_scope(tmp_path: Path) -> None:
    module = _import_storage_module()
    store = _build_store(module, tmp_path / "results")
    if store is None:
        pytest.skip("snapshot storage class not implemented yet")
    if any(not hasattr(store, name) for name in ("upsert_envelope", "claim_next_queued", "control_snapshot")):
        pytest.skip("claim APIs not found")

    from cli.agent_cli.background_tasks.models import BackgroundTaskType, TaskEnvelope

    default_env = TaskEnvelope(
        task_id="bg_scope_default",
        task_type=BackgroundTaskType.SMOKE,
    )
    tenant_env = TaskEnvelope(
        task_id="bg_scope_tenant",
        task_type=BackgroundTaskType.SMOKE,
        tenant_id="tenant_a",
        workspace_scope="workspace_a",
    )
    store.upsert_envelope(default_env)
    store.upsert_envelope(tenant_env)

    claimed_default = store.claim_next_queued(runner_token="runner_default")
    assert claimed_default is not None
    assert claimed_default.task_id == "bg_scope_default"

    claimed_tenant = store.claim_next_queued(
        runner_token="runner_tenant",
        tenant_id="tenant_a",
        workspace_scope="workspace_a",
    )
    assert claimed_tenant is not None
    assert claimed_tenant.task_id == "bg_scope_tenant"

    default_control = store.control_snapshot("bg_scope_default")
    tenant_control = store.control_snapshot("bg_scope_tenant")
    assert default_control is not None
    assert tenant_control is not None
    assert default_control["tenant_id"] == "default"
    assert default_control["workspace_scope"] == "default"
    assert tenant_control["tenant_id"] == "tenant_a"
    assert tenant_control["workspace_scope"] == "workspace_a"


def test_storage_defaulting_normalizes_blank_scope_on_control_and_envelope(tmp_path: Path) -> None:
    module = _import_storage_module()
    store = _build_store(module, tmp_path / "results")
    if store is None:
        pytest.skip("snapshot storage class not implemented yet")
    if any(not hasattr(store, name) for name in ("upsert_envelope", "control_snapshot", "claim_next_queued")):
        pytest.skip("control/claim APIs not found")

    from cli.agent_cli.background_tasks.models import BackgroundTaskType, TaskEnvelope

    envelope = TaskEnvelope(
        task_id="bg_scope_blank_defaulting",
        task_type=BackgroundTaskType.SMOKE,
        tenant_id="   ",
        workspace_scope="",
    )
    store.upsert_envelope(envelope)

    control = store.control_snapshot("bg_scope_blank_defaulting")
    assert control is not None
    assert control["tenant_id"] == "default"
    assert control["workspace_scope"] == "default"
    assert control["envelope"]["tenant_id"] == "default"
    assert control["envelope"]["workspace_scope"] == "default"

    claimed = store.claim_next_queued(
        runner_token="runner_defaulting",
        tenant_id=" ",
        workspace_scope="  ",
    )
    assert claimed is not None
    assert claimed.task_id == "bg_scope_blank_defaulting"


def test_storage_requeue_stale_running_respects_tenant_scope_filter(tmp_path: Path) -> None:
    module = _import_storage_module()
    store = _build_store(module, tmp_path / "results")
    if store is None:
        pytest.skip("snapshot storage class not implemented yet")
    if any(not hasattr(store, name) for name in ("upsert_envelope", "claim_next_queued", "requeue_stale_running", "control_snapshot")):
        pytest.skip("stale requeue APIs not found")

    from cli.agent_cli.background_tasks.models import BackgroundTaskType, TaskEnvelope

    scoped = TaskEnvelope(
        task_id="bg_scope_requeue_tenant",
        task_type=BackgroundTaskType.TEAMMATE,
        tenant_id="tenant_a",
        workspace_scope="workspace_a",
    )
    default = TaskEnvelope(
        task_id="bg_scope_requeue_default",
        task_type=BackgroundTaskType.TEAMMATE,
    )
    store.upsert_envelope(scoped)
    store.upsert_envelope(default)

    assert store.claim_next_queued(
        runner_token="runner_tenant",
        tenant_id="tenant_a",
        workspace_scope="workspace_a",
    )
    assert store.claim_next_queued(runner_token="runner_default")

    stale_timestamp = (datetime.now(timezone.utc) - timedelta(seconds=120)).strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            """
            UPDATE background_task_dispatches
            SET updated_at = ?, runner_pid = 0
            WHERE task_id IN (?, ?)
            """,
            (stale_timestamp, "bg_scope_requeue_tenant", "bg_scope_requeue_default"),
        )
        conn.commit()

    recovered = store.requeue_stale_running(
        max_age_seconds=30,
        tenant_id="tenant_a",
        workspace_scope="workspace_a",
    )
    assert len(recovered) == 1
    assert recovered[0]["task_id"] == "bg_scope_requeue_tenant"
    assert recovered[0]["tenant_id"] == "tenant_a"
    assert recovered[0]["workspace_scope"] == "workspace_a"

    scoped_control = store.control_snapshot("bg_scope_requeue_tenant")
    default_control = store.control_snapshot("bg_scope_requeue_default")
    assert scoped_control is not None
    assert default_control is not None
    assert scoped_control["queue_state"] == "queued"
    assert default_control["queue_state"] == "running"


def test_storage_backend_contract_exposes_sqlite_first_interface(tmp_path: Path) -> None:
    module = _import_storage_module()
    store = _build_store(module, tmp_path / "results")
    if store is None:
        pytest.skip("snapshot storage class not implemented yet")
    required = ("storage_backend_contract", "storage_backend_capabilities", "storage_backend_label")
    if any(not hasattr(store, name) for name in required):
        pytest.skip("backend interface contract APIs not found")

    contract = store.storage_backend_contract()
    capabilities = store.storage_backend_capabilities()
    label = store.storage_backend_label()

    assert contract["contract_version"] == 1
    assert contract["backend_kind"] == "sqlite"
    assert contract["backend_interface"] == "sqlite_first"
    assert contract["backend_adapter"] == "builtin_sqlite_dispatch"
    assert contract["queue_source_of_truth"] == "dispatch"
    assert contract["default_backend"] is True
    assert contract["supports"]["tenant_scope_filtering"] is True
    assert contract["supports"]["stale_requeue"] is True
    assert contract["supports"]["claim_dispatch"] is True

    assert capabilities["backend_kind"] == "sqlite"
    assert capabilities["backend_interface"] == "sqlite_first"
    assert capabilities["backend_adapter"] == "builtin_sqlite_dispatch"
    assert capabilities["queue_source_of_truth"] == "dispatch"
    assert capabilities["default_backend"] is True
    assert capabilities["supports"]["tenant_scope_filtering"] is True

    assert label == "sqlite:builtin_sqlite_dispatch:v1"

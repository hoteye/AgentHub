from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .models import TaskEnvelope, TaskResult
from . import storage_runtime as storage_runtime_service

_STORAGE_BACKEND_CONTRACT_VERSION = 1
_STORAGE_BACKEND_KIND = "sqlite"
_STORAGE_BACKEND_INTERFACE = "sqlite_first"
_STORAGE_BACKEND_ADAPTER = "builtin_sqlite_dispatch"


def install_storage_bindings(storage_cls: type[Any]) -> None:
    def control_snapshot(self: Any, task_id: str) -> dict[str, Any] | None:
        control = self.get_control(task_id)
        if not isinstance(control, dict):
            return None
        envelope = control.get("envelope")
        payload = dict(control)
        payload["envelope"] = envelope.to_dict() if isinstance(envelope, TaskEnvelope) else None
        return payload

    def upsert_result(self: Any, result: TaskResult) -> None:
        self.ensure_ready()
        with self._lock:
            artifact_json = json.dumps(result.artifact, ensure_ascii=False)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO background_task_runs (
                      task_id, status, started_at, finished_at, summary, artifact_json, error, retry_count, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(task_id) DO UPDATE SET
                      status=excluded.status,
                      started_at=excluded.started_at,
                      finished_at=excluded.finished_at,
                      summary=excluded.summary,
                      artifact_json=excluded.artifact_json,
                      error=excluded.error,
                      retry_count=excluded.retry_count,
                      updated_at=CURRENT_TIMESTAMP
                    """,
                    (
                        result.task_id,
                        result.status.value,
                        result.started_at,
                        result.finished_at,
                        result.summary,
                        artifact_json,
                        result.error,
                        int(result.retry_count),
                    ),
                )
                conn.commit()

    def get_result(self: Any, task_id: str) -> TaskResult | None:
        self.ensure_ready()
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    """
                    SELECT task_id, status, started_at, finished_at, summary, artifact_json, error, retry_count
                    FROM background_task_runs
                    WHERE task_id = ?
                    """,
                    (task_id,),
                ).fetchone()
        if row is None:
            return None
        return storage_runtime_service.task_result_from_row(row)

    def list_recent(self: Any, *, limit: int = 50) -> list[TaskResult]:
        self.ensure_ready()
        bounded_limit = max(1, int(limit))
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT task_id, status, started_at, finished_at, summary, artifact_json, error, retry_count
                    FROM background_task_runs
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (bounded_limit,),
                ).fetchall()
        return [storage_runtime_service.task_result_from_row(row) for row in rows]

    def write_result_snapshot(
        self: Any, task_id: str, payload: dict[str, Any], *, suffix: str = "result"
    ) -> Path:
        self.ensure_ready()
        with self._lock:
            filename = storage_runtime_service.safe_snapshot_filename(task_id, suffix=suffix)
            path = self.results_dir / filename
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return path

    def upsert_snapshot(self: Any, snapshot: dict[str, Any] | TaskResult) -> TaskResult:
        result = snapshot if isinstance(snapshot, TaskResult) else TaskResult.from_dict(snapshot)
        self.upsert_result(result)
        self.write_result_snapshot(result.task_id, result.to_dict(), suffix="snapshot")
        return result

    def write_snapshot(self: Any, snapshot: dict[str, Any] | TaskResult) -> TaskResult:
        return self.upsert_snapshot(snapshot)

    def save_snapshot(self: Any, snapshot: dict[str, Any] | TaskResult) -> TaskResult:
        return self.upsert_snapshot(snapshot)

    def put_snapshot(self: Any, snapshot: dict[str, Any] | TaskResult) -> TaskResult:
        return self.upsert_snapshot(snapshot)

    def read_snapshot(self: Any, task_id: str) -> dict[str, Any] | None:
        result = self.get_result(task_id)
        return result.to_dict() if result is not None else None

    def load_snapshot(self: Any, task_id: str) -> dict[str, Any] | None:
        return self.read_snapshot(task_id)

    def get_snapshot(self: Any, task_id: str) -> dict[str, Any] | None:
        return self.read_snapshot(task_id)

    def requeue_stale_running(
        self: Any,
        *,
        max_age_seconds: float,
        tenant_id: str = "default",
        workspace_scope: str = "default",
    ) -> list[dict[str, Any]]:
        self.ensure_ready()
        bounded_age = max(1.0, float(max_age_seconds or 0.0))
        normalized_tenant = storage_runtime_service.normalize_scope_value(tenant_id)
        normalized_workspace = storage_runtime_service.normalize_scope_value(workspace_scope)
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=bounded_age)
        recovered: list[dict[str, Any]] = []
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT task_id, dispatch_id, task_type, runner_pid, runner_token, updated_at, tenant_id, workspace_scope
                    FROM background_task_dispatches
                    WHERE queue_state = 'running'
                      AND tenant_id = ?
                      AND workspace_scope = ?
                    ORDER BY updated_at ASC, created_at ASC, task_id ASC
                    """,
                    (normalized_tenant, normalized_workspace),
                ).fetchall()
                for row in rows:
                    task_id = str(row[0] or "").strip()
                    dispatch_id = storage_runtime_service.normalize_dispatch_id(row[1])
                    task_type = str(row[2] or "").strip()
                    runner_pid = storage_runtime_service.normalize_pid(row[3])
                    runner_token = storage_runtime_service.normalize_runner_token(row[4])
                    updated_at_raw = str(row[5] or "").strip()
                    row_tenant = storage_runtime_service.normalize_scope_value(row[6] if len(row) > 6 else "default")
                    row_workspace = storage_runtime_service.normalize_scope_value(row[7] if len(row) > 7 else "default")
                    updated_at = parse_dispatch_timestamp(updated_at_raw)
                    if updated_at is None or updated_at > cutoff:
                        continue
                    if runner_pid > 0 and pid_is_running(runner_pid):
                        continue
                    updated = conn.execute(
                        """
                        UPDATE background_task_dispatches
                        SET queue_state = 'queued',
                            cancel_requested = 0,
                            runner_pid = 0,
                            runner_token = '',
                            updated_at = CURRENT_TIMESTAMP
                        WHERE task_id = ?
                          AND dispatch_id = ?
                          AND queue_state = 'running'
                          AND runner_pid = ?
                          AND runner_token = ?
                          AND tenant_id = ?
                          AND workspace_scope = ?
                        """,
                        (
                            task_id,
                            dispatch_id,
                            runner_pid,
                            runner_token,
                            row_tenant,
                            row_workspace,
                        ),
                    )
                    if int(updated.rowcount or 0) != 1:
                        continue
                    conn.commit()
                    stale_age_seconds = max(
                        0.0,
                        round((datetime.now(timezone.utc) - updated_at).total_seconds(), 3),
                    )
                    recovered.append(
                        {
                            "task_id": task_id,
                            "dispatch_id": dispatch_id,
                            "task_type": task_type,
                            "runner_pid": runner_pid,
                            "runner_token": runner_token,
                            "updated_at": updated_at_raw,
                            "stale_age_seconds": stale_age_seconds,
                            "tenant_id": row_tenant,
                            "workspace_scope": row_workspace,
                        }
                    )
        return recovered

    def storage_backend_contract(self: Any) -> dict[str, Any]:
        return {
            "contract_version": _STORAGE_BACKEND_CONTRACT_VERSION,
            "backend_kind": _STORAGE_BACKEND_KIND,
            "backend_interface": _STORAGE_BACKEND_INTERFACE,
            "backend_adapter": _STORAGE_BACKEND_ADAPTER,
            "queue_source_of_truth": "dispatch",
            "default_backend": True,
            "supports": {
                "tenant_scope_filtering": True,
                "stale_requeue": True,
                "claim_dispatch": True,
            },
        }

    def storage_backend_capabilities(self: Any) -> dict[str, Any]:
        contract = storage_backend_contract(self)
        supports = contract.get("supports")
        normalized_supports = dict(supports) if isinstance(supports, dict) else {}
        return {
            "backend_kind": contract.get("backend_kind"),
            "backend_interface": contract.get("backend_interface"),
            "backend_adapter": contract.get("backend_adapter"),
            "queue_source_of_truth": contract.get("queue_source_of_truth"),
            "default_backend": bool(contract.get("default_backend")),
            "supports": normalized_supports,
        }

    def storage_backend_label(self: Any) -> str:
        contract = storage_backend_contract(self)
        return (
            f"{contract.get('backend_kind')}:"
            f"{contract.get('backend_adapter')}:"
            f"v{int(contract.get('contract_version') or 1)}"
        )

    storage_cls.control_snapshot = control_snapshot
    storage_cls.upsert_result = upsert_result
    storage_cls.get_result = get_result
    storage_cls.list_recent = list_recent
    storage_cls.write_result_snapshot = write_result_snapshot
    storage_cls.upsert_snapshot = upsert_snapshot
    storage_cls.write_snapshot = write_snapshot
    storage_cls.save_snapshot = save_snapshot
    storage_cls.put_snapshot = put_snapshot
    storage_cls.read_snapshot = read_snapshot
    storage_cls.load_snapshot = load_snapshot
    storage_cls.get_snapshot = get_snapshot
    storage_cls.requeue_stale_running = requeue_stale_running
    storage_cls.storage_backend_contract = storage_backend_contract
    storage_cls.storage_backend_capabilities = storage_backend_capabilities
    storage_cls.storage_backend_label = storage_backend_label
    storage_cls._decode_json_mapping = staticmethod(storage_runtime_service.decode_json_mapping)
    storage_cls._decode_envelope = staticmethod(storage_runtime_service.decode_envelope)


def parse_dispatch_timestamp(value: str) -> datetime | None:
    return storage_runtime_service.parse_dispatch_timestamp(value)


def pid_is_running(pid: int) -> bool:
    return storage_runtime_service.pid_is_running(pid)

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from .models import TaskEnvelope
from . import storage_binding_runtime as storage_binding_runtime_service
from . import storage_db_helpers as storage_db_helpers_service
from . import storage_runtime as storage_runtime_service
from . import storage_sql as storage_sql_service


_SCHEMA_SQL = storage_db_helpers_service.SCHEMA_SQL


@dataclass(slots=True)
class BackgroundTaskStorage:
    results_dir: Path
    db_path: Path | None = None
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

    def __post_init__(self) -> None:
        self.results_dir = Path(self.results_dir)
        self.db_path = Path(self.db_path) if self.db_path is not None else self.results_dir / "background_tasks.sqlite3"

    def ensure_ready(self) -> None:
        with self._lock:
            assert self.db_path is not None
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.results_dir.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                conn.executescript(_SCHEMA_SQL)
                self._ensure_dispatch_scope_columns(conn)
                conn.commit()

    @staticmethod
    def _ensure_dispatch_scope_columns(conn: sqlite3.Connection) -> None:
        storage_db_helpers_service.ensure_dispatch_scope_columns(conn)

    def upsert_envelope(
        self,
        envelope: TaskEnvelope,
        *,
        queue_state: str = "queued",
        cancel_requested: bool = False,
        runner_pid: int = 0,
        runner_token: str = "",
    ) -> None:
        self.ensure_ready()
        with self._lock:
            envelope_json = json.dumps(envelope.to_dict(), ensure_ascii=False)
            tenant_id = storage_runtime_service.normalize_scope_value(getattr(envelope, "tenant_id", "default"))
            workspace_scope = storage_runtime_service.normalize_scope_value(
                getattr(envelope, "workspace_scope", "default")
            )
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    storage_sql_service.UPSERT_ENVELOPE_SQL,
                    (
                        envelope.task_id,
                        envelope.task_type.value,
                        int(envelope.dispatch_id),
                        str(queue_state or "queued"),
                        tenant_id,
                        workspace_scope,
                        envelope_json,
                        1 if cancel_requested else 0,
                        max(0, int(runner_pid or 0)),
                        str(runner_token or ""),
                        str(envelope.created_at or ""),
                    ),
                )
                conn.commit()

    def get_envelope(self, task_id: str) -> Optional[TaskEnvelope]:
        control = self.get_control(task_id)
        if not isinstance(control, dict):
            return None
        raw_envelope = control.get("envelope")
        if isinstance(raw_envelope, TaskEnvelope):
            return raw_envelope
        return None

    def get_control(self, task_id: str) -> Dict[str, Any] | None:
        self.ensure_ready()
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                row = conn.execute(
                    storage_sql_service.SELECT_CONTROL_SQL,
                    (task_id,),
                ).fetchone()
        if row is None:
            return None
        return storage_runtime_service.control_from_row(row)

    def claim_next_queued(
        self,
        *,
        runner_token: str,
        tenant_id: str = "default",
        workspace_scope: str = "default",
    ) -> Optional[TaskEnvelope]:
        self.ensure_ready()
        token = storage_runtime_service.normalize_runner_token(runner_token)
        normalized_tenant = storage_runtime_service.normalize_scope_value(tenant_id)
        normalized_workspace = storage_runtime_service.normalize_scope_value(workspace_scope)
        if not token:
            return None
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    storage_sql_service.CLAIM_NEXT_CANDIDATES_SQL,
                    (normalized_tenant, normalized_workspace),
                ).fetchall()
                for row in rows:
                    updated = conn.execute(
                        storage_sql_service.CLAIM_QUEUED_SQL,
                        (
                            token,
                            str(row[0] or ""),
                            int(row[1] or 1),
                            normalized_tenant,
                            normalized_workspace,
                        ),
                    )
                    if int(updated.rowcount or 0) != 1:
                        continue
                    conn.commit()
                    return self._decode_envelope(row[2])
        return None

    def claim_dispatch(
        self,
        task_id: str,
        *,
        dispatch_id: int,
        runner_token: str,
        tenant_id: str = "default",
        workspace_scope: str = "default",
    ) -> bool:
        self.ensure_ready()
        normalized_task_id = storage_runtime_service.normalize_task_id(task_id)
        normalized_token = storage_runtime_service.normalize_runner_token(runner_token)
        normalized_tenant = storage_runtime_service.normalize_scope_value(tenant_id)
        normalized_workspace = storage_runtime_service.normalize_scope_value(workspace_scope)
        if not normalized_task_id or not normalized_token:
            return False
        normalized_dispatch_id = storage_runtime_service.normalize_dispatch_id(dispatch_id)
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                updated = conn.execute(
                    storage_sql_service.CLAIM_QUEUED_SQL,
                    (
                        normalized_token,
                        normalized_task_id,
                        normalized_dispatch_id,
                        normalized_tenant,
                        normalized_workspace,
                    ),
                )
                if int(updated.rowcount or 0) == 1:
                    conn.commit()
                    return True
                row = conn.execute(
                    storage_sql_service.SELECT_DISPATCH_STATE_SQL,
                    (normalized_task_id, normalized_tenant, normalized_workspace),
                ).fetchone()
        if row is None:
            return False
        return (
            int(row[0] or 1) == normalized_dispatch_id
            and str(row[1] or "") == "running"
            and str(row[2] or "") == normalized_token
        )

    def request_cancel(self, task_id: str) -> bool:
        self.ensure_ready()
        normalized_task_id = storage_runtime_service.normalize_task_id(task_id)
        if not normalized_task_id:
            return False
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                updated = conn.execute(
                    storage_sql_service.REQUEST_CANCEL_SQL,
                    (normalized_task_id,),
                )
                conn.commit()
                return int(updated.rowcount or 0) == 1

    def clear_cancel_request(self, task_id: str) -> None:
        self.ensure_ready()
        normalized_task_id = storage_runtime_service.normalize_task_id(task_id)
        if not normalized_task_id:
            return
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    storage_sql_service.CLEAR_CANCEL_SQL,
                    (normalized_task_id,),
                )
                conn.commit()

    def cancel_queued(self, task_id: str) -> bool:
        self.ensure_ready()
        normalized_task_id = storage_runtime_service.normalize_task_id(task_id)
        if not normalized_task_id:
            return False
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                updated = conn.execute(
                    storage_sql_service.CANCEL_QUEUED_SQL,
                    (normalized_task_id,),
                )
                conn.commit()
                return int(updated.rowcount or 0) == 1

    def is_cancel_requested(self, task_id: str, *, dispatch_id: int | None = None) -> bool:
        control = self.get_control(task_id)
        if not isinstance(control, dict):
            return False
        if dispatch_id is not None and int(control.get("dispatch_id") or 1) != max(1, int(dispatch_id or 1)):
            return False
        return bool(control.get("cancel_requested"))

    def set_runner_pid(self, task_id: str, *, dispatch_id: int, runner_token: str, pid: int) -> bool:
        self.ensure_ready()
        normalized_task_id = storage_runtime_service.normalize_task_id(task_id)
        normalized_token = storage_runtime_service.normalize_runner_token(runner_token)
        if not normalized_task_id or not normalized_token:
            return False
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                updated = conn.execute(
                    storage_sql_service.SET_RUNNER_PID_SQL,
                    (
                        storage_runtime_service.normalize_pid(pid),
                        normalized_task_id,
                        storage_runtime_service.normalize_dispatch_id(dispatch_id),
                        normalized_token,
                    ),
                )
                conn.commit()
                return int(updated.rowcount or 0) == 1

    def touch_dispatch(self, task_id: str, *, dispatch_id: int, runner_token: str) -> bool:
        self.ensure_ready()
        normalized_task_id = storage_runtime_service.normalize_task_id(task_id)
        normalized_token = storage_runtime_service.normalize_runner_token(runner_token)
        if not normalized_task_id or not normalized_token:
            return False
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                updated = conn.execute(
                    storage_sql_service.TOUCH_DISPATCH_SQL,
                    (
                        normalized_task_id,
                        storage_runtime_service.normalize_dispatch_id(dispatch_id),
                        normalized_token,
                    ),
                )
                conn.commit()
                return int(updated.rowcount or 0) == 1

    def complete_dispatch(
        self,
        task_id: str,
        *,
        dispatch_id: int,
        queue_state: str,
        runner_token: str = "",
    ) -> bool:
        self.ensure_ready()
        normalized_task_id = storage_runtime_service.normalize_task_id(task_id)
        if not normalized_task_id:
            return False
        normalized_queue_state = storage_runtime_service.normalize_queue_state(
            queue_state,
            default="completed",
        )
        normalized_dispatch_id = storage_runtime_service.normalize_dispatch_id(dispatch_id)
        normalized_token = storage_runtime_service.normalize_runner_token(runner_token)
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                query = storage_sql_service.COMPLETE_DISPATCH_SQL
                params: list[Any] = [
                    normalized_queue_state,
                    normalized_task_id,
                    normalized_dispatch_id,
                ]
                if normalized_token:
                    query += " AND runner_token = ?"
                    params.append(normalized_token)
                updated = conn.execute(query, tuple(params))
                conn.commit()
                return int(updated.rowcount or 0) == 1

    def requeue_stale_running(
        self,
        *,
        max_age_seconds: float,
        tenant_id: str = "default",
        workspace_scope: str = "default",
    ) -> list[dict[str, Any]]:
        self.ensure_ready()
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                return storage_db_helpers_service.requeue_stale_running(
                    conn,
                    max_age_seconds=max_age_seconds,
                    tenant_id=tenant_id,
                    workspace_scope=workspace_scope,
                )

_CUSTOM_REQUEUE_STALE_RUNNING = BackgroundTaskStorage.requeue_stale_running
storage_binding_runtime_service.install_storage_bindings(BackgroundTaskStorage)
BackgroundTaskStorage.requeue_stale_running = _CUSTOM_REQUEUE_STALE_RUNNING

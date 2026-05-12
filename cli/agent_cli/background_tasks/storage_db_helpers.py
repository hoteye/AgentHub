from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from . import storage_runtime as storage_runtime_service

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS background_task_runs (
  task_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  started_at TEXT NOT NULL DEFAULT '',
  finished_at TEXT NOT NULL DEFAULT '',
  summary TEXT NOT NULL DEFAULT '',
  artifact_json TEXT NOT NULL DEFAULT '{}',
  error TEXT NOT NULL DEFAULT '',
  retry_count INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS background_task_dispatches (
  task_id TEXT PRIMARY KEY,
  task_type TEXT NOT NULL DEFAULT '',
  dispatch_id INTEGER NOT NULL DEFAULT 1,
  queue_state TEXT NOT NULL DEFAULT 'queued',
  tenant_id TEXT NOT NULL DEFAULT 'default',
  workspace_scope TEXT NOT NULL DEFAULT 'default',
  envelope_json TEXT NOT NULL DEFAULT '{}',
  cancel_requested INTEGER NOT NULL DEFAULT 0,
  runner_pid INTEGER NOT NULL DEFAULT 0,
  runner_token TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_background_task_dispatches_state_updated
  ON background_task_dispatches(queue_state, updated_at);
"""


def ensure_dispatch_scope_columns(conn: sqlite3.Connection) -> None:
    rows = conn.execute("PRAGMA table_info(background_task_dispatches)").fetchall()
    known = {str(row[1] or "").strip() for row in rows}
    if "tenant_id" not in known:
        conn.execute(
            """
            ALTER TABLE background_task_dispatches
            ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default'
            """
        )
    if "workspace_scope" not in known:
        conn.execute(
            """
            ALTER TABLE background_task_dispatches
            ADD COLUMN workspace_scope TEXT NOT NULL DEFAULT 'default'
            """
        )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_background_task_dispatches_scope_state
        ON background_task_dispatches(tenant_id, workspace_scope, queue_state, updated_at)
        """
    )


def requeue_stale_running(
    conn: sqlite3.Connection,
    *,
    max_age_seconds: float,
    tenant_id: str = "default",
    workspace_scope: str = "default",
) -> list[dict[str, Any]]:
    bounded_age = max(1.0, float(max_age_seconds or 0.0))
    normalized_tenant = storage_runtime_service.normalize_scope_value(tenant_id)
    normalized_workspace = storage_runtime_service.normalize_scope_value(workspace_scope)
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=bounded_age)
    recovered: list[dict[str, Any]] = []
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
        updated_at = storage_runtime_service.parse_dispatch_timestamp(updated_at_raw)
        if updated_at is None or updated_at > cutoff:
            continue
        if runner_pid > 0 and storage_runtime_service.pid_is_running(runner_pid):
            continue
        # CAS-style reclaim guard: if heartbeat refreshes `updated_at` after scan, reclaim must fail.
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
              AND updated_at = ?
            """,
            (
                task_id,
                dispatch_id,
                runner_pid,
                runner_token,
                row_tenant,
                row_workspace,
                updated_at_raw,
            ),
        )
        if int(updated.rowcount or 0) != 1:
            continue
        conn.commit()
        stale_age_seconds = max(
            0.0,
            round(
                (
                    datetime.now(timezone.utc) - updated_at
                ).total_seconds(),
                3,
            ),
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

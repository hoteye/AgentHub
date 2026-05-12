from __future__ import annotations


UPSERT_ENVELOPE_SQL = """
INSERT INTO background_task_dispatches (
  task_id, task_type, dispatch_id, queue_state, tenant_id, workspace_scope, envelope_json,
  cancel_requested, runner_pid, runner_token, created_at, updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
ON CONFLICT(task_id) DO UPDATE SET
  task_type=excluded.task_type,
  dispatch_id=excluded.dispatch_id,
  queue_state=excluded.queue_state,
  tenant_id=excluded.tenant_id,
  workspace_scope=excluded.workspace_scope,
  envelope_json=excluded.envelope_json,
  cancel_requested=excluded.cancel_requested,
  runner_pid=excluded.runner_pid,
  runner_token=excluded.runner_token,
  created_at=excluded.created_at,
  updated_at=CURRENT_TIMESTAMP
"""

SELECT_CONTROL_SQL = """
SELECT task_id, task_type, dispatch_id, queue_state, envelope_json,
       cancel_requested, runner_pid, runner_token, created_at, updated_at,
       tenant_id, workspace_scope
FROM background_task_dispatches
WHERE task_id = ?
"""

CLAIM_NEXT_CANDIDATES_SQL = """
SELECT task_id, dispatch_id, envelope_json
FROM background_task_dispatches
WHERE queue_state = 'queued'
  AND tenant_id = ?
  AND workspace_scope = ?
ORDER BY updated_at ASC, created_at ASC, task_id ASC
LIMIT 32
"""

CLAIM_QUEUED_SQL = """
UPDATE background_task_dispatches
SET queue_state = 'running',
    runner_token = ?,
    runner_pid = 0,
    updated_at = CURRENT_TIMESTAMP
WHERE task_id = ?
  AND dispatch_id = ?
  AND queue_state = 'queued'
  AND tenant_id = ?
  AND workspace_scope = ?
"""

SELECT_DISPATCH_STATE_SQL = """
SELECT dispatch_id, queue_state, runner_token
FROM background_task_dispatches
WHERE task_id = ?
  AND tenant_id = ?
  AND workspace_scope = ?
"""

REQUEST_CANCEL_SQL = """
UPDATE background_task_dispatches
SET cancel_requested = 1,
    updated_at = CURRENT_TIMESTAMP
WHERE task_id = ?
"""

CLEAR_CANCEL_SQL = """
UPDATE background_task_dispatches
SET cancel_requested = 0,
    updated_at = CURRENT_TIMESTAMP
WHERE task_id = ?
"""

CANCEL_QUEUED_SQL = """
UPDATE background_task_dispatches
SET queue_state = 'cancelled',
    cancel_requested = 0,
    runner_pid = 0,
    runner_token = '',
    updated_at = CURRENT_TIMESTAMP
WHERE task_id = ?
  AND queue_state = 'queued'
"""

SET_RUNNER_PID_SQL = """
UPDATE background_task_dispatches
SET runner_pid = ?,
    updated_at = CURRENT_TIMESTAMP
WHERE task_id = ?
  AND dispatch_id = ?
  AND queue_state = 'running'
  AND runner_token = ?
"""

TOUCH_DISPATCH_SQL = """
UPDATE background_task_dispatches
SET updated_at = CURRENT_TIMESTAMP
WHERE task_id = ?
  AND dispatch_id = ?
  AND queue_state = 'running'
  AND runner_token = ?
"""

COMPLETE_DISPATCH_SQL = """
UPDATE background_task_dispatches
SET queue_state = ?,
    cancel_requested = 0,
    runner_pid = 0,
    runner_token = '',
    updated_at = CURRENT_TIMESTAMP
WHERE task_id = ?
  AND dispatch_id = ?
"""

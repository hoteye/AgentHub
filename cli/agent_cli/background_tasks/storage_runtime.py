from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict

from .models import TaskEnvelope, TaskResult

_STORAGE_BACKEND_KIND_SQLITE = "sqlite"
def normalize_task_id(task_id: str) -> str:
    return str(task_id or "").strip()


def normalize_runner_token(runner_token: str) -> str:
    return str(runner_token or "").strip()


def normalize_dispatch_id(dispatch_id: int) -> int:
    return max(1, int(dispatch_id or 1))


def normalize_scope_value(value: str, *, default: str = "default") -> str:
    text = str(value or "").strip()
    return text or default


def normalize_pid(pid: int) -> int:
    return max(0, int(pid or 0))


def normalize_queue_state(queue_state: str, *, default: str) -> str:
    return str(queue_state or default).strip() or default


def decode_json_mapping(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if not isinstance(raw, str):
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def decode_envelope(raw: Any) -> TaskEnvelope:
    def _normalize_envelope_scope(envelope: TaskEnvelope) -> TaskEnvelope:
        envelope.tenant_id = normalize_scope_value(getattr(envelope, "tenant_id", "default"))
        envelope.workspace_scope = normalize_scope_value(getattr(envelope, "workspace_scope", "default"))
        return envelope

    if isinstance(raw, TaskEnvelope):
        return _normalize_envelope_scope(raw)
    if isinstance(raw, dict):
        return _normalize_envelope_scope(TaskEnvelope.from_dict(raw))
    if not isinstance(raw, str):
        return _normalize_envelope_scope(TaskEnvelope.from_dict({}))
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {}
    return _normalize_envelope_scope(TaskEnvelope.from_dict(payload if isinstance(payload, dict) else {}))


def control_from_row(row: tuple[Any, ...]) -> Dict[str, Any]:
    tenant_id = normalize_scope_value(row[10] if len(row) > 10 else "default")
    workspace_scope = normalize_scope_value(row[11] if len(row) > 11 else "default")
    return {
        "task_id": row[0],
        "task_type": row[1],
        "dispatch_id": normalize_dispatch_id(row[2]),
        "queue_state": normalize_queue_state(row[3], default="queued"),
        "envelope": decode_envelope(row[4]),
        "cancel_requested": bool(row[5]),
        "runner_pid": normalize_pid(row[6]),
        "runner_token": str(row[7] or ""),
        "created_at": str(row[8] or ""),
        "updated_at": str(row[9] or ""),
        "tenant_id": tenant_id,
        "workspace_scope": workspace_scope,
    }


def task_result_from_row(row: tuple[Any, ...]) -> TaskResult:
    return TaskResult.from_dict(
        {
            "task_id": row[0],
            "status": row[1],
            "started_at": row[2],
            "finished_at": row[3],
            "summary": row[4],
            "artifact": decode_json_mapping(row[5]),
            "error": row[6],
            "retry_count": row[7],
        }
    )


def safe_snapshot_filename(task_id: str, *, suffix: str) -> str:
    safe_task_id = "".join(ch for ch in task_id if ch.isalnum() or ch in {"-", "_"})
    return f"{safe_task_id or 'task'}_{suffix}.json"


def parse_dispatch_timestamp(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for pattern in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(text, pattern)
        except ValueError:
            continue
        return parsed.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def pid_is_running(pid: int) -> bool:
    normalized_pid = normalize_pid(pid)
    if normalized_pid <= 0:
        return False
    try:
        os.kill(normalized_pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True

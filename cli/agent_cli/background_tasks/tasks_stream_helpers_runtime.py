from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def resolve_dispatch_runner_pid(
    storage: Any,
    *,
    envelope_task_id: str,
    stream_progress: dict[str, Any],
) -> int:
    cached_runner_pid = stream_progress.get("runner_pid")
    try:
        normalized_cached = max(0, int(cached_runner_pid or 0))
    except (TypeError, ValueError):
        normalized_cached = 0
    if normalized_cached > 0:
        return normalized_cached
    control = storage.get_control(envelope_task_id) if hasattr(storage, "get_control") else None
    if not isinstance(control, dict):
        return 0
    try:
        resolved_runner_pid = max(0, int(control.get("runner_pid") or 0))
    except (TypeError, ValueError):
        resolved_runner_pid = 0
    if resolved_runner_pid > 0:
        stream_progress["runner_pid"] = resolved_runner_pid
    return resolved_runner_pid


def resolve_running_log_path(
    *,
    stream_progress: dict[str, Any],
    key: str,
    storage: Any,
    task_id: str,
    log_kind: str,
) -> str:
    cached = str(stream_progress.get(key) or "").strip()
    if cached:
        return cached
    resolved = str(Path(storage.results_dir) / f"{task_id}_teammate_{log_kind}.log")
    stream_progress[key] = resolved
    return resolved


def running_snapshot_process_info(
    *,
    storage: Any,
    envelope_task_id: str,
    stream_progress: dict[str, Any],
    task_id: str,
) -> dict[str, Any]:
    runner_pid = resolve_dispatch_runner_pid(
        storage,
        envelope_task_id=envelope_task_id,
        stream_progress=stream_progress,
    )
    worker_pid = max(0, int(os.getpid() or 0))
    stdout_path = resolve_running_log_path(
        stream_progress=stream_progress,
        key="stdout_path",
        storage=storage,
        task_id=task_id,
        log_kind="stdout",
    )
    stderr_path = resolve_running_log_path(
        stream_progress=stream_progress,
        key="stderr_path",
        storage=storage,
        task_id=task_id,
        log_kind="stderr",
    )
    last_event_at = datetime.now(timezone.utc).isoformat()
    return {
        "runner_pid": runner_pid,
        "worker_pid": worker_pid,
        "stdout_path": stdout_path,
        "stderr_path": stderr_path,
        "last_event_at": last_event_at,
    }

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable

from .models import utc_now_iso
from .queue import huey_available

from . import worker_entry_state_runtime as worker_entry_state_runtime_service
from .worker_state import (
    current_worker_code_version,
    read_worker_state,
    write_worker_state,
)


def pid_is_running(pid: int) -> bool:
    normalized_pid = max(0, int(pid or 0))
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


def worker_state_indicates_stopped(adapter: Any) -> bool:
    latest = read_worker_state(adapter.config)
    status = str(latest.get("status") or "").strip().lower()
    return status in {"stopped", "exited"}


def write_stopped_worker_state(adapter: Any, *, state: dict[str, Any], reason: str) -> None:
    stopped_at = utc_now_iso()
    next_state = dict(state or {})
    next_state["status"] = "stopped"
    next_state["stopped_at"] = stopped_at
    next_state["last_heartbeat_at"] = stopped_at
    next_state["stop_reason"] = str(reason or "").strip()
    write_worker_state(adapter.config, next_state)


def preserve_active_loop_worker_state(adapter: Any) -> bool:
    state = read_worker_state(adapter.config)
    if str(state.get("mode") or "").strip().lower() != "loop":
        return False
    if str(state.get("status") or "").strip().lower() in {"", "stopped", "exited"}:
        return False
    worker_pid = int(state.get("worker_pid") or 0)
    return worker_pid > 0 and pid_is_running(worker_pid)


def run_worker_once_impl(
    *,
    adapter: Any,
    cwd: str | Path | None,
    max_jobs: int,
    stale_after_seconds: float,
    preserve_loop_state_fn: Callable[[Any], bool] | None = None,
) -> int:
    if preserve_loop_state_fn is None:
        preserve_loop_state = preserve_active_loop_worker_state(adapter)
    else:
        preserve_loop_state = bool(preserve_loop_state_fn(adapter))
    started_at = utc_now_iso()
    worker_code_version = current_worker_code_version()
    resolved_cwd = worker_entry_state_runtime_service.normalized_cwd(cwd)
    requested_jobs = worker_entry_state_runtime_service.normalized_requested_jobs(max_jobs)
    normalized_stale_after = worker_entry_state_runtime_service.normalized_stale_after_seconds(
        stale_after_seconds
    )
    recovered = list(adapter.cleanup_stale_tasks(max_age_seconds=normalized_stale_after) or [])
    base_state = worker_entry_state_runtime_service.base_state(
        mode="once",
        cwd=resolved_cwd,
        started_at=started_at,
        requested_jobs=requested_jobs,
        poll_interval=0.0,
        provider=adapter.config.provider,
        queue_provider=adapter.queue.provider_label,
        stale_after_seconds=normalized_stale_after,
        worker_code_version=worker_code_version,
    )
    base_state = worker_entry_state_runtime_service.once_running_state(
        worker_entry_state_runtime_service.with_recovered_tasks(
            base_state, recovered=recovered, at=started_at
        ),
        started_at=started_at,
    )
    if not preserve_loop_state:
        write_worker_state(adapter.config, base_state)
    processed = int(adapter.run_pending(max_jobs=requested_jobs, perform_maintenance=False) or 0)
    finished_at = utc_now_iso()
    final_state = worker_entry_state_runtime_service.once_final_state(
        base_state,
        finished_at=finished_at,
        processed=processed,
    )
    if not preserve_loop_state:
        write_worker_state(adapter.config, final_state)
    return processed


def run_worker_loop(
    *,
    adapter: Any,
    base_state: dict[str, Any],
    poll_interval: float,
    stale_after_seconds: float,
    requested_jobs: int,
) -> None:
    last_processed_count = 0
    last_processed_at = ""
    last_poll_at = base_state.get("started_at") or ""
    last_cleanup_count = 0
    last_cleanup_at = ""
    last_cleanup_task_ids: list[str] = []

    try:
        while True:
            recovered = list(adapter.cleanup_stale_tasks(max_age_seconds=stale_after_seconds) or [])
            processed = int(adapter.run_pending(max_jobs=requested_jobs, perform_maintenance=False) or 0)
            heartbeat_at = utc_now_iso()
            last_poll_at = heartbeat_at
            last_processed_count = processed
            if processed > 0:
                last_processed_at = heartbeat_at
            last_cleanup_count = len(recovered)
            if recovered:
                last_cleanup_at = heartbeat_at
                last_cleanup_task_ids = [
                    str(item.get("task_id") or "")
                    for item in recovered
                    if str(item.get("task_id") or "")
                ]
            write_worker_state(
                adapter.config,
                worker_entry_state_runtime_service.loop_iteration_state(
                    base_state,
                    heartbeat_at=heartbeat_at,
                    processed=processed,
                    last_processed_at=last_processed_at,
                    last_cleanup_count=last_cleanup_count,
                    last_cleanup_at=last_cleanup_at,
                    last_cleanup_task_ids=last_cleanup_task_ids,
                ),
            )
            if processed > 0:
                continue
            if not huey_available():
                time.sleep(poll_interval)
                continue
            time.sleep(poll_interval)
    finally:
        stopped_at = utc_now_iso()
        write_worker_state(
            adapter.config,
            worker_entry_state_runtime_service.loop_stopped_state(
                base_state,
                stopped_at=stopped_at,
                last_poll_at=last_poll_at,
                last_processed_count=last_processed_count,
                last_processed_at=last_processed_at,
                last_cleanup_count=last_cleanup_count,
                last_cleanup_at=last_cleanup_at,
                last_cleanup_task_ids=last_cleanup_task_ids,
            ),
        )

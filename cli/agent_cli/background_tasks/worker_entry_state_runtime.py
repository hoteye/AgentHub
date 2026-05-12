from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .queue import huey_available


def normalized_cwd(cwd: str | Path | None) -> str:
    return str(Path(cwd or os.getcwd()).expanduser().resolve())


def normalized_requested_jobs(max_jobs: int) -> int:
    return max(1, int(max_jobs))


def normalized_poll_interval(poll_interval: float) -> float:
    return max(0.1, float(poll_interval))


def normalized_stale_after_seconds(stale_after_seconds: float) -> float:
    return float(max(1.0, stale_after_seconds))


def base_state(
    *,
    mode: str,
    cwd: str,
    started_at: str,
    requested_jobs: int,
    poll_interval: float,
    provider: str,
    queue_provider: str,
    stale_after_seconds: float,
    worker_code_version: str,
) -> dict[str, Any]:
    return {
        "mode": mode,
        "worker_pid": os.getpid(),
        "cwd": cwd,
        "started_at": started_at,
        "max_jobs": requested_jobs,
        "poll_interval": poll_interval,
        "provider": provider,
        "queue_provider": queue_provider,
        "huey_available": bool(huey_available()),
        "stale_after_seconds": stale_after_seconds,
        "worker_code_version": worker_code_version,
    }


def with_recovered_tasks(state: dict[str, Any], *, recovered: list[dict[str, Any]], at: str) -> dict[str, Any]:
    next_state = dict(state)
    next_state["last_cleanup_count"] = len(recovered)
    if recovered:
        next_state["last_cleanup_at"] = at
        next_state["last_cleanup_task_ids"] = [
            str(item.get("task_id") or "")
            for item in recovered
            if str(item.get("task_id") or "")
        ]
    return next_state


def once_running_state(base: dict[str, Any], *, started_at: str) -> dict[str, Any]:
    state = dict(base)
    state.update(
        {
            "status": "running",
            "last_heartbeat_at": started_at,
            "last_poll_at": started_at,
            "last_processed_count": 0,
        }
    )
    return state


def once_final_state(base: dict[str, Any], *, finished_at: str, processed: int) -> dict[str, Any]:
    state = dict(base)
    state.update(
        {
            "status": "stopped",
            "last_heartbeat_at": finished_at,
            "last_poll_at": finished_at,
            "last_processed_count": processed,
            "stopped_at": finished_at,
        }
    )
    if processed > 0:
        state["last_processed_at"] = finished_at
    return state


def loop_starting_state(base: dict[str, Any], *, started_at: str) -> dict[str, Any]:
    state = dict(base)
    state.update(
        {
            "status": "starting",
            "last_heartbeat_at": started_at,
            "last_poll_at": started_at,
            "last_processed_count": 0,
            "last_cleanup_count": 0,
        }
    )
    return state


def loop_iteration_state(
    base: dict[str, Any],
    *,
    heartbeat_at: str,
    processed: int,
    last_processed_at: str,
    last_cleanup_count: int,
    last_cleanup_at: str,
    last_cleanup_task_ids: list[str],
) -> dict[str, Any]:
    state = dict(base)
    state.update(
        {
            "status": "idle",
            "last_heartbeat_at": heartbeat_at,
            "last_poll_at": heartbeat_at,
            "last_processed_count": processed,
            "last_processed_at": last_processed_at,
            "last_cleanup_count": last_cleanup_count,
            "last_cleanup_at": last_cleanup_at,
            "last_cleanup_task_ids": list(last_cleanup_task_ids),
        }
    )
    return state


def loop_stopped_state(
    base: dict[str, Any],
    *,
    stopped_at: str,
    last_poll_at: str,
    last_processed_count: int,
    last_processed_at: str,
    last_cleanup_count: int,
    last_cleanup_at: str,
    last_cleanup_task_ids: list[str],
) -> dict[str, Any]:
    state = dict(base)
    state.update(
        {
            "status": "stopped",
            "last_heartbeat_at": stopped_at,
            "last_poll_at": last_poll_at or stopped_at,
            "last_processed_count": last_processed_count,
            "last_processed_at": last_processed_at,
            "last_cleanup_count": last_cleanup_count,
            "last_cleanup_at": last_cleanup_at,
            "last_cleanup_task_ids": list(last_cleanup_task_ids),
            "stopped_at": stopped_at,
        }
    )
    return state

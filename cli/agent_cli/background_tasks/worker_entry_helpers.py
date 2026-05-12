from __future__ import annotations

import time
from typing import Any, Callable, Dict


def attempt_stop_worker(
    *,
    worker_pid: int,
    state: Dict[str, Any],
    state_path: str,
    force: bool,
    wait_timeout_seconds: float,
    pid_is_running_fn: Callable[[int], bool],
    worker_state_indicates_stopped_fn: Callable[[], bool],
    write_stopped_worker_state_fn: Callable[..., None],
    kill_fn: Callable[[int, int], None],
    sigterm: int,
    sigint: int,
    sigkill: int | None,
) -> Dict[str, Any]:
    forced = False
    try:
        kill_fn(worker_pid, sigterm if sigterm else sigint)
    except ProcessLookupError:
        write_stopped_worker_state_fn(state=state, reason="worker_not_running")
        return {
            "stopped": True,
            "reason": "worker_not_running",
            "worker_pid": worker_pid,
            "state_path": state_path,
        }
    except OSError as exc:
        write_stopped_worker_state_fn(state=state, reason=f"worker_stop_error:{type(exc).__name__}")
        return {
            "stopped": False,
            "reason": f"worker_stop_error:{type(exc).__name__}",
            "worker_pid": worker_pid,
            "state_path": state_path,
        }
    deadline = time.monotonic() + max(0.1, float(wait_timeout_seconds))
    while time.monotonic() < deadline:
        if not pid_is_running_fn(worker_pid):
            write_stopped_worker_state_fn(state=state, reason="worker_stopped")
            return {
                "stopped": True,
                "worker_pid": worker_pid,
                "forced": False,
                "state_path": state_path,
            }
        if worker_state_indicates_stopped_fn():
            return {
                "stopped": True,
                "reason": "worker_stopped_state",
                "worker_pid": worker_pid,
                "forced": False,
                "state_path": state_path,
            }
        time.sleep(0.1)
    if force and sigkill is not None and pid_is_running_fn(worker_pid):
        try:
            kill_fn(worker_pid, sigkill)
        except ProcessLookupError:
            write_stopped_worker_state_fn(state=state, reason="worker_not_running")
            return {
                "stopped": True,
                "reason": "worker_not_running",
                "worker_pid": worker_pid,
                "forced": True,
                "state_path": state_path,
            }
        forced = True
        deadline = time.monotonic() + max(0.1, float(wait_timeout_seconds))
        while time.monotonic() < deadline:
            if not pid_is_running_fn(worker_pid):
                write_stopped_worker_state_fn(state=state, reason="worker_killed")
                return {
                    "stopped": True,
                    "worker_pid": worker_pid,
                    "forced": forced,
                    "state_path": state_path,
                }
            if worker_state_indicates_stopped_fn():
                return {
                    "stopped": True,
                    "reason": "worker_stopped_state",
                    "worker_pid": worker_pid,
                    "forced": forced,
                    "state_path": state_path,
                }
            time.sleep(0.1)
    if worker_state_indicates_stopped_fn():
        return {
            "stopped": True,
            "reason": "worker_stopped_state",
            "worker_pid": worker_pid,
            "forced": forced,
            "state_path": state_path,
        }
    return {
        "stopped": False,
        "reason": "worker_stop_timeout",
        "worker_pid": worker_pid,
        "forced": forced,
        "state_path": state_path,
    }

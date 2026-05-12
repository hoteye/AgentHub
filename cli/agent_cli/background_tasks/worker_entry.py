from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

from .adapter import (
    DEFAULT_STALE_DISPATCH_AGE_SECONDS,
    build_background_task_adapter,
)
from .config import read_background_tasks_config
from .models import utc_now_iso
from .queue import huey_available
from . import worker_entry_state_runtime as worker_entry_state_runtime_service
from . import worker_entry_helpers as worker_entry_helpers_service
from .worker_entry_runner import (
    preserve_active_loop_worker_state,
    pid_is_running,
    run_worker_loop,
    run_worker_once_impl,
    write_stopped_worker_state,
    worker_state_indicates_stopped,
)
from .worker_state import (
    current_worker_code_signature_metadata,
    current_worker_code_version,
    read_worker_state,
    write_worker_state,
)


def _pid_is_running(pid: int) -> bool:
    return pid_is_running(pid)


def _worker_state_indicates_stopped(adapter: Any) -> bool:
    state = read_worker_state(adapter.config)
    status = str(state.get("status") or "").strip().lower()
    return status in {"stopped", "exited"}


def _write_stopped_worker_state(adapter: Any, *, state: dict[str, Any], reason: str) -> None:
    write_stopped_worker_state(adapter, state=state, reason=reason)


def _preserve_active_loop_worker_state(adapter: Any) -> bool:
    state = read_worker_state(adapter.config)
    if str(state.get("mode") or "").strip().lower() != "loop":
        return False
    if str(state.get("status") or "").strip().lower() in {"", "stopped", "exited"}:
        return False
    worker_pid = int(state.get("worker_pid") or 0)
    return worker_pid > 0 and _pid_is_running(worker_pid)


def resolve_worker_huey(*, cwd: str | Path | None = None) -> Any:
    adapter = build_background_task_adapter(cwd=cwd)
    return adapter.queue.huey_instance()


def start_worker_process(
    *,
    cwd: str | Path | None = None,
    max_jobs: int = 1,
    poll_interval: float = 1.0,
    stale_after_seconds: float = DEFAULT_STALE_DISPATCH_AGE_SECONDS,
) -> dict[str, Any]:
    adapter = build_background_task_adapter(cwd=cwd)
    status = adapter.worker_status() if hasattr(adapter, "worker_status") else {}
    current_code_version = current_worker_code_version()
    signature_meta = current_worker_code_signature_metadata()
    if not adapter.config.enabled:
        return {
            "started": False,
            "reason": "background_tasks_disabled",
            "state_path": str(adapter.config.huey.results_dir / "worker_state.json"),
        }
    if isinstance(status, dict) and str(status.get("health") or "").strip() == "healthy":
        worker_code_version = str(status.get("worker_code_version") or "").strip()
        started_at = str(status.get("started_at") or "").strip()
        worker_status = str(status.get("status") or "").strip()
        if worker_code_version and worker_code_version == current_code_version:
            return {
                "started": False,
                "reason": "worker_already_healthy",
                "worker_pid": int(status.get("worker_pid") or 0),
                "state_path": str(status.get("state_path") or ""),
                "worker_code_version": worker_code_version,
                "current_worker_code_version": current_code_version,
                "worker_code_version_match": True,
                "restart_required": False,
                "restart_reason": "",
                "worker_code_signature_algorithm": str(signature_meta["algorithm"]),
                "worker_code_signature_source": str(signature_meta["source"]),
                "worker_code_signature_file_count": int(signature_meta["file_count"]),
                "status": worker_status,
                "started_at": started_at,
            }
        return {
            "started": False,
            "reason": "worker_version_mismatch",
            "worker_pid": int(status.get("worker_pid") or 0),
            "state_path": str(status.get("state_path") or ""),
            "worker_code_version": worker_code_version,
            "current_worker_code_version": current_code_version,
            "worker_code_version_match": False,
            "restart_required": True,
            "restart_reason": "code_version_mismatch",
            "worker_code_signature_algorithm": str(signature_meta["algorithm"]),
            "worker_code_signature_source": str(signature_meta["source"]),
            "worker_code_signature_file_count": int(signature_meta["file_count"]),
            "status": worker_status,
            "started_at": started_at,
        }
    resolved_cwd = str(Path(cwd or os.getcwd()).expanduser().resolve())
    repo_root = Path(__file__).resolve().parents[3]
    stdout_path = adapter.config.huey.results_dir / "worker_stdout.log"
    stderr_path = adapter.config.huey.results_dir / "worker_stderr.log"
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    argv = [
        sys.executable,
        "-m",
        "cli.agent_cli.background_tasks.worker_entry",
        "--cwd",
        resolved_cwd,
        "--max-jobs",
        str(max(1, int(max_jobs))),
        "--poll-interval",
        str(max(0.1, float(poll_interval))),
        "--stale-after-seconds",
        str(max(1.0, float(stale_after_seconds))),
    ]
    popen_kwargs: dict[str, Any] = {
        "cwd": str(repo_root),
        "stdin": subprocess.DEVNULL,
        "text": True,
        "close_fds": True,
    }
    if os.name == "nt":
        creationflags = 0
        creationflags |= int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) or 0)
        creationflags |= int(getattr(subprocess, "DETACHED_PROCESS", 0) or 0)
        if creationflags:
            popen_kwargs["creationflags"] = creationflags
    else:
        popen_kwargs["start_new_session"] = True
    with stdout_path.open("a", encoding="utf-8") as stdout_handle, stderr_path.open("a", encoding="utf-8") as stderr_handle:
        process = subprocess.Popen(
            argv,
            stdout=stdout_handle,
            stderr=stderr_handle,
            **popen_kwargs,
        )
    return {
        "started": True,
        "worker_pid": int(getattr(process, "pid", 0) or 0),
        "command": argv,
        "cwd": resolved_cwd,
        "state_path": str(adapter.config.huey.results_dir / "worker_state.json"),
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
        "current_worker_code_version": current_code_version,
        "worker_code_signature_algorithm": str(signature_meta["algorithm"]),
        "worker_code_signature_source": str(signature_meta["source"]),
        "worker_code_signature_file_count": int(signature_meta["file_count"]),
    }


def stop_worker_process(
    *,
    cwd: str | Path | None = None,
    force: bool = False,
    wait_timeout_seconds: float = 3.0,
) -> dict[str, Any]:
    adapter = build_background_task_adapter(cwd=cwd)
    status = adapter.worker_status() if hasattr(adapter, "worker_status") else {}
    state = read_worker_state(adapter.config)
    state_path = str((status.get("state_path") if isinstance(status, dict) else "") or adapter.config.huey.results_dir / "worker_state.json")
    worker_pid = int(
        (status.get("worker_pid") if isinstance(status, dict) else 0)
        or state.get("worker_pid")
        or 0
    )
    if worker_pid <= 0:
        return {
            "stopped": False,
            "reason": "worker_pid_missing",
            "state_path": state_path,
        }
    if not _pid_is_running(worker_pid):
        _write_stopped_worker_state(adapter, state=state, reason="worker_not_running")
        return {
            "stopped": True,
            "reason": "worker_not_running",
            "worker_pid": worker_pid,
            "state_path": state_path,
        }
    return worker_entry_helpers_service.attempt_stop_worker(
        worker_pid=worker_pid,
        state=state,
        state_path=state_path,
        force=force,
        wait_timeout_seconds=wait_timeout_seconds,
        pid_is_running_fn=_pid_is_running,
        worker_state_indicates_stopped_fn=lambda: _worker_state_indicates_stopped(adapter),
        write_stopped_worker_state_fn=lambda *, state, reason: _write_stopped_worker_state(
            adapter,
            state=state,
            reason=reason,
        ),
        kill_fn=os.kill,
        sigterm=getattr(signal, "SIGTERM", signal.SIGINT),
        sigint=signal.SIGINT,
        sigkill=getattr(signal, "SIGKILL", None),
    )


def run_worker_once(
    *,
    cwd: str | Path | None = None,
    max_jobs: int = 1,
    stale_after_seconds: float = DEFAULT_STALE_DISPATCH_AGE_SECONDS,
) -> int:
    adapter = build_background_task_adapter(cwd=cwd)
    return run_worker_once_impl(
        adapter=adapter,
        cwd=cwd,
        max_jobs=max_jobs,
        stale_after_seconds=stale_after_seconds,
        preserve_loop_state_fn=_preserve_active_loop_worker_state,
    )


def run_worker(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AgentHub background task worker entry")
    parser.add_argument("--cwd", default="", help="Optional cwd for config discovery")
    parser.add_argument("--once", action="store_true", help="Run local pending queue once")
    parser.add_argument("--max-jobs", type=int, default=1, help="Max jobs for --once mode")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Polling interval in seconds for long-running mode")
    parser.add_argument(
        "--stale-after-seconds",
        type=float,
        default=DEFAULT_STALE_DISPATCH_AGE_SECONDS,
        help="Requeue running tasks whose dispatch heartbeat is stale for at least this many seconds",
    )
    args = parser.parse_args(argv)

    config = read_background_tasks_config(cwd=args.cwd or None)
    if not config.enabled:
        return 0
    if args.once:
        run_worker_once(
            cwd=args.cwd or None,
            max_jobs=worker_entry_state_runtime_service.normalized_requested_jobs(args.max_jobs),
            stale_after_seconds=worker_entry_state_runtime_service.normalized_stale_after_seconds(
                float(args.stale_after_seconds)
            ),
        )
        return 0
    adapter = build_background_task_adapter(cwd=args.cwd or None)
    poll_interval = worker_entry_state_runtime_service.normalized_poll_interval(
        float(args.poll_interval)
    )
    stale_after_seconds = worker_entry_state_runtime_service.normalized_stale_after_seconds(
        float(args.stale_after_seconds)
    )
    started_at = utc_now_iso()
    worker_code_version = current_worker_code_version()
    resolved_cwd = worker_entry_state_runtime_service.normalized_cwd(args.cwd or None)
    requested_jobs = worker_entry_state_runtime_service.normalized_requested_jobs(args.max_jobs)
    base_state = worker_entry_state_runtime_service.base_state(
        mode="loop",
        cwd=resolved_cwd,
        started_at=started_at,
        requested_jobs=requested_jobs,
        poll_interval=poll_interval,
        provider=adapter.config.provider,
        queue_provider=adapter.queue.provider_label,
        stale_after_seconds=stale_after_seconds,
        worker_code_version=worker_code_version,
    )
    write_worker_state(
        adapter.config,
        worker_entry_state_runtime_service.loop_starting_state(base_state, started_at=started_at),
    )
    run_worker_loop(
        adapter=adapter,
        base_state=base_state,
        poll_interval=poll_interval,
        stale_after_seconds=stale_after_seconds,
        requested_jobs=requested_jobs,
    )


def main() -> int:
    return run_worker()


if __name__ == "__main__":
    raise SystemExit(main())

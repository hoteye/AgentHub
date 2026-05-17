from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from cli.agent_cli.providers.auth_refresh_daemon_process_state_runtime import (
    _STATE_VERSION,
    _as_str,
    _load_contexts_file,
    _read_json_dict,
    _safe_int,
    _write_contexts_file,
    _write_json_atomic,
    daemon_contexts_path_for_store,
    daemon_state_path_for_store,
)
from cli.agent_cli.providers.auth_refresh_scheduler_runtime import (
    RefreshProviderContext,
    refresh_due_sessions,
)
from cli.agent_cli.providers.auth_token_store_runtime import FileAuthTokenStore
from cli.agent_cli.providers.oauth_device_flow_runtime import refresh_oauth_token


def _module_parent_for_subprocess() -> Path:
    # The worker is launched with `python -m cli...`; source checkouts need the
    # repository root, not the cli/ working directory, on sys.path.
    return Path(__file__).resolve().parents[3]


def _pid_is_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except Exception:
        return False
    proc_stat_path = Path(f"/proc/{pid}/stat")
    if proc_stat_path.exists():
        try:
            stat_parts = proc_stat_path.read_text(encoding="utf-8").split()
        except Exception:
            stat_parts = []
        if len(stat_parts) > 2 and str(stat_parts[2]).strip().upper() == "Z":
            return False
    return True


def managed_refresh_daemon_status(
    *,
    store_path: Path,
) -> dict[str, Any]:
    state_path = daemon_state_path_for_store(store_path=store_path)
    state = _read_json_dict(state_path)
    pid = _safe_int(state.get("pid"), 0)
    running = _pid_is_running(pid)
    interval_seconds = max(1, _safe_int(state.get("interval_seconds"), 60))
    now_ts = float(time.time())
    heartbeat = float(state.get("last_heartbeat_at") or 0.0)
    heartbeat_age_seconds = (now_ts - heartbeat) if heartbeat > 0 else None
    healthy = bool(
        running
        and heartbeat_age_seconds is not None
        and heartbeat_age_seconds <= max(30.0, float(interval_seconds * 3))
    )
    summary = dict(state.get("last_summary") or {})
    alert_level = "ok" if healthy else ("warning" if running else "error")
    alert_reason = ""
    if running and not healthy:
        alert_reason = "heartbeat_stale"
    elif not running and pid > 0:
        alert_reason = "process_not_running"
    elif _as_str(state.get("last_error")):
        alert_reason = "last_error_present"
    return {
        "status": "running" if running else "stopped",
        "daemon_mode": "managed",
        "daemon_status": "running" if running else "stopped",
        "running": running,
        "healthy": healthy,
        "alert_level": alert_level,
        "alert_reason": alert_reason,
        "pid": pid,
        "state_path": str(state_path),
        "contexts_path": str(daemon_contexts_path_for_store(store_path=store_path)),
        "interval_seconds": interval_seconds,
        "refresh_window_seconds": max(0, _safe_int(state.get("refresh_window_seconds"), 300)),
        "started_at": float(state.get("started_at") or 0.0) or None,
        "last_heartbeat_at": heartbeat or None,
        "last_run_at": float(state.get("last_run_at") or 0.0) or None,
        "heartbeat_age_seconds": (
            int(heartbeat_age_seconds) if heartbeat_age_seconds is not None else None
        ),
        "loop_count": max(0, _safe_int(state.get("loop_count"), 0)),
        "last_error": _as_str(state.get("last_error")),
        "summary_status": _as_str(summary.get("status")),
        "contexts": max(0, _safe_int(summary.get("contexts"), 0)),
        "refreshed": max(0, _safe_int(summary.get("refreshed"), 0)),
        "skipped": max(0, _safe_int(summary.get("skipped"), 0)),
        "failed": max(0, _safe_int(summary.get("failed"), 0)),
    }


def start_managed_refresh_daemon(
    *,
    store_path: Path,
    contexts: list[RefreshProviderContext],
    interval_seconds: int = 60,
    refresh_window_seconds: int = 300,
    python_executable: str | None = None,
) -> dict[str, Any]:
    existing = managed_refresh_daemon_status(store_path=store_path)
    if bool(existing.get("running")):
        return {"result": "already_running", **existing}
    interval_value = max(1, int(interval_seconds or 60))
    refresh_window_value = max(0, int(refresh_window_seconds or 300))
    state_path = daemon_state_path_for_store(store_path=store_path)
    contexts_path = daemon_contexts_path_for_store(store_path=store_path)
    _write_contexts_file(contexts_path=contexts_path, contexts=contexts)

    command = [
        str(python_executable or sys.executable),
        "-m",
        "cli.agent_cli.providers.auth_refresh_daemon_process_runtime",
        "--run-worker",
        "--store-path",
        str(store_path),
        "--state-path",
        str(state_path),
        "--contexts-path",
        str(contexts_path),
        "--interval-seconds",
        str(interval_value),
        "--refresh-window-seconds",
        str(refresh_window_value),
    ]
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(_module_parent_for_subprocess()),
        start_new_session=True,
        close_fds=True,
    )
    bootstrap_state = {
        "version": _STATE_VERSION,
        "pid": int(process.pid),
        "interval_seconds": interval_value,
        "refresh_window_seconds": refresh_window_value,
        "started_at": float(time.time()),
        "last_heartbeat_at": None,
        "last_run_at": None,
        "loop_count": 0,
        "last_error": "",
        "last_summary": {
            "status": "ok",
            "contexts": len(contexts),
            "refreshed": 0,
            "skipped": 0,
            "failed": 0,
        },
    }
    _write_json_atomic(state_path, bootstrap_state)
    time.sleep(0.1)
    snapshot = managed_refresh_daemon_status(store_path=store_path)
    return {"result": "started", **snapshot}


def stop_managed_refresh_daemon(
    *,
    store_path: Path,
    timeout_seconds: float = 3.0,
    force: bool = False,
) -> dict[str, Any]:
    state_path = daemon_state_path_for_store(store_path=store_path)
    state = _read_json_dict(state_path)
    pid = _safe_int(state.get("pid"), 0)
    if not _pid_is_running(pid):
        snapshot = managed_refresh_daemon_status(store_path=store_path)
        return {"result": "already_stopped", **snapshot}
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception:
        pass
    deadline = time.time() + max(0.5, float(timeout_seconds or 3.0))
    while time.time() < deadline and _pid_is_running(pid):
        time.sleep(0.05)
    if _pid_is_running(pid) and force:
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
        hard_deadline = time.time() + max(0.5, float(timeout_seconds or 3.0))
        while time.time() < hard_deadline and _pid_is_running(pid):
            time.sleep(0.05)
    snapshot = managed_refresh_daemon_status(store_path=store_path)
    if not bool(snapshot.get("running")):
        final_state = _read_json_dict(state_path)
        final_state["stopped_at"] = float(time.time())
        _write_json_atomic(state_path, final_state)
        return {"result": "stopped", **snapshot}
    return {"result": "stop_timeout", **snapshot}


def run_managed_refresh_daemon_worker(
    *,
    store_path: Path,
    state_path: Path,
    contexts_path: Path,
    interval_seconds: int,
    refresh_window_seconds: int,
) -> int:
    stop_event = threading.Event()

    def _handle_signal(_signum: int, _frame: Any) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    interval_value = max(1, int(interval_seconds or 60))
    refresh_window_value = max(0, int(refresh_window_seconds or 300))
    store = FileAuthTokenStore(store_path=store_path)
    started_at = float(time.time())
    loop_count = 0
    while not stop_event.is_set():
        now_ts = float(time.time())
        contexts = _load_contexts_file(contexts_path=contexts_path)
        error_text = ""
        try:
            summary = refresh_due_sessions(
                store=store,
                contexts=contexts,
                now_ts=now_ts,
                refresh_window_seconds=refresh_window_value,
                refresh_fn=refresh_oauth_token,
            )
        except Exception as exc:
            error_text = str(exc)
            summary = {
                "status": "error",
                "contexts": 0,
                "refreshed": 0,
                "skipped": 0,
                "failed": 0,
                "results": [],
                "error_code": "managed_refresh_daemon_iteration_failed",
            }
        loop_count += 1
        _write_json_atomic(
            state_path,
            {
                "version": _STATE_VERSION,
                "pid": os.getpid(),
                "interval_seconds": interval_value,
                "refresh_window_seconds": refresh_window_value,
                "started_at": started_at,
                "last_heartbeat_at": now_ts,
                "last_run_at": now_ts,
                "loop_count": loop_count,
                "last_error": error_text,
                "last_summary": dict(summary or {}),
            },
        )
        if stop_event.wait(interval_value):
            break
    _write_json_atomic(
        state_path,
        {
            "version": _STATE_VERSION,
            "pid": os.getpid(),
            "interval_seconds": interval_value,
            "refresh_window_seconds": refresh_window_value,
            "started_at": started_at,
            "last_heartbeat_at": float(time.time()),
            "last_run_at": float(time.time()),
            "loop_count": loop_count,
            "last_error": "",
            "last_summary": {
                "status": "stopped",
                "contexts": 0,
                "refreshed": 0,
                "skipped": 0,
                "failed": 0,
            },
            "stopped_at": float(time.time()),
        },
    )
    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Managed auth refresh daemon worker/runtime")
    parser.add_argument("--run-worker", action="store_true", help="Run daemon worker loop")
    parser.add_argument("--store-path", required=True, help="Path to auth.json token store")
    parser.add_argument("--state-path", required=True, help="Path to daemon state JSON")
    parser.add_argument("--contexts-path", required=True, help="Path to daemon contexts JSON")
    parser.add_argument("--interval-seconds", type=int, default=60)
    parser.add_argument("--refresh-window-seconds", type=int, default=300)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    if not bool(args.run_worker):
        return 2
    return run_managed_refresh_daemon_worker(
        store_path=Path(str(args.store_path)).resolve(),
        state_path=Path(str(args.state_path)).resolve(),
        contexts_path=Path(str(args.contexts_path)).resolve(),
        interval_seconds=max(1, int(args.interval_seconds or 60)),
        refresh_window_seconds=max(0, int(args.refresh_window_seconds or 300)),
    )


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import sys
import time
from pathlib import Path

from cli.agent_cli.providers.auth_refresh_daemon_process_runtime import (
    managed_refresh_daemon_status,
    start_managed_refresh_daemon,
    stop_managed_refresh_daemon,
)


def test_managed_refresh_daemon_start_status_stop(tmp_path: Path) -> None:
    store_path = tmp_path / "auth.json"
    start = start_managed_refresh_daemon(
        store_path=store_path,
        contexts=[],
        interval_seconds=1,
        refresh_window_seconds=300,
        python_executable=sys.executable,
    )
    assert start["result"] in {"started", "already_running"}

    status = managed_refresh_daemon_status(store_path=store_path)
    deadline = time.time() + 5.0
    while (not bool(status.get("running")) or int(status.get("loop_count") or 0) == 0) and time.time() < deadline:
        time.sleep(0.1)
        status = managed_refresh_daemon_status(store_path=store_path)
    assert status["daemon_mode"] == "managed"
    assert status["running"] is True
    assert int(status.get("loop_count") or 0) >= 1

    stop = stop_managed_refresh_daemon(
        store_path=store_path,
        timeout_seconds=5.0,
        force=True,
    )
    assert stop["result"] in {"stopped", "already_stopped"}
    final = managed_refresh_daemon_status(store_path=store_path)
    assert final["running"] is False

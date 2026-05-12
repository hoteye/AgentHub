from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .models import TaskEnvelope
from .storage import BackgroundTaskStorage

_DISPATCH_HEARTBEAT_INTERVAL_SECONDS = 1.0


@dataclass(slots=True)
class SubprocessRunResult:
    returncode: int
    command: list[str]
    stdout: str = ""
    stderr: str = ""
    cancelled: bool = False
    timed_out: bool = False
    timeout_seconds: float | None = None
    cwd: str = ""
    stdout_path: Path | None = None
    stderr_path: Path | None = None


@dataclass(slots=True)
class BenchmarkRunResult:
    returncode: int
    command: list[str]
    report_path: Path
    stdout: str = ""
    stderr: str = ""
    cancelled: bool = False
    timed_out: bool = False
    timeout_seconds: float | None = None
    cwd: str = ""
    stdout_path: Path | None = None
    stderr_path: Path | None = None


def run_logged_subprocess(
    envelope: TaskEnvelope,
    *,
    command: list[str],
    cwd: Path,
    storage: BackgroundTaskStorage | None,
    runner_token: str,
    log_prefix: str,
    env: dict[str, str] | None = None,
    timeout_seconds: float | None = None,
    stdout_line_callback: Callable[[str], None] | None = None,
    stderr_line_callback: Callable[[str], None] | None = None,
    heartbeat_callback: Callable[[], None] | None = None,
) -> SubprocessRunResult:
    resolved_cwd = Path(cwd).expanduser().resolve()
    normalized_timeout_seconds = float(timeout_seconds) if timeout_seconds is not None and float(timeout_seconds) > 0 else None
    stdout_path = None
    stderr_path = None
    if storage is not None:
        stdout_path = storage.results_dir / f"{envelope.task_id}_{log_prefix}_stdout.log"
        stderr_path = storage.results_dir / f"{envelope.task_id}_{log_prefix}_stderr.log"
        stdout_path.parent.mkdir(parents=True, exist_ok=True)
        stderr_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        resolved_tmp = Path.cwd()
        stdout_path = resolved_tmp / f"{envelope.task_id}_{log_prefix}_stdout.log"
        stderr_path = resolved_tmp / f"{envelope.task_id}_{log_prefix}_stderr.log"

    with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open("w", encoding="utf-8") as stderr_handle:
        process = subprocess.Popen(
            list(command or []),
            cwd=str(resolved_cwd),
            env=env,
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
        )
        if storage is not None:
            storage.set_runner_pid(
                envelope.task_id,
                dispatch_id=envelope.dispatch_id,
                runner_token=runner_token,
                pid=int(getattr(process, "pid", 0) or 0),
            )
            storage.touch_dispatch(
                envelope.task_id,
                dispatch_id=envelope.dispatch_id,
                runner_token=runner_token,
            )
        cancelled = False
        timed_out = False
        last_heartbeat_at = time.monotonic()
        started_monotonic = time.monotonic()
        stdout_offset = 0
        stderr_offset = 0
        stdout_pending = ""
        stderr_pending = ""
        while True:
            returncode = process.poll()
            stdout_offset, stdout_pending = _pump_log_lines(
                stdout_path,
                offset=stdout_offset,
                pending=stdout_pending,
                line_callback=stdout_line_callback,
            )
            stderr_offset, stderr_pending = _pump_log_lines(
                stderr_path,
                offset=stderr_offset,
                pending=stderr_pending,
                line_callback=stderr_line_callback,
            )
            if returncode is not None:
                break
            if storage is not None and (time.monotonic() - last_heartbeat_at) >= _DISPATCH_HEARTBEAT_INTERVAL_SECONDS:
                storage.touch_dispatch(
                    envelope.task_id,
                    dispatch_id=envelope.dispatch_id,
                    runner_token=runner_token,
                )
                if callable(heartbeat_callback):
                    heartbeat_callback()
                last_heartbeat_at = time.monotonic()
            if normalized_timeout_seconds is not None and (time.monotonic() - started_monotonic) >= normalized_timeout_seconds:
                timed_out = True
                terminate_process(process)
                break
            if storage is not None and storage.is_cancel_requested(envelope.task_id, dispatch_id=envelope.dispatch_id):
                cancelled = True
                terminate_process(process)
                break
            time.sleep(0.2)
        if process.poll() is None:
            process.wait(timeout=5.0)
        returncode = int(process.returncode or 0)
        _pump_log_lines(
            stdout_path,
            offset=stdout_offset,
            pending=stdout_pending,
            line_callback=stdout_line_callback,
            flush_pending=True,
        )
        _pump_log_lines(
            stderr_path,
            offset=stderr_offset,
            pending=stderr_pending,
            line_callback=stderr_line_callback,
            flush_pending=True,
        )

    stdout_text = stdout_path.read_text(encoding="utf-8") if stdout_path.exists() else ""
    stderr_text = stderr_path.read_text(encoding="utf-8") if stderr_path.exists() else ""
    return SubprocessRunResult(
        returncode=returncode,
        command=list(command or []),
        stdout=stdout_text,
        stderr=stderr_text,
        cancelled=cancelled,
        timed_out=timed_out,
        timeout_seconds=normalized_timeout_seconds,
        cwd=str(resolved_cwd),
        stdout_path=stdout_path,
        stderr_path=stderr_path,
    )


def terminate_process(process: subprocess.Popen[str]) -> None:
    try:
        process.terminate()
        process.wait(timeout=3.0)
        return
    except Exception:
        pass
    try:
        process.kill()
        process.wait(timeout=3.0)
    except Exception:
        pass


def _pump_log_lines(
    path: Path,
    *,
    offset: int,
    pending: str,
    line_callback: Callable[[str], None] | None,
    flush_pending: bool = False,
) -> tuple[int, str]:
    text = pending
    next_offset = offset
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            handle.seek(offset)
            chunk = handle.read()
            next_offset = handle.tell()
        if chunk:
            text += chunk
    if not text:
        return next_offset, ""
    if not callable(line_callback):
        return next_offset, ""
    lines = text.splitlines(keepends=True)
    next_pending = ""
    if not flush_pending and lines and not lines[-1].endswith(("\n", "\r")):
        next_pending = lines.pop()
    for line in lines:
        line_callback(line.rstrip("\r\n"))
    if flush_pending and next_pending:
        line_callback(next_pending)
        next_pending = ""
    return next_offset, next_pending

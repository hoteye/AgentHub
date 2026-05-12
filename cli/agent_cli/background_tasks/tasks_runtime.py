from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .models import BackgroundTaskStatus, TaskResult


def subprocess_outcome(
    run: Any,
    *,
    success_summary: str,
    failure_summary: str,
    cancelled_summary: str,
    timed_out_summary: str,
    timeout_error_text_fn: Callable[[str, float | None], str],
    trim_error_fn: Callable[[str], str],
    timeout_label: str,
) -> tuple[BackgroundTaskStatus, str, str]:
    if run.cancelled:
        return (BackgroundTaskStatus.CANCELLED, cancelled_summary, "")
    if run.timed_out:
        return (
            BackgroundTaskStatus.FAILED,
            timed_out_summary,
            timeout_error_text_fn(timeout_label, run.timeout_seconds),
        )
    if run.returncode == 0:
        return (BackgroundTaskStatus.COMPLETED, success_summary, "")
    return (
        BackgroundTaskStatus.FAILED,
        failure_summary,
        trim_error_fn(run.stderr or run.stdout or f"{timeout_label} exited {run.returncode}"),
    )


def subprocess_snapshot_payload(
    *,
    envelope: Any,
    status: BackgroundTaskStatus,
    command: list[str],
    returncode: int,
    report_path: Path,
    stdout: str,
    stderr: str,
    cancelled: bool,
    timed_out: bool,
    timeout_seconds: float | None,
    terminal_state: str,
    progress_payload: dict[str, Any],
    extra: dict[str, Any] | None = None,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
) -> dict[str, Any]:
    payload = {
        "task": envelope.to_dict(),
        "status": status.value,
        "command": command,
        "returncode": returncode,
        "report_path": str(report_path),
        "stdout": stdout,
        "stderr": stderr,
        "cancelled": cancelled,
        "timed_out": timed_out,
        "timeout_seconds": timeout_seconds,
        "terminal_state": terminal_state,
        **progress_payload,
    }
    if extra:
        payload.update(extra)
    if stdout_path is not None:
        payload["stdout_path"] = str(stdout_path)
    if stderr_path is not None:
        payload["stderr_path"] = str(stderr_path)
    return payload


def subprocess_artifact_payload(
    *,
    report_path: Path,
    snapshot_path: Path,
    timed_out: bool,
    timeout_seconds: float | None,
    terminal_state: str,
    subprocess_artifact: dict[str, Any],
    extra: dict[str, Any] | None = None,
    stdout_path: Path | None = None,
    stderr_path: Path | None = None,
) -> dict[str, Any]:
    payload = {
        "report_path": str(report_path),
        "snapshot_path": str(snapshot_path),
        "timed_out": timed_out,
        "timeout_seconds": timeout_seconds,
        "terminal_state": terminal_state,
        **subprocess_artifact,
    }
    if extra:
        payload.update(extra)
    if stdout_path is not None:
        payload["stdout_path"] = str(stdout_path)
    if stderr_path is not None:
        payload["stderr_path"] = str(stderr_path)
    return payload


def subprocess_task_result(
    *,
    task_id: str,
    status: BackgroundTaskStatus,
    started_at: str,
    finished_at: str,
    summary: str,
    artifact: dict[str, Any],
    error: str,
    retry_count: int,
) -> TaskResult:
    return TaskResult(
        task_id=task_id,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        summary=summary,
        artifact=artifact,
        error=error,
        retry_count=retry_count,
    )

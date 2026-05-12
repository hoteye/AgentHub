from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .models import BackgroundTaskStatus, TaskResult


def enrich_snapshot_payload(
    *,
    snapshot_payload: dict[str, Any],
    response_payload: dict[str, Any] | None,
    protocol_diagnostics: dict[str, Any],
    response_status: dict[str, Any],
    route_report: dict[str, Any],
    stage_cwd: Path | None,
    review_path: str,
    run_stdout_path: Path | None,
    run_stderr_path: Path | None,
    running_snapshot_metadata: dict[str, Any],
) -> dict[str, Any]:
    updated = dict(snapshot_payload)
    if isinstance(response_payload, dict):
        updated["headless_response"] = response_payload
    if protocol_diagnostics:
        updated["protocol_diagnostics"] = protocol_diagnostics
    if response_status:
        updated["response_status"] = response_status
    if route_report:
        updated["route_report"] = route_report
    if stage_cwd is not None:
        updated["stage_cwd"] = str(stage_cwd)
    if review_path:
        updated["review_path"] = review_path
    if run_stdout_path is not None:
        updated["stdout_path"] = str(run_stdout_path)
    if run_stderr_path is not None:
        updated["stderr_path"] = str(run_stderr_path)
    updated.update(running_snapshot_metadata)
    return updated


def enrich_artifact(
    *,
    artifact: dict[str, Any],
    response_payload: dict[str, Any] | None,
    assistant_text: str,
    commentary_preview_text: str,
    stage_cwd: Path | None,
    review_path: str,
    run_stdout_path: Path | None,
    run_stderr_path: Path | None,
    trim_error_fn: Callable[..., str],
) -> dict[str, Any]:
    updated = dict(artifact)
    if stage_cwd is not None:
        updated["stage_cwd"] = str(stage_cwd)
    if review_path:
        updated["review_path"] = review_path
    if isinstance(response_payload, dict):
        thread_id = str(response_payload.get("thread_id") or "").strip()
        if thread_id:
            updated["thread_id"] = thread_id
        if assistant_text:
            updated["assistant_text_preview"] = trim_error_fn(assistant_text, max_chars=160)
        if commentary_preview_text:
            updated["commentary_text_preview"] = trim_error_fn(commentary_preview_text, max_chars=160)
    if run_stdout_path is not None:
        updated["stdout_path"] = str(run_stdout_path)
    if run_stderr_path is not None:
        updated["stderr_path"] = str(run_stderr_path)
    return updated


def staged_result(
    *,
    current: TaskResult,
    artifact: dict[str, Any],
    status: BackgroundTaskStatus,
    finished_at: str,
    summary: str,
    error: str,
) -> TaskResult:
    return TaskResult(
        task_id=current.task_id,
        status=status,
        started_at=current.started_at,
        finished_at=finished_at,
        summary=summary,
        artifact=artifact,
        error=error,
        retry_count=int(current.retry_count or 0),
    )

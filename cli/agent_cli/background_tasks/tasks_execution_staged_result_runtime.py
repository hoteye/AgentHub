from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from . import tasks_execution_result_runtime
from . import tasks_execution_teammate_result_runtime as teammate_result_runtime
from .models import BackgroundTaskStatus, TaskResult

_TEAMMATE_RUNNING_SNAPSHOT_SUFFIX = "teammate_running"


def teammate_running_snapshot_path(*, results_dir: Path, task_id: str) -> Path:
    return Path(results_dir) / f"{task_id}_{_TEAMMATE_RUNNING_SNAPSHOT_SUFFIX}.json"


def teammate_running_snapshot_metadata(*, results_dir: Path, task_id: str) -> dict[str, Any]:
    snapshot_path = teammate_running_snapshot_path(results_dir=results_dir, task_id=task_id)
    if not snapshot_path.exists():
        return {}
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    metadata: dict[str, Any] = {"running_snapshot_path": str(snapshot_path)}
    for key in ("runner_pid", "worker_pid", "last_event_at", "stdout_path", "stderr_path"):
        value = payload.get(key)
        if value not in (None, ""):
            metadata[key] = value
    return metadata


def build_staged_apply_blocked_result(
    *,
    current: TaskResult,
    artifact: dict[str, Any],
    out_of_scope_files: list[str],
    task_id: str,
    utc_now_iso_fn: Callable[[], str],
    trim_error_fn: Callable[..., str],
) -> TaskResult:
    tasks_execution_result_runtime.staged_result_artifact(
        artifact=artifact,
        final_apply_state="blocked",
        final_apply_pending=False,
        review_commands=[f"/background_task_reject {task_id}"],
        finished_at=utc_now_iso_fn(),
        out_of_scope_files=out_of_scope_files,
    )
    finished_at = str(artifact.get("final_apply_decided_at") or utc_now_iso_fn())
    return teammate_result_runtime.staged_result(
        current=current,
        artifact=artifact,
        status=BackgroundTaskStatus.FAILED,
        finished_at=finished_at,
        summary="background teammate apply blocked by path policy",
        error=trim_error_fn("out-of-scope staged changes: " + ", ".join(out_of_scope_files[:8]), max_chars=320),
    )


def build_staged_apply_completed_result(
    *,
    current: TaskResult,
    artifact: dict[str, Any],
    modified_files: list[str],
    applied_at: str,
) -> TaskResult:
    tasks_execution_result_runtime.staged_result_artifact(
        artifact=artifact,
        final_apply_state="applied",
        final_apply_pending=False,
        review_commands=[],
        finished_at=applied_at,
        applied_files=modified_files,
    )
    return teammate_result_runtime.staged_result(
        current=current,
        artifact=artifact,
        status=BackgroundTaskStatus.COMPLETED,
        finished_at=applied_at,
        summary="background teammate changes applied to live workspace",
        error="",
    )


def build_staged_reject_result(
    *,
    current: TaskResult,
    artifact: dict[str, Any],
    rejected_at: str,
) -> TaskResult:
    tasks_execution_result_runtime.staged_result_artifact(
        artifact=artifact,
        final_apply_state="rejected",
        final_apply_pending=False,
        review_commands=[],
        finished_at=rejected_at,
    )
    return teammate_result_runtime.staged_result(
        current=current,
        artifact=artifact,
        status=current.status,
        finished_at=rejected_at,
        summary="background teammate staged changes rejected",
        error=current.error,
    )

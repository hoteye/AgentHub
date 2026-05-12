from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable

from .models import BackgroundTaskStatus, TaskResult


def build_subprocess_task_result(
    *,
    envelope: Any,
    storage: Any,
    run: Any,
    started_at: str,
    retry_count: int,
    status: BackgroundTaskStatus,
    summary: str,
    error_text: str,
    title: str,
    goal: str,
    snapshot_suffix: str,
    report_path: Path,
    terminal_state: str,
    extra_snapshot: dict[str, Any] | None = None,
    extra_artifact: dict[str, Any] | None = None,
    subprocess_progress_payload_fn: Callable[..., dict[str, Any]],
    subprocess_snapshot_payload_fn: Callable[..., dict[str, Any]],
    subprocess_artifact_payload_fn: Callable[..., dict[str, Any]],
    subprocess_artifact_fn: Callable[[dict[str, Any]], dict[str, Any]],
    task_artifact_fn: Callable[..., dict[str, Any]],
    subprocess_task_result_fn: Callable[..., TaskResult],
    utc_now_iso_fn: Callable[[], str],
) -> TaskResult:
    finished_at = utc_now_iso_fn()
    progress_payload = subprocess_progress_payload_fn(
        title=title,
        goal=goal,
        command=run.command,
        returncode=run.returncode,
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        summary=summary,
        error=error_text,
    )
    snapshot_payload = subprocess_snapshot_payload_fn(
        envelope=envelope,
        status=status,
        command=run.command,
        returncode=run.returncode,
        report_path=report_path,
        stdout=run.stdout,
        stderr=run.stderr,
        cancelled=bool(run.cancelled),
        timed_out=bool(run.timed_out),
        timeout_seconds=run.timeout_seconds,
        terminal_state=terminal_state,
        progress_payload=progress_payload,
        extra=extra_snapshot,
        stdout_path=run.stdout_path,
        stderr_path=run.stderr_path,
    )
    snapshot_path = storage.write_result_snapshot(envelope.task_id, snapshot_payload, suffix=snapshot_suffix)
    artifact = task_artifact_fn(
        envelope,
        queue_state=status.value,
        cancel_requested=False,
        extra=subprocess_artifact_payload_fn(
            report_path=report_path,
            snapshot_path=snapshot_path,
            timed_out=bool(run.timed_out),
            timeout_seconds=run.timeout_seconds,
            terminal_state=terminal_state,
            subprocess_artifact=subprocess_artifact_fn(progress_payload),
            extra=extra_artifact,
            stdout_path=run.stdout_path,
            stderr_path=run.stderr_path,
        ),
    )
    return subprocess_task_result_fn(
        task_id=envelope.task_id,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        summary=summary,
        artifact=artifact,
        error=error_text,
        retry_count=retry_count,
    )


def staged_review_state(
    *,
    task_id: str,
    artifact: dict[str, Any],
    review_payload: dict[str, Any],
    live_cwd: Path,
    normalize_policy_path_fn: Callable[[Path, Any], str],
    parse_path_list_fn: Callable[[Any], list[str]],
    dedupe_compact_items_fn: Callable[..., list[str]],
    paths_outside_policy_fn: Callable[..., list[str]],
) -> dict[str, Any]:
    allowed_paths = dedupe_compact_items_fn(
        [
            normalize_policy_path_fn(live_cwd, item)
            for item in parse_path_list_fn(review_payload.get("allowed_paths") or artifact.get("allowed_paths"))
            if normalize_policy_path_fn(live_cwd, item)
        ],
        limit=32,
    )
    blocked_paths = dedupe_compact_items_fn(
        [
            normalize_policy_path_fn(live_cwd, item)
            for item in parse_path_list_fn(review_payload.get("blocked_paths") or artifact.get("blocked_paths"))
            if normalize_policy_path_fn(live_cwd, item)
        ],
        limit=32,
    )
    modified_files = dedupe_compact_items_fn(
        [str(item.get("path") or "").strip() for item in list(review_payload.get("changes") or []) if isinstance(item, dict)],
        limit=64,
    )
    out_of_scope_files = paths_outside_policy_fn(
        modified_files,
        allowed_paths=allowed_paths,
        blocked_paths=blocked_paths,
    )
    return {
        "allowed_paths": allowed_paths,
        "blocked_paths": blocked_paths,
        "modified_files": modified_files,
        "out_of_scope_files": out_of_scope_files,
    }


def apply_staged_changes(
    *,
    review_payload: dict[str, Any],
    live_cwd: Path,
    stage_cwd: Path,
    normalize_policy_path_fn: Callable[[Path, Any], str],
) -> None:
    for change in list(review_payload.get("changes") or []):
        if not isinstance(change, dict):
            continue
        relative_path = normalize_policy_path_fn(live_cwd, change.get("path"))
        if not relative_path or relative_path == ".":
            continue
        live_path = live_cwd / relative_path
        stage_path = stage_cwd / relative_path
        change_type = str(change.get("change_type") or "").strip()
        if change_type == "delete":
            if live_path.exists():
                live_path.unlink()
            continue
        if not stage_path.exists():
            raise FileNotFoundError(f"staged file missing: {stage_path}")
        live_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(stage_path, live_path)


def updated_review_payload(
    review_payload: dict[str, Any],
    *,
    final_apply_pending: bool,
    final_apply_state: str,
    review_commands: list[str],
    out_of_scope_files: list[str] | None = None,
    applied_files: list[str] | None = None,
    final_apply_decided_at: str | None = None,
) -> dict[str, Any]:
    updated = dict(review_payload)
    updated["final_apply_pending"] = final_apply_pending
    updated["final_apply_state"] = final_apply_state
    updated["review_commands"] = list(review_commands)
    if out_of_scope_files is not None:
        updated["out_of_scope_files"] = list(out_of_scope_files)
    if applied_files is not None:
        updated["applied_files"] = list(applied_files)
    if final_apply_decided_at is not None:
        updated["final_apply_decided_at"] = final_apply_decided_at
    return updated

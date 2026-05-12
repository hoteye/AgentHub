from __future__ import annotations

from pathlib import Path
from typing import Any

from . import tasks_facade_runtime
from . import tasks_support_runtime
from .models import BackgroundTaskStatus, TaskEnvelope, TaskResult
from .storage import BackgroundTaskStorage


def background_terminal_state(
    *,
    status: BackgroundTaskStatus,
    cancelled: bool = False,
    timed_out: bool = False,
) -> str:
    return tasks_facade_runtime.background_terminal_state(status=status, cancelled=cancelled, timed_out=timed_out)


def paths_outside_policy(
    paths: list[str],
    *,
    allowed_paths: list[str],
    blocked_paths: list[str],
) -> list[str]:
    return tasks_facade_runtime.paths_outside_policy(
        paths,
        allowed_paths=allowed_paths,
        blocked_paths=blocked_paths,
    )


def prepare_stage_workspace(
    task_id: str,
    *,
    source_root: Path,
    storage: BackgroundTaskStorage,
) -> Path:
    return tasks_facade_runtime.prepare_stage_workspace(task_id, source_root=source_root, storage=storage)


def diff_preview(
    *,
    relative_path: str,
    before_path: Path | None,
    after_path: Path | None,
) -> tuple[bool, str]:
    return tasks_support_runtime.diff_preview(
        relative_path=relative_path,
        before_path=before_path,
        after_path=after_path,
    )


def collect_workspace_changes(source_root: Path, stage_root: Path) -> list[dict[str, Any]]:
    return tasks_facade_runtime.collect_workspace_changes(source_root, stage_root)


def teammate_review_commands(task_id: str, *, blocked: bool) -> list[str]:
    return tasks_facade_runtime.teammate_review_commands(task_id, blocked=blocked)


def worker_heartbeat_callback(
    *,
    storage: BackgroundTaskStorage,
    envelope: TaskEnvelope,
    on_heartbeat_callback: Any = None,
) -> Any:
    return tasks_facade_runtime.worker_heartbeat_callback(
        storage=storage,
        envelope=envelope,
        on_heartbeat_callback=on_heartbeat_callback,
    )


def consume_teammate_stdout_line(
    line: str,
    *,
    state: dict[str, Any],
    storage: BackgroundTaskStorage,
    envelope: TaskEnvelope,
    started_at: str,
    retry_count: int,
    live_cwd: Path,
    provider: str,
    model: str,
    reasoning_effort: str,
    allowed_paths: list[str],
    blocked_paths: list[str],
    staged_workspace: bool,
    bootstrap_artifact: dict[str, Any],
    stream_progress: dict[str, Any],
) -> None:
    tasks_facade_runtime.consume_teammate_stdout_line(
        line,
        state=state,
        storage=storage,
        envelope=envelope,
        started_at=started_at,
        retry_count=retry_count,
        live_cwd=live_cwd,
        provider=provider,
        model=model,
        reasoning_effort=reasoning_effort,
        allowed_paths=allowed_paths,
        blocked_paths=blocked_paths,
        staged_workspace=staged_workspace,
        bootstrap_artifact=bootstrap_artifact,
        stream_progress=stream_progress,
    )


def ensure_teammate_running_snapshot(
    *,
    state: dict[str, Any],
    storage: BackgroundTaskStorage,
    envelope: TaskEnvelope,
    started_at: str,
    retry_count: int,
    live_cwd: Path,
    provider: str,
    model: str,
    reasoning_effort: str,
    allowed_paths: list[str],
    blocked_paths: list[str],
    staged_workspace: bool,
    bootstrap_artifact: dict[str, Any],
    stream_progress: dict[str, Any],
) -> None:
    tasks_facade_runtime.ensure_teammate_running_snapshot(
        state=state,
        storage=storage,
        envelope=envelope,
        started_at=started_at,
        retry_count=retry_count,
        live_cwd=live_cwd,
        provider=provider,
        model=model,
        reasoning_effort=reasoning_effort,
        allowed_paths=allowed_paths,
        blocked_paths=blocked_paths,
        staged_workspace=staged_workspace,
        bootstrap_artifact=bootstrap_artifact,
        stream_progress=stream_progress,
    )


def apply_staged_teammate_result(task_id: str, *, storage: BackgroundTaskStorage) -> TaskResult | None:
    return tasks_facade_runtime.apply_staged_teammate_result(task_id, storage=storage)


def reject_staged_teammate_result(task_id: str, *, storage: BackgroundTaskStorage) -> TaskResult | None:
    return tasks_facade_runtime.reject_staged_teammate_result(task_id, storage=storage)

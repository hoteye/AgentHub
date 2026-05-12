from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from . import tasks_execution_result_runtime
from . import tasks_execution_staged_result_runtime as tasks_execution_staged_result_runtime_service
from . import tasks_execution_teammate_build_runtime as tasks_execution_teammate_build_runtime_service
from . import tasks_execution_teammate_result_runtime as teammate_result_runtime
from .models import BackgroundTaskStatus, TaskResult

def teammate_running_snapshot_path(*, results_dir: Path, task_id: str) -> Path:
    return tasks_execution_staged_result_runtime_service.teammate_running_snapshot_path(
        results_dir=results_dir,
        task_id=task_id,
    )


def teammate_running_snapshot_metadata(*, results_dir: Path, task_id: str) -> dict[str, Any]:
    return tasks_execution_staged_result_runtime_service.teammate_running_snapshot_metadata(
        results_dir=results_dir,
        task_id=task_id,
    )


def build_benchmark_run_request(
    *,
    payload: dict[str, Any],
    benchmark_script_path: Path,
    report_path: Path,
    python_executable: str,
    normalize_argv_fn: Callable[[Any], list[str]],
    task_timeout_seconds_fn: Callable[[dict[str, Any]], float | None],
) -> dict[str, Any]:
    argv = normalize_argv_fn(payload.get("argv"))
    command = [python_executable, str(benchmark_script_path), *argv]
    if "--json" not in argv:
        command.append("--json")
    if "--out" not in argv:
        command.extend(["--out", str(report_path)])
    return {
        "argv": argv,
        "command": command,
        "timeout_seconds": task_timeout_seconds_fn(payload),
    }


def build_smoke_run_request(
    *,
    payload: dict[str, Any],
    cli_root: Path,
    smoke_kind_scripts: dict[str, Path],
    report_path: Path,
    python_executable: str,
    normalize_smoke_kind_fn: Callable[[dict[str, Any]], str],
    normalize_argv_fn: Callable[[Any], list[str]],
    task_timeout_seconds_fn: Callable[[dict[str, Any]], float | None],
) -> dict[str, Any]:
    kind = normalize_smoke_kind_fn(payload)
    script_path = smoke_kind_scripts.get(kind)
    if script_path is None:
        raise ValueError(f"unsupported smoke kind: {kind or '-'}")
    argv = normalize_argv_fn(payload.get("argv"))
    command = [python_executable, str(script_path), *argv]
    if "--out" not in argv:
        command.extend(["--out", str(report_path)])
    return {
        "kind": kind,
        "script_path": script_path,
        "argv": argv,
        "command": command,
        "cwd": Path(str(payload.get("cwd") or cli_root)),
        "timeout_seconds": task_timeout_seconds_fn(payload),
    }


def normalize_teammate_request(
    *,
    payload: dict[str, Any],
    metadata: Any,
    workspace_root: Path,
    parse_path_list_fn: Callable[[Any], list[str]],
    dedupe_compact_items_fn: Callable[..., list[str]],
    normalize_policy_path_fn: Callable[[Path, Any], str],
    task_timeout_seconds_fn: Callable[[dict[str, Any]], float | None],
) -> dict[str, Any]:
    task_text = str(payload.get("task") or payload.get("prompt") or "").strip()
    live_cwd = Path(str(payload.get("cwd") or workspace_root)).expanduser().resolve()
    provider = str(payload.get("provider") or getattr(metadata, "provider_name", "") or "").strip()
    model = str(payload.get("model") or getattr(metadata, "model", "") or "").strip()
    metadata_extra = getattr(metadata, "extra", {}) or {}
    reasoning_effort = str(payload.get("reasoning_effort") or metadata_extra.get("reasoning_effort") or "").strip()
    sandbox_mode = str(payload.get("sandbox_mode") or "read-only").strip() or "read-only"
    raw_allowed_paths = parse_path_list_fn(payload.get("allowed_paths"))
    raw_blocked_paths = parse_path_list_fn(payload.get("blocked_paths"))
    if sandbox_mode == "workspace-write" and not raw_allowed_paths:
        raw_allowed_paths = ["."]
    if sandbox_mode == "workspace-write" and not raw_blocked_paths:
        raw_blocked_paths = [".git"]
    allowed_paths = dedupe_compact_items_fn(
        [normalize_policy_path_fn(live_cwd, item) for item in raw_allowed_paths if normalize_policy_path_fn(live_cwd, item)],
        limit=32,
    )
    blocked_paths = dedupe_compact_items_fn(
        [normalize_policy_path_fn(live_cwd, item) for item in raw_blocked_paths if normalize_policy_path_fn(live_cwd, item)],
        limit=32,
    )
    return {
        "task_text": task_text,
        "live_cwd": live_cwd,
        "provider": provider,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "sandbox_mode": sandbox_mode,
        "allowed_paths": allowed_paths,
        "blocked_paths": blocked_paths,
        "timeout_seconds": task_timeout_seconds_fn(payload),
        "staged_workspace": sandbox_mode == "workspace-write",
    }


build_teammate_bootstrap_failure_result = (
    tasks_execution_teammate_build_runtime_service.build_teammate_bootstrap_failure_result
)


build_teammate_task_result = tasks_execution_teammate_build_runtime_service.build_teammate_task_result


def build_staged_apply_blocked_result(
    *,
    current: TaskResult,
    artifact: dict[str, Any],
    out_of_scope_files: list[str],
    task_id: str,
    utc_now_iso_fn: Callable[[], str],
    trim_error_fn: Callable[..., str],
) -> TaskResult:
    return tasks_execution_staged_result_runtime_service.build_staged_apply_blocked_result(
        current=current,
        artifact=artifact,
        out_of_scope_files=out_of_scope_files,
        task_id=task_id,
        utc_now_iso_fn=utc_now_iso_fn,
        trim_error_fn=trim_error_fn,
    )


def build_staged_apply_completed_result(
    *,
    current: TaskResult,
    artifact: dict[str, Any],
    modified_files: list[str],
    applied_at: str,
) -> TaskResult:
    return tasks_execution_staged_result_runtime_service.build_staged_apply_completed_result(
        current=current,
        artifact=artifact,
        modified_files=modified_files,
        applied_at=applied_at,
    )


def build_staged_reject_result(
    *,
    current: TaskResult,
    artifact: dict[str, Any],
    rejected_at: str,
) -> TaskResult:
    return tasks_execution_staged_result_runtime_service.build_staged_reject_result(
        current=current,
        artifact=artifact,
        rejected_at=rejected_at,
    )

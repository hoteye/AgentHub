from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import BackgroundTaskStatus


def bootstrap_snapshot_payload(
    *,
    envelope: Any,
    status: BackgroundTaskStatus,
    task_text: str,
    live_cwd: Path,
    allowed_paths: list[str],
    blocked_paths: list[str],
    staged_workspace: bool,
    timeout_seconds: float | None,
    bootstrap_artifact: dict[str, Any],
    progress_payload: dict[str, Any],
    terminal_state: str,
) -> dict[str, Any]:
    return {
        "task": envelope.to_dict(),
        "status": status.value,
        "task_text": task_text,
        "command": [],
        "returncode": 2,
        "response_path": "",
        "stdout": "",
        "stderr": "",
        "cancelled": False,
        "live_cwd": str(live_cwd),
        "allowed_paths": allowed_paths,
        "blocked_paths": blocked_paths,
        "staged_workspace": staged_workspace,
        "timeout_seconds": timeout_seconds,
        "terminal_state": terminal_state,
        **bootstrap_artifact,
        **progress_payload,
    }


def bootstrap_artifact_extra(
    *,
    provider: str,
    model: str,
    reasoning_effort: str,
    live_cwd: Path,
    allowed_paths: list[str],
    blocked_paths: list[str],
    staged_workspace: bool,
    timed_out: bool,
    timeout_seconds: float | None,
    terminal_state: str,
    bootstrap_artifact: dict[str, Any],
    subprocess_artifact: dict[str, Any],
) -> dict[str, Any]:
    return {
        "provider": provider,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "tool_event_names": [],
        "modified_files": [],
        "commands": [],
        "test_commands": [],
        "live_cwd": str(live_cwd),
        "allowed_paths": allowed_paths,
        "blocked_paths": blocked_paths,
        "staged_workspace": staged_workspace,
        "timed_out": timed_out,
        "timeout_seconds": timeout_seconds,
        "terminal_state": terminal_state,
        "final_apply_pending": False,
        "final_apply_state": "not_started",
        "out_of_scope_files": [],
        "review_commands": [],
        **bootstrap_artifact,
        **subprocess_artifact,
    }


def teammate_snapshot_payload(
    *,
    envelope: Any,
    status: BackgroundTaskStatus,
    task_text: str,
    run: Any,
    response_path: str,
    live_cwd: Path,
    allowed_paths: list[str],
    blocked_paths: list[str],
    staged_workspace: bool,
    terminal_state: str,
    tool_event_names: list[str],
    modified_files: list[str],
    commands: list[str],
    test_commands: list[str],
    command_policies: list[dict[str, Any]],
    final_apply_pending: bool,
    final_apply_state: str,
    out_of_scope_files: list[str],
    review_commands: list[str],
    stream_event_count: int,
    progress_payload: dict[str, Any],
    bootstrap_artifact: dict[str, Any],
) -> dict[str, Any]:
    return {
        "task": envelope.to_dict(),
        "status": status.value,
        "task_text": task_text,
        "command": run.command,
        "returncode": run.returncode,
        "response_path": response_path,
        "stdout": run.stdout,
        "stderr": run.stderr,
        "cancelled": bool(run.cancelled),
        "timed_out": bool(run.timed_out),
        "timeout_seconds": run.timeout_seconds,
        "terminal_state": terminal_state,
        "tool_event_names": tool_event_names,
        "modified_files": modified_files,
        "commands": commands,
        "test_commands": test_commands,
        "command_policies": command_policies,
        "live_cwd": str(live_cwd),
        "allowed_paths": allowed_paths,
        "blocked_paths": blocked_paths,
        "staged_workspace": staged_workspace,
        "final_apply_pending": final_apply_pending,
        "final_apply_state": final_apply_state,
        "out_of_scope_files": out_of_scope_files,
        "review_commands": review_commands,
        "stream_event_count": stream_event_count,
        **progress_payload,
        **bootstrap_artifact,
    }


def teammate_artifact_extra(
    *,
    response_path: str,
    snapshot_path: str,
    provider: str,
    model: str,
    reasoning_effort: str,
    tool_event_names: list[str],
    modified_files: list[str],
    commands: list[str],
    test_commands: list[str],
    command_policies: list[dict[str, Any]],
    live_cwd: Path,
    allowed_paths: list[str],
    blocked_paths: list[str],
    staged_workspace: bool,
    run: Any,
    terminal_state: str,
    response_status: dict[str, Any],
    route_report: dict[str, Any],
    final_apply_pending: bool,
    final_apply_state: str,
    out_of_scope_files: list[str],
    review_commands: list[str],
    stream_event_count: int,
    bootstrap_artifact: dict[str, Any],
    subprocess_artifact: dict[str, Any],
    running_snapshot_metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "response_path": response_path,
        "snapshot_path": snapshot_path,
        "provider": provider,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "tool_event_names": tool_event_names,
        "modified_files": modified_files,
        "commands": commands,
        "test_commands": test_commands,
        "command_policies": command_policies,
        "live_cwd": str(live_cwd),
        "allowed_paths": allowed_paths,
        "blocked_paths": blocked_paths,
        "staged_workspace": staged_workspace,
        "timed_out": bool(run.timed_out),
        "timeout_seconds": run.timeout_seconds,
        "terminal_state": terminal_state,
        "runtime_provider_name": str(response_status.get("provider_name") or "").strip(),
        "runtime_provider_model": str(response_status.get("provider_model") or "").strip(),
        "runtime_timing_summary": str(response_status.get("timing_summary") or "").strip(),
        "route_report": route_report,
        "final_apply_pending": final_apply_pending,
        "final_apply_state": final_apply_state,
        "out_of_scope_files": out_of_scope_files,
        "review_commands": review_commands,
        "stream_event_count": stream_event_count,
        **bootstrap_artifact,
        **subprocess_artifact,
        **running_snapshot_metadata,
    }


def staged_result_artifact(
    *,
    artifact: dict[str, Any],
    final_apply_state: str,
    final_apply_pending: bool,
    review_commands: list[str],
    finished_at: str,
    out_of_scope_files: list[str] | None = None,
    applied_files: list[str] | None = None,
) -> dict[str, Any]:
    updated = artifact
    updated["final_apply_pending"] = final_apply_pending
    updated["final_apply_state"] = final_apply_state
    updated["review_commands"] = review_commands
    updated["final_apply_decided_at"] = finished_at
    if out_of_scope_files is not None:
        updated["out_of_scope_files"] = out_of_scope_files
    if applied_files is not None:
        updated["applied_files"] = applied_files
    return updated

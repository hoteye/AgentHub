from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from .models import BackgroundTaskStatus, TaskResult
from .tasks_execution_runtime import teammate_running_snapshot_path
from .tasks_stream_helpers_runtime import (
    resolve_dispatch_runner_pid,
    resolve_running_log_path,
    running_snapshot_process_info,
)

def worker_heartbeat_callback(
    *,
    results_dir: Path,
    task_id: str,
    task_type: str,
    touch_worker_state_results_dir_fn: Callable[..., None],
    on_heartbeat_callback: Callable[[], None] | None = None,
) -> Callable[[], None]:
    def _callback() -> None:
        touch_worker_state_results_dir_fn(
            results_dir,
            status="busy",
            active_task_id=task_id,
            active_task_type=task_type,
            runner_pid=os.getpid(),
        )
        if callable(on_heartbeat_callback):
            on_heartbeat_callback()

    return _callback


def consume_teammate_stdout_line(
    line: str,
    *,
    state: dict[str, Any],
    storage: Any,
    envelope: Any,
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
    monotonic_fn: Callable[[], float],
    consume_headless_jsonl_line_fn: Callable[[dict[str, Any], str], dict[str, Any]],
    synthetic_response_payload_fn: Callable[[dict[str, Any]], dict[str, Any]],
    teammate_response_projection_fn: Callable[..., dict[str, Any]],
    running_summary_text_fn: Callable[[dict[str, Any]], str],
    response_status_mapping_fn: Callable[[Any], dict[str, Any]],
    mapping_dict_fn: Callable[[Any], dict[str, Any]],
    route_report_from_status_fn: Callable[[dict[str, Any]], dict[str, Any]],
    teammate_commands_fn: Callable[[dict[str, Any]], list[str]],
    teammate_test_commands_fn: Callable[[list[str]], list[str]],
    teammate_modified_files_fn: Callable[[dict[str, Any], Any], list[str]],
    trim_error_fn: Callable[..., str],
    subprocess_artifact_fn: Callable[[dict[str, Any]], dict[str, Any]],
    task_artifact_fn: Callable[..., dict[str, Any]],
) -> None:
    consume_headless_jsonl_line_fn(state, line)
    now = monotonic_fn()
    last_persist = float(stream_progress.get("last_persist_monotonic") or 0.0)
    if (now - last_persist) < 0.75 and int(state.get("event_count") or 0) > 1:
        return
    stream_progress["last_persist_monotonic"] = now
    _persist_teammate_running_state(
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
        synthetic_response_payload_fn=synthetic_response_payload_fn,
        teammate_response_projection_fn=teammate_response_projection_fn,
        running_summary_text_fn=running_summary_text_fn,
        response_status_mapping_fn=response_status_mapping_fn,
        mapping_dict_fn=mapping_dict_fn,
        route_report_from_status_fn=route_report_from_status_fn,
        teammate_commands_fn=teammate_commands_fn,
        teammate_test_commands_fn=teammate_test_commands_fn,
        teammate_modified_files_fn=teammate_modified_files_fn,
        trim_error_fn=trim_error_fn,
        subprocess_artifact_fn=subprocess_artifact_fn,
        task_artifact_fn=task_artifact_fn,
    )


def ensure_teammate_running_snapshot(
    *,
    state: dict[str, Any],
    storage: Any,
    envelope: Any,
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
    synthetic_response_payload_fn: Callable[[dict[str, Any]], dict[str, Any]],
    teammate_response_projection_fn: Callable[..., dict[str, Any]],
    running_summary_text_fn: Callable[[dict[str, Any]], str],
    response_status_mapping_fn: Callable[[Any], dict[str, Any]],
    mapping_dict_fn: Callable[[Any], dict[str, Any]],
    route_report_from_status_fn: Callable[[dict[str, Any]], dict[str, Any]],
    teammate_commands_fn: Callable[[dict[str, Any]], list[str]],
    teammate_test_commands_fn: Callable[[list[str]], list[str]],
    teammate_modified_files_fn: Callable[[dict[str, Any], Any], list[str]],
    trim_error_fn: Callable[..., str],
    subprocess_artifact_fn: Callable[[dict[str, Any]], dict[str, Any]],
    task_artifact_fn: Callable[..., dict[str, Any]],
) -> None:
    if bool(stream_progress.get("has_running_snapshot")):
        return
    _persist_teammate_running_state(
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
        synthetic_response_payload_fn=synthetic_response_payload_fn,
        teammate_response_projection_fn=teammate_response_projection_fn,
        running_summary_text_fn=running_summary_text_fn,
        response_status_mapping_fn=response_status_mapping_fn,
        mapping_dict_fn=mapping_dict_fn,
        route_report_from_status_fn=route_report_from_status_fn,
        teammate_commands_fn=teammate_commands_fn,
        teammate_test_commands_fn=teammate_test_commands_fn,
        teammate_modified_files_fn=teammate_modified_files_fn,
        trim_error_fn=trim_error_fn,
        subprocess_artifact_fn=subprocess_artifact_fn,
        task_artifact_fn=task_artifact_fn,
    )


def _persist_teammate_running_state(
    *,
    state: dict[str, Any],
    storage: Any,
    envelope: Any,
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
    synthetic_response_payload_fn: Callable[[dict[str, Any]], dict[str, Any]],
    teammate_response_projection_fn: Callable[..., dict[str, Any]],
    running_summary_text_fn: Callable[[dict[str, Any]], str],
    response_status_mapping_fn: Callable[[Any], dict[str, Any]],
    mapping_dict_fn: Callable[[Any], dict[str, Any]],
    route_report_from_status_fn: Callable[[dict[str, Any]], dict[str, Any]],
    teammate_commands_fn: Callable[[dict[str, Any]], list[str]],
    teammate_test_commands_fn: Callable[[list[str]], list[str]],
    teammate_modified_files_fn: Callable[[dict[str, Any], Any], list[str]],
    trim_error_fn: Callable[..., str],
    subprocess_artifact_fn: Callable[[dict[str, Any]], dict[str, Any]],
    task_artifact_fn: Callable[..., dict[str, Any]],
) -> None:
    synthetic_payload = synthetic_response_payload_fn(state)
    projection = teammate_response_projection_fn(
        response_payload=synthetic_payload,
        live_cwd=live_cwd,
        response_status_mapping_fn=response_status_mapping_fn,
        mapping_dict_fn=mapping_dict_fn,
        route_report_from_status_fn=route_report_from_status_fn,
        teammate_commands_fn=teammate_commands_fn,
        teammate_test_commands_fn=teammate_test_commands_fn,
        teammate_modified_files_fn=teammate_modified_files_fn,
    )
    running_text = running_summary_text_fn(state)
    process_info = running_snapshot_process_info(
        storage=storage,
        envelope_task_id=envelope.task_id,
        stream_progress=stream_progress,
        task_id=envelope.task_id,
    )
    running_summary = trim_error_fn(running_text or "running", max_chars=120)
    running_progress_payload = {
        "step_count": 1,
        "checkpoint_count": 1,
        "current_step_id": "step_1",
        "current_step_status": "running",
        "current_step_title": "teammate headless turn",
        "latest_checkpoint": {
            "checkpoint_id": "checkpoint_1",
            "kind": "step_started",
            "status": "running",
            "summary": running_text or "running",
            "timestamp": started_at,
            "step_id": "step_1",
        },
    }
    running_snapshot_payload = {
        "task": envelope.to_dict(),
        "status": BackgroundTaskStatus.RUNNING.value,
        "queue_state": BackgroundTaskStatus.RUNNING.value,
        "terminal_state": "running",
        "summary": running_summary,
        "provider": provider,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "thread_id": str(synthetic_payload.get("thread_id") or "").strip(),
        "assistant_text_preview": trim_error_fn(str(projection.get("assistant_text") or running_text), max_chars=160),
        "commentary_text_preview": trim_error_fn(running_text, max_chars=160),
        "tool_event_names": list(projection.get("tool_event_names") or []),
        "modified_files": list(projection.get("modified_files") or []),
        "commands": list(projection.get("commands") or []),
        "test_commands": list(projection.get("test_commands") or []),
        "command_policies": list(projection.get("command_policies") or []),
        "allowed_paths": allowed_paths,
        "blocked_paths": blocked_paths,
        "staged_workspace": staged_workspace,
        "stream_event_count": int(state.get("event_count") or 0),
        "runner_pid": process_info["runner_pid"],
        "worker_pid": process_info["worker_pid"],
        "stdout_path": process_info["stdout_path"],
        "stderr_path": process_info["stderr_path"],
        "last_event_at": process_info["last_event_at"],
        **bootstrap_artifact,
        **subprocess_artifact_fn(running_progress_payload),
    }
    running_snapshot_path = teammate_running_snapshot_path(
        results_dir=storage.results_dir,
        task_id=envelope.task_id,
    )
    storage.write_result_snapshot(
        envelope.task_id,
        running_snapshot_payload,
        suffix="teammate_running",
    )
    stream_progress["has_running_snapshot"] = True
    artifact = task_artifact_fn(
        envelope,
        queue_state=BackgroundTaskStatus.RUNNING.value,
        cancel_requested=False,
        extra={
            "provider": provider,
            "model": model,
            "reasoning_effort": reasoning_effort,
            "thread_id": str(synthetic_payload.get("thread_id") or "").strip(),
            "assistant_text_preview": trim_error_fn(str(projection.get("assistant_text") or running_text), max_chars=160),
            "commentary_text_preview": trim_error_fn(running_text, max_chars=160),
            "tool_event_names": list(projection.get("tool_event_names") or []),
            "modified_files": list(projection.get("modified_files") or []),
            "commands": list(projection.get("commands") or []),
            "test_commands": list(projection.get("test_commands") or []),
            "command_policies": list(projection.get("command_policies") or []),
            "allowed_paths": allowed_paths,
            "blocked_paths": blocked_paths,
            "staged_workspace": staged_workspace,
            "stream_event_count": int(state.get("event_count") or 0),
            "terminal_state": "running",
            "running_snapshot_path": str(running_snapshot_path),
            "runner_pid": process_info["runner_pid"],
            "worker_pid": process_info["worker_pid"],
            "stdout_path": process_info["stdout_path"],
            "stderr_path": process_info["stderr_path"],
            "last_event_at": process_info["last_event_at"],
            **bootstrap_artifact,
            **subprocess_artifact_fn(running_progress_payload),
        },
    )
    storage.upsert_result(
        TaskResult(
            task_id=envelope.task_id,
            status=BackgroundTaskStatus.RUNNING,
            started_at=started_at,
            summary=running_summary,
            artifact=artifact,
            retry_count=retry_count,
        )
    )


def _resolve_dispatch_runner_pid(
    storage: Any,
    *,
    envelope_task_id: str,
    stream_progress: dict[str, Any],
) -> int:
    cached_runner_pid = stream_progress.get("runner_pid")
    try:
        normalized_cached = max(0, int(cached_runner_pid or 0))
    except (TypeError, ValueError):
        normalized_cached = 0
    if normalized_cached > 0:
        return normalized_cached
    control = storage.get_control(envelope_task_id) if hasattr(storage, "get_control") else None
    if not isinstance(control, dict):
        return 0
    try:
        resolved_runner_pid = max(0, int(control.get("runner_pid") or 0))
    except (TypeError, ValueError):
        resolved_runner_pid = 0
    if resolved_runner_pid > 0:
        stream_progress["runner_pid"] = resolved_runner_pid
    return resolved_runner_pid


def _resolve_running_log_path(
    *,
    stream_progress: dict[str, Any],
    key: str,
    storage: Any,
    task_id: str,
    log_kind: str,
) -> str:
    cached = str(stream_progress.get(key) or "").strip()
    if cached:
        return cached
    resolved = str(Path(storage.results_dir) / f"{task_id}_teammate_{log_kind}.log")
    stream_progress[key] = resolved
    return resolved

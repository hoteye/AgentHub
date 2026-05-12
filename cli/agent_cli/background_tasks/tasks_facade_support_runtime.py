from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from . import tasks_stream_runtime
from . import tasks_support_runtime
from . import tasks_teammate_runtime
from .models import BackgroundTaskStatus, TaskEnvelope, TaskResult
from .queue_runtime import _subprocess_artifact, _task_artifact
from .storage import BackgroundTaskStorage
from .worker_state import touch_worker_state_results_dir

normalize_argv = tasks_support_runtime.normalize_argv
dedupe_compact_items = tasks_support_runtime.dedupe_compact_items
relative_task_path = tasks_support_runtime.relative_task_path
tool_payload_path_candidates = tasks_support_runtime.tool_payload_path_candidates
teammate_modified_files = tasks_support_runtime.teammate_modified_files
teammate_commands = tasks_support_runtime.teammate_commands
teammate_test_commands = tasks_support_runtime.teammate_test_commands
parse_path_list = tasks_support_runtime.parse_path_list
task_timeout_seconds = tasks_support_runtime.task_timeout_seconds
timeout_error_text = tasks_support_runtime.timeout_error_text
mapping_dict = tasks_support_runtime.mapping_dict
response_status_mapping = tasks_support_runtime.response_status_mapping
route_report_from_status = tasks_support_runtime.route_report_from_status
bootstrap_diagnostic_artifact_fields = tasks_support_runtime.bootstrap_diagnostic_artifact_fields
bootstrap_failure_error = tasks_support_runtime.bootstrap_failure_error
normalize_policy_path = tasks_support_runtime.normalize_policy_path
trim_error = tasks_support_runtime.trim_error
decode_json_text = tasks_support_runtime.decode_json_text
load_review_payload = tasks_support_runtime.load_review_payload


def normalize_smoke_kind(payload: dict[str, Any], *, smoke_kind_scripts: dict[str, Path]) -> str:
    return tasks_support_runtime.normalize_smoke_kind(payload, smoke_kind_scripts=smoke_kind_scripts)


def background_terminal_state(
    *,
    status: BackgroundTaskStatus,
    cancelled: bool = False,
    timed_out: bool = False,
) -> str:
    return tasks_support_runtime.background_terminal_state(
        status=status,
        cancelled=cancelled,
        timed_out=timed_out,
    )


def collect_bootstrap_diagnostics(cwd: Path, *, bootstrap_dependency_files: tuple[str, ...]) -> dict[str, Any]:
    return tasks_support_runtime.collect_bootstrap_diagnostics(
        cwd,
        bootstrap_dependency_files=bootstrap_dependency_files,
    )


def paths_outside_policy(
    paths: list[str],
    *,
    allowed_paths: list[str],
    blocked_paths: list[str],
) -> list[str]:
    return tasks_support_runtime.paths_outside_policy(
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
    return tasks_support_runtime.prepare_stage_workspace(
        task_id,
        source_root=source_root,
        storage=storage,
    )


def collect_workspace_changes(source_root: Path, stage_root: Path) -> list[dict[str, Any]]:
    return tasks_support_runtime.collect_workspace_changes(source_root, stage_root)


def teammate_review_commands(task_id: str, *, blocked: bool) -> list[str]:
    return tasks_support_runtime.teammate_review_commands(task_id, blocked=blocked)


def worker_heartbeat_callback(
    *,
    storage: BackgroundTaskStorage,
    envelope: TaskEnvelope,
    on_heartbeat_callback: Any = None,
) -> Any:
    return tasks_stream_runtime.worker_heartbeat_callback(
        results_dir=storage.results_dir,
        task_id=envelope.task_id,
        task_type=envelope.task_type.value,
        touch_worker_state_results_dir_fn=touch_worker_state_results_dir,
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
    tasks_stream_runtime.consume_teammate_stdout_line(
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
        monotonic_fn=time.monotonic,
        consume_headless_jsonl_line_fn=tasks_teammate_runtime.consume_headless_jsonl_line,
        synthetic_response_payload_fn=tasks_teammate_runtime.synthetic_response_payload_from_jsonl_state,
        teammate_response_projection_fn=tasks_teammate_runtime.teammate_response_projection,
        running_summary_text_fn=tasks_teammate_runtime.running_summary_text,
        response_status_mapping_fn=response_status_mapping,
        mapping_dict_fn=mapping_dict,
        route_report_from_status_fn=route_report_from_status,
        teammate_commands_fn=teammate_commands,
        teammate_test_commands_fn=teammate_test_commands,
        teammate_modified_files_fn=teammate_modified_files,
        trim_error_fn=trim_error,
        subprocess_artifact_fn=_subprocess_artifact,
        task_artifact_fn=_task_artifact,
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
    tasks_stream_runtime.ensure_teammate_running_snapshot(
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
        synthetic_response_payload_fn=tasks_teammate_runtime.synthetic_response_payload_from_jsonl_state,
        teammate_response_projection_fn=tasks_teammate_runtime.teammate_response_projection,
        running_summary_text_fn=tasks_teammate_runtime.running_summary_text,
        response_status_mapping_fn=response_status_mapping,
        mapping_dict_fn=mapping_dict,
        route_report_from_status_fn=route_report_from_status,
        teammate_commands_fn=teammate_commands,
        teammate_test_commands_fn=teammate_test_commands,
        teammate_modified_files_fn=teammate_modified_files,
        trim_error_fn=trim_error,
        subprocess_artifact_fn=_subprocess_artifact,
        task_artifact_fn=_task_artifact,
    )


def persist_updated_result(storage: BackgroundTaskStorage, result: TaskResult) -> TaskResult:
    storage.upsert_result(result)
    storage.write_result_snapshot(result.task_id, result.to_dict(), suffix="snapshot")
    return result

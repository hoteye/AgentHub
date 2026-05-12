from __future__ import annotations

from pathlib import Path
from typing import Any

from . import tasks_facade_ops_runtime
from .tasks_facade_support_runtime import (
    background_terminal_state,
    bootstrap_diagnostic_artifact_fields,
    bootstrap_failure_error,
    collect_bootstrap_diagnostics,
    collect_workspace_changes,
    consume_teammate_stdout_line,
    decode_json_text,
    dedupe_compact_items,
    ensure_teammate_running_snapshot,
    load_review_payload,
    mapping_dict,
    normalize_argv,
    normalize_policy_path,
    normalize_smoke_kind,
    parse_path_list,
    paths_outside_policy,
    persist_updated_result,
    prepare_stage_workspace,
    relative_task_path,
    response_status_mapping,
    route_report_from_status,
    task_timeout_seconds,
    teammate_commands,
    teammate_modified_files,
    teammate_review_commands,
    teammate_test_commands,
    timeout_error_text,
    tool_payload_path_candidates,
    trim_error,
    worker_heartbeat_callback,
)
from .models import TaskEnvelope, TaskResult
from .storage import BackgroundTaskStorage

__all__ = [
    "apply_staged_teammate_result",
    "background_terminal_state",
    "bootstrap_diagnostic_artifact_fields",
    "bootstrap_failure_error",
    "collect_bootstrap_diagnostics",
    "collect_workspace_changes",
    "consume_teammate_stdout_line",
    "decode_json_text",
    "dedupe_compact_items",
    "ensure_teammate_running_snapshot",
    "execute_benchmark_task",
    "execute_smoke_task",
    "execute_teammate_task",
    "invoke_benchmark_runner",
    "load_review_payload",
    "mapping_dict",
    "normalize_argv",
    "normalize_policy_path",
    "normalize_smoke_kind",
    "parse_path_list",
    "paths_outside_policy",
    "persist_updated_result",
    "prepare_stage_workspace",
    "relative_task_path",
    "reject_staged_teammate_result",
    "response_status_mapping",
    "route_report_from_status",
    "run_benchmark_subprocess",
    "task_timeout_seconds",
    "teammate_commands",
    "teammate_modified_files",
    "teammate_review_commands",
    "teammate_test_commands",
    "timeout_error_text",
    "tool_payload_path_candidates",
    "trim_error",
    "worker_heartbeat_callback",
]


def run_benchmark_subprocess(
    envelope: TaskEnvelope,
    *,
    report_path: Path,
    cli_root: Path,
    benchmark_script_path: Path,
    cwd: Path | None = None,
    storage: BackgroundTaskStorage | None = None,
    runner_token: str = "",
) -> Any:
    return tasks_facade_ops_runtime.run_benchmark_subprocess(
        envelope,
        report_path=report_path,
        cli_root=cli_root,
        benchmark_script_path=benchmark_script_path,
        cwd=cwd,
        storage=storage,
        runner_token=runner_token,
        normalize_argv_fn=normalize_argv,
        task_timeout_seconds_fn=task_timeout_seconds,
        worker_heartbeat_callback_fn=worker_heartbeat_callback,
    )


def invoke_benchmark_runner(
    envelope: TaskEnvelope,
    *,
    report_path: Path,
    storage: BackgroundTaskStorage,
    runner_token: str,
    cli_root: Path,
    benchmark_script_path: Path,
) -> Any:
    return tasks_facade_ops_runtime.invoke_benchmark_runner(
        envelope,
        report_path=report_path,
        storage=storage,
        runner_token=runner_token,
        cli_root=cli_root,
        benchmark_script_path=benchmark_script_path,
    )


def execute_benchmark_task(
    envelope: TaskEnvelope,
    *,
    storage: BackgroundTaskStorage,
    runner_token: str,
    started_at: str,
    retry_count: int,
    cli_root: Path,
    benchmark_script_path: Path,
) -> TaskResult:
    return tasks_facade_ops_runtime.execute_benchmark_task(
        envelope,
        storage=storage,
        runner_token=runner_token,
        started_at=started_at,
        retry_count=retry_count,
        cli_root=cli_root,
        benchmark_script_path=benchmark_script_path,
        timeout_error_text_fn=timeout_error_text,
        trim_error_fn=trim_error,
        background_terminal_state_fn=background_terminal_state,
    )


def execute_smoke_task(
    envelope: TaskEnvelope,
    *,
    storage: BackgroundTaskStorage,
    runner_token: str,
    started_at: str,
    retry_count: int,
    cli_root: Path,
    smoke_kind_scripts: dict[str, Path],
) -> TaskResult:
    return tasks_facade_ops_runtime.execute_smoke_task(
        envelope,
        storage=storage,
        runner_token=runner_token,
        started_at=started_at,
        retry_count=retry_count,
        cli_root=cli_root,
        smoke_kind_scripts=smoke_kind_scripts,
        normalize_smoke_kind_fn=normalize_smoke_kind,
        normalize_argv_fn=normalize_argv,
        task_timeout_seconds_fn=task_timeout_seconds,
        worker_heartbeat_callback_fn=worker_heartbeat_callback,
        timeout_error_text_fn=timeout_error_text,
        trim_error_fn=trim_error,
        background_terminal_state_fn=background_terminal_state,
    )


def execute_teammate_task(
    envelope: TaskEnvelope,
    *,
    storage: BackgroundTaskStorage,
    runner_token: str,
    started_at: str,
    retry_count: int,
    cli_root: Path,
    workspace_root: Path,
    headless_response_path_env: str,
    bootstrap_dependency_files: tuple[str, ...],
) -> TaskResult:
    return tasks_facade_ops_runtime.execute_teammate_task(
        envelope,
        storage=storage,
        runner_token=runner_token,
        started_at=started_at,
        retry_count=retry_count,
        cli_root=cli_root,
        workspace_root=workspace_root,
        headless_response_path_env=headless_response_path_env,
        bootstrap_dependency_files=bootstrap_dependency_files,
        parse_path_list_fn=parse_path_list,
        dedupe_compact_items_fn=dedupe_compact_items,
        normalize_policy_path_fn=normalize_policy_path,
        task_timeout_seconds_fn=task_timeout_seconds,
        collect_bootstrap_diagnostics_fn=collect_bootstrap_diagnostics,
        bootstrap_diagnostic_artifact_fields_fn=bootstrap_diagnostic_artifact_fields,
        bootstrap_failure_error_fn=bootstrap_failure_error,
        prepare_stage_workspace_fn=prepare_stage_workspace,
        consume_teammate_stdout_line_fn=consume_teammate_stdout_line,
        worker_heartbeat_callback_fn=worker_heartbeat_callback,
        ensure_teammate_running_snapshot_fn=ensure_teammate_running_snapshot,
        decode_json_text_fn=decode_json_text,
        collect_workspace_changes_fn=collect_workspace_changes,
        response_status_mapping_fn=response_status_mapping,
        mapping_dict_fn=mapping_dict,
        route_report_from_status_fn=route_report_from_status,
        teammate_commands_fn=teammate_commands,
        teammate_test_commands_fn=teammate_test_commands,
        teammate_modified_files_fn=teammate_modified_files,
        paths_outside_policy_fn=paths_outside_policy,
        teammate_review_commands_fn=teammate_review_commands,
        trim_error_fn=trim_error,
        timeout_error_text_fn=timeout_error_text,
        background_terminal_state_fn=background_terminal_state,
    )


def apply_staged_teammate_result(task_id: str, *, storage: BackgroundTaskStorage) -> TaskResult | None:
    return tasks_facade_ops_runtime.apply_staged_teammate_result(
        task_id,
        storage=storage,
        load_review_payload_fn=load_review_payload,
        normalize_policy_path_fn=normalize_policy_path,
        parse_path_list_fn=parse_path_list,
        dedupe_compact_items_fn=dedupe_compact_items,
        paths_outside_policy_fn=paths_outside_policy,
        trim_error_fn=trim_error,
        persist_updated_result_fn=persist_updated_result,
    )


def reject_staged_teammate_result(task_id: str, *, storage: BackgroundTaskStorage) -> TaskResult | None:
    return tasks_facade_ops_runtime.reject_staged_teammate_result(
        task_id,
        storage=storage,
        load_review_payload_fn=load_review_payload,
        persist_updated_result_fn=persist_updated_result,
    )

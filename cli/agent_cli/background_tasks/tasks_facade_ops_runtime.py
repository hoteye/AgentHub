from __future__ import annotations

import inspect
import sys
from pathlib import Path
from typing import Any

from . import tasks_facade_ops_teammate_runtime
from . import tasks_execution_runtime
from . import tasks_flow_runtime
from . import tasks_runtime
from .models import TaskEnvelope, TaskResult, utc_now_iso
from .queue_runtime import _subprocess_artifact, _subprocess_progress_payload, _task_artifact
from .storage import BackgroundTaskStorage
from .tasks_facade_ops_helpers import (
    invoke_benchmark_runner,
    resolve_smoke_profile_payload as _resolve_smoke_profile_payload,
    run_benchmark_subprocess,
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
    timeout_error_text_fn: Any,
    trim_error_fn: Any,
    background_terminal_state_fn: Any,
) -> TaskResult:
    report_path = storage.results_dir / f"{envelope.task_id}_benchmark_report.json"
    run = invoke_benchmark_runner(
        envelope,
        report_path=report_path,
        storage=storage,
        runner_token=runner_token,
        cli_root=cli_root,
        benchmark_script_path=benchmark_script_path,
    )
    status, summary, error_text = tasks_runtime.subprocess_outcome(
        run,
        success_summary=__import__("cli.agent_cli.background_tasks.tasks_support_runtime", fromlist=[""]).benchmark_success_summary(run.report_path),
        failure_summary="benchmark task failed",
        cancelled_summary="benchmark task cancelled",
        timed_out_summary="benchmark task timed out",
        timeout_error_text_fn=timeout_error_text_fn,
        trim_error_fn=trim_error_fn,
        timeout_label="benchmark",
    )
    return tasks_flow_runtime.build_subprocess_task_result(
        envelope=envelope,
        storage=storage,
        run=run,
        started_at=started_at,
        retry_count=retry_count,
        status=status,
        summary=summary,
        error_text=error_text,
        title="benchmark subprocess",
        goal="benchmark_headless_models.py",
        snapshot_suffix="benchmark",
        report_path=run.report_path,
        terminal_state=background_terminal_state_fn(
            status=status,
            cancelled=bool(run.cancelled),
            timed_out=bool(run.timed_out),
        ),
        subprocess_progress_payload_fn=_subprocess_progress_payload,
        subprocess_snapshot_payload_fn=tasks_runtime.subprocess_snapshot_payload,
        subprocess_artifact_payload_fn=tasks_runtime.subprocess_artifact_payload,
        subprocess_artifact_fn=_subprocess_artifact,
        task_artifact_fn=_task_artifact,
        subprocess_task_result_fn=tasks_runtime.subprocess_task_result,
        utc_now_iso_fn=utc_now_iso,
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
    normalize_smoke_kind_fn: Any,
    normalize_argv_fn: Any,
    task_timeout_seconds_fn: Any,
    worker_heartbeat_callback_fn: Any,
    timeout_error_text_fn: Any,
    trim_error_fn: Any,
    background_terminal_state_fn: Any,
) -> TaskResult:
    from .tasks import _run_logged_subprocess
    from . import tasks_support_runtime

    payload = dict(envelope.payload or {})
    payload, smoke_profile = _resolve_smoke_profile_payload(payload, normalize_argv_fn=normalize_argv_fn)
    report_path = storage.results_dir / f"{envelope.task_id}_smoke_report.json"
    run_request = tasks_execution_runtime.build_smoke_run_request(
        payload=payload,
        cli_root=cli_root,
        smoke_kind_scripts=smoke_kind_scripts,
        report_path=report_path,
        python_executable=sys.executable,
        normalize_smoke_kind_fn=lambda inner_payload: normalize_smoke_kind_fn(
            inner_payload,
            smoke_kind_scripts=smoke_kind_scripts,
        ),
        normalize_argv_fn=normalize_argv_fn,
        task_timeout_seconds_fn=task_timeout_seconds_fn,
    )
    kind = str(run_request["kind"])
    script_path = run_request["script_path"]
    run = _run_logged_subprocess(
        envelope,
        command=run_request["command"],
        cwd=run_request["cwd"],
        storage=storage,
        runner_token=runner_token,
        log_prefix="smoke",
        timeout_seconds=run_request["timeout_seconds"],
        heartbeat_callback=worker_heartbeat_callback_fn(storage=storage, envelope=envelope),
    )
    status, summary, error_text = tasks_runtime.subprocess_outcome(
        run,
        success_summary=tasks_support_runtime.smoke_success_summary(kind, report_path),
        failure_summary=f"smoke task failed: {kind}",
        cancelled_summary=f"smoke task cancelled: {kind}",
        timed_out_summary=f"smoke task timed out: {kind}",
        timeout_error_text_fn=timeout_error_text_fn,
        trim_error_fn=trim_error_fn,
        timeout_label="smoke",
    )
    result = tasks_flow_runtime.build_subprocess_task_result(
        envelope=envelope,
        storage=storage,
        run=run,
        started_at=started_at,
        retry_count=retry_count,
        status=status,
        summary=summary,
        error_text=error_text,
        title=f"smoke subprocess ({kind})",
        goal=f"{script_path.name}:{kind}",
        snapshot_suffix="smoke",
        report_path=report_path,
        terminal_state=background_terminal_state_fn(
            status=status,
            cancelled=bool(run.cancelled),
            timed_out=bool(run.timed_out),
        ),
        extra_snapshot={
            "kind": kind,
            "profile": smoke_profile,
            "script_path": str(script_path),
            "report_path": str(report_path),
        },
        extra_artifact={
            "kind": kind,
            "profile": smoke_profile,
            "script_path": str(script_path),
            "report_path": str(report_path),
        },
        subprocess_progress_payload_fn=_subprocess_progress_payload,
        subprocess_snapshot_payload_fn=tasks_runtime.subprocess_snapshot_payload,
        subprocess_artifact_payload_fn=tasks_runtime.subprocess_artifact_payload,
        subprocess_artifact_fn=_subprocess_artifact,
        task_artifact_fn=_task_artifact,
        subprocess_task_result_fn=tasks_runtime.subprocess_task_result,
        utc_now_iso_fn=utc_now_iso,
    )
    if report_path.exists():
        result.artifact["report_exists"] = True
    return result


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
    parse_path_list_fn: Any,
    dedupe_compact_items_fn: Any,
    normalize_policy_path_fn: Any,
    task_timeout_seconds_fn: Any,
    collect_bootstrap_diagnostics_fn: Any,
    bootstrap_diagnostic_artifact_fields_fn: Any,
    bootstrap_failure_error_fn: Any,
    prepare_stage_workspace_fn: Any,
    consume_teammate_stdout_line_fn: Any,
    worker_heartbeat_callback_fn: Any,
    ensure_teammate_running_snapshot_fn: Any,
    decode_json_text_fn: Any,
    collect_workspace_changes_fn: Any,
    response_status_mapping_fn: Any,
    mapping_dict_fn: Any,
    route_report_from_status_fn: Any,
    teammate_commands_fn: Any,
    teammate_test_commands_fn: Any,
    teammate_modified_files_fn: Any,
    paths_outside_policy_fn: Any,
    teammate_review_commands_fn: Any,
    trim_error_fn: Any,
    timeout_error_text_fn: Any,
    background_terminal_state_fn: Any,
) -> TaskResult:
    return tasks_facade_ops_teammate_runtime.execute_teammate_task(
        envelope=envelope,
        storage=storage,
        runner_token=runner_token,
        started_at=started_at,
        retry_count=retry_count,
        cli_root=cli_root,
        workspace_root=workspace_root,
        headless_response_path_env=headless_response_path_env,
        bootstrap_dependency_files=bootstrap_dependency_files,
        parse_path_list_fn=parse_path_list_fn,
        dedupe_compact_items_fn=dedupe_compact_items_fn,
        normalize_policy_path_fn=normalize_policy_path_fn,
        task_timeout_seconds_fn=task_timeout_seconds_fn,
        collect_bootstrap_diagnostics_fn=collect_bootstrap_diagnostics_fn,
        bootstrap_diagnostic_artifact_fields_fn=bootstrap_diagnostic_artifact_fields_fn,
        bootstrap_failure_error_fn=bootstrap_failure_error_fn,
        prepare_stage_workspace_fn=prepare_stage_workspace_fn,
        consume_teammate_stdout_line_fn=consume_teammate_stdout_line_fn,
        worker_heartbeat_callback_fn=worker_heartbeat_callback_fn,
        ensure_teammate_running_snapshot_fn=ensure_teammate_running_snapshot_fn,
        decode_json_text_fn=decode_json_text_fn,
        collect_workspace_changes_fn=collect_workspace_changes_fn,
        response_status_mapping_fn=response_status_mapping_fn,
        mapping_dict_fn=mapping_dict_fn,
        route_report_from_status_fn=route_report_from_status_fn,
        teammate_commands_fn=teammate_commands_fn,
        teammate_test_commands_fn=teammate_test_commands_fn,
        teammate_modified_files_fn=teammate_modified_files_fn,
        paths_outside_policy_fn=paths_outside_policy_fn,
        teammate_review_commands_fn=teammate_review_commands_fn,
        trim_error_fn=trim_error_fn,
        timeout_error_text_fn=timeout_error_text_fn,
        background_terminal_state_fn=background_terminal_state_fn,
    )


def apply_staged_teammate_result(
    task_id: str,
    *,
    storage: BackgroundTaskStorage,
    load_review_payload_fn: Any,
    normalize_policy_path_fn: Any,
    parse_path_list_fn: Any,
    dedupe_compact_items_fn: Any,
    paths_outside_policy_fn: Any,
    trim_error_fn: Any,
    persist_updated_result_fn: Any,
) -> TaskResult | None:
    return tasks_facade_ops_teammate_runtime.apply_staged_teammate_result(
        task_id,
        storage=storage,
        load_review_payload_fn=load_review_payload_fn,
        normalize_policy_path_fn=normalize_policy_path_fn,
        parse_path_list_fn=parse_path_list_fn,
        dedupe_compact_items_fn=dedupe_compact_items_fn,
        paths_outside_policy_fn=paths_outside_policy_fn,
        trim_error_fn=trim_error_fn,
        persist_updated_result_fn=persist_updated_result_fn,
    )


def reject_staged_teammate_result(
    task_id: str,
    *,
    storage: BackgroundTaskStorage,
    load_review_payload_fn: Any,
    persist_updated_result_fn: Any,
) -> TaskResult | None:
    return tasks_facade_ops_teammate_runtime.reject_staged_teammate_result(
        task_id,
        storage=storage,
        load_review_payload_fn=load_review_payload_fn,
        persist_updated_result_fn=persist_updated_result_fn,
    )

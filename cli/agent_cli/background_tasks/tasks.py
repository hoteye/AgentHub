from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import BackgroundTaskStatus, BackgroundTaskType, TaskEnvelope, TaskResult, new_task_id, utc_now_iso
from .storage import BackgroundTaskStorage
from . import subprocess_runtime
from . import tasks_delegates_runtime
from . import tasks_facade_runtime
from . import tasks_policy_helper_runtime
from . import tasks_support_runtime
from .subprocess_runtime import run_logged_subprocess
from .queue_runtime import (
    _cancelled_result,
    _claim_dispatch,
    _task_artifact,
)


_CLI_ROOT = Path(__file__).resolve().parents[2]
_WORKSPACE_ROOT = _CLI_ROOT.parent
_BENCHMARK_SCRIPT_PATH = _CLI_ROOT / "scripts" / "benchmark_headless_models.py"
_MULTI_LLM_SCRIPT_PATH = _CLI_ROOT / "scripts" / "run_multi_llm_live_cases.py"
_POLICY_HELPER_SCRIPT_PATH = _CLI_ROOT / "scripts" / "run_policy_helper_live_cases.py"
_BOOTSTRAP_DEPENDENCY_FILES = ("pyproject.toml", "requirements.txt", "package.json")
_HEADLESS_RESPONSE_PATH_ENV = "AGENT_CLI_HEADLESS_RESPONSE_PATH"
_POLICY_HELPER_REGRESSION_PROFILE = tasks_policy_helper_runtime.POLICY_HELPER_REGRESSION_PROFILE
_POLICY_HELPER_REGRESSION_KIND = tasks_policy_helper_runtime.POLICY_HELPER_REGRESSION_KIND
_POLICY_HELPER_REGRESSION_DEFAULT_COMBOS = tasks_policy_helper_runtime.POLICY_HELPER_REGRESSION_DEFAULT_COMBOS
_POLICY_HELPER_REGRESSION_DEFAULT_ARGV = tasks_policy_helper_runtime.POLICY_HELPER_REGRESSION_DEFAULT_ARGV
_POLICY_HELPER_BACKGROUND_PROFILE_KEY = tasks_policy_helper_runtime.POLICY_HELPER_BACKGROUND_PROFILE_KEY

_SMOKE_KIND_SCRIPTS = {
    "multi_llm": _MULTI_LLM_SCRIPT_PATH,
    "multi_llm_live_cases": _MULTI_LLM_SCRIPT_PATH,
    "multi_llm_regression": _MULTI_LLM_SCRIPT_PATH,
    "policy_helper": _POLICY_HELPER_SCRIPT_PATH,
    "policy_helper_live_cases": _POLICY_HELPER_SCRIPT_PATH,
    "policy_helper_regression": _POLICY_HELPER_SCRIPT_PATH,
}

BenchmarkRunResult = subprocess_runtime.BenchmarkRunResult
SubprocessRunResult = subprocess_runtime.SubprocessRunResult
_run_logged_subprocess = run_logged_subprocess


def execute_background_task(
    envelope: TaskEnvelope,
    *,
    storage: BackgroundTaskStorage,
    runner_token: str = "",
    claimed: bool = False,
) -> TaskResult:
    token = str(runner_token or new_task_id("runner")).strip()
    existing = storage.get_result(envelope.task_id)
    retry_count = int(getattr(existing, "retry_count", 0) or 0)
    started_at = utc_now_iso()

    if not _claim_dispatch(storage, envelope, runner_token=token, claimed=claimed):
        return existing or TaskResult(
            task_id=envelope.task_id,
            status=BackgroundTaskStatus.QUEUED,
            summary="stale dispatch skipped",
            retry_count=retry_count,
        )

    if storage.is_cancel_requested(envelope.task_id, dispatch_id=envelope.dispatch_id):
        result = _cancelled_result(
            envelope,
            started_at=started_at,
            retry_count=retry_count,
            summary=f"{envelope.task_type.value} task cancelled before start",
        )
        storage.complete_dispatch(
            envelope.task_id,
            dispatch_id=envelope.dispatch_id,
            queue_state=BackgroundTaskStatus.CANCELLED.value,
            runner_token=token,
        )
        storage.upsert_result(result)
        return result

    storage.upsert_result(
        TaskResult(
            task_id=envelope.task_id,
            status=BackgroundTaskStatus.RUNNING,
            started_at=started_at,
            summary="running",
            artifact=_task_artifact(
                envelope,
                queue_state=BackgroundTaskStatus.RUNNING.value,
                cancel_requested=False,
            ),
            retry_count=retry_count,
        )
    )

    try:
        if envelope.task_type == BackgroundTaskType.BENCHMARK:
            result = _execute_benchmark_task(
                envelope,
                storage=storage,
                runner_token=token,
                started_at=started_at,
                retry_count=retry_count,
            )
        elif envelope.task_type == BackgroundTaskType.SMOKE:
            result = _execute_smoke_task(
                envelope,
                storage=storage,
                runner_token=token,
                started_at=started_at,
                retry_count=retry_count,
            )
        elif envelope.task_type == BackgroundTaskType.TEAMMATE:
            result = _execute_teammate_task(
                envelope,
                storage=storage,
                runner_token=token,
                started_at=started_at,
                retry_count=retry_count,
            )
        else:
            raise ValueError(f"unsupported background task type: {envelope.task_type.value}")
    except Exception as exc:
        result = TaskResult(
            task_id=envelope.task_id,
            status=BackgroundTaskStatus.FAILED,
            started_at=started_at,
            finished_at=utc_now_iso(),
            summary=f"{envelope.task_type.value} task failed",
            artifact=_task_artifact(
                envelope,
                queue_state=BackgroundTaskStatus.FAILED.value,
                cancel_requested=False,
            ),
            error=f"{type(exc).__name__}: {exc}",
            retry_count=retry_count,
        )
        storage.write_result_snapshot(
            envelope.task_id,
            {
                "task": envelope.to_dict(),
                "status": result.status.value,
                "summary": result.summary,
                "error": result.error,
            },
            suffix="failure",
        )

    storage.complete_dispatch(
        envelope.task_id,
        dispatch_id=envelope.dispatch_id,
        queue_state=result.status.value,
        runner_token=token,
    )
    storage.upsert_result(result)
    return result


def run_benchmark_subprocess(
    envelope: TaskEnvelope,
    *,
    report_path: Path,
    cwd: Path | None = None,
    storage: BackgroundTaskStorage | None = None,
    runner_token: str = "",
) -> BenchmarkRunResult:
    return tasks_facade_runtime.run_benchmark_subprocess(
        envelope,
        report_path=report_path,
        cli_root=_CLI_ROOT,
        benchmark_script_path=_BENCHMARK_SCRIPT_PATH,
        cwd=cwd,
        storage=storage,
        runner_token=runner_token,
    )


def _execute_benchmark_task(
    envelope: TaskEnvelope,
    *,
    storage: BackgroundTaskStorage,
    runner_token: str,
    started_at: str,
    retry_count: int,
) -> TaskResult:
    return tasks_facade_runtime.execute_benchmark_task(
        envelope,
        storage=storage,
        runner_token=runner_token,
        started_at=started_at,
        retry_count=retry_count,
        cli_root=_CLI_ROOT,
        benchmark_script_path=_BENCHMARK_SCRIPT_PATH,
    )


def _execute_smoke_task(
    envelope: TaskEnvelope,
    *,
    storage: BackgroundTaskStorage,
    runner_token: str,
    started_at: str,
    retry_count: int,
) -> TaskResult:
    normalized_envelope = _normalize_policy_helper_regression_envelope(envelope)
    result = tasks_facade_runtime.execute_smoke_task(
        normalized_envelope,
        storage=storage,
        runner_token=runner_token,
        started_at=started_at,
        retry_count=retry_count,
        cli_root=_CLI_ROOT,
        smoke_kind_scripts=_SMOKE_KIND_SCRIPTS,
    )
    return _enrich_policy_helper_smoke_result(result, envelope=normalized_envelope)


def _execute_teammate_task(
    envelope: TaskEnvelope,
    *,
    storage: BackgroundTaskStorage,
    runner_token: str,
    started_at: str,
    retry_count: int,
) -> TaskResult:
    return tasks_facade_runtime.execute_teammate_task(
        envelope,
        storage=storage,
        runner_token=runner_token,
        started_at=started_at,
        retry_count=retry_count,
        cli_root=_CLI_ROOT,
        workspace_root=_WORKSPACE_ROOT,
        headless_response_path_env=_HEADLESS_RESPONSE_PATH_ENV,
        bootstrap_dependency_files=_BOOTSTRAP_DEPENDENCY_FILES,
    )


_normalize_policy_helper_regression_envelope = tasks_policy_helper_runtime.normalize_policy_helper_regression_envelope
_is_policy_helper_regression_payload = tasks_policy_helper_runtime.is_policy_helper_regression_payload
_enrich_policy_helper_smoke_result = tasks_policy_helper_runtime.enrich_policy_helper_smoke_result
_load_report_payload = tasks_policy_helper_runtime.load_report_payload
_policy_helper_combo_ids = tasks_policy_helper_runtime.policy_helper_combo_ids
_extract_option_values = tasks_policy_helper_runtime.extract_option_values
_policy_helper_summary_suffix = tasks_policy_helper_runtime.policy_helper_summary_suffix


_normalize_argv = tasks_facade_runtime.normalize_argv
_dedupe_compact_items = tasks_facade_runtime.dedupe_compact_items
_relative_task_path = tasks_facade_runtime.relative_task_path
_tool_payload_path_candidates = tasks_facade_runtime.tool_payload_path_candidates
_teammate_modified_files = tasks_facade_runtime.teammate_modified_files
_teammate_commands = tasks_facade_runtime.teammate_commands
_teammate_test_commands = tasks_facade_runtime.teammate_test_commands
_parse_path_list = tasks_facade_runtime.parse_path_list
_task_timeout_seconds = tasks_facade_runtime.task_timeout_seconds
_timeout_error_text = tasks_facade_runtime.timeout_error_text
_mapping_dict = tasks_facade_runtime.mapping_dict
_response_status_mapping = tasks_facade_runtime.response_status_mapping
_route_report_from_status = tasks_facade_runtime.route_report_from_status
_bootstrap_diagnostic_artifact_fields = tasks_facade_runtime.bootstrap_diagnostic_artifact_fields
_bootstrap_failure_error = tasks_facade_runtime.bootstrap_failure_error
_normalize_policy_path = tasks_facade_runtime.normalize_policy_path
_find_git_root = tasks_support_runtime.find_git_root
_capture_command_output = tasks_support_runtime.capture_command_output
_git_repo_state = tasks_support_runtime.git_repo_state
_path_matches_rule = tasks_support_runtime.path_matches_rule
_stage_workspace_ignore = tasks_support_runtime.stage_workspace_ignore
_workspace_file_index = tasks_support_runtime.workspace_file_index
_benchmark_success_summary = tasks_support_runtime.benchmark_success_summary
_smoke_success_summary = tasks_support_runtime.smoke_success_summary
_trim_error = tasks_facade_runtime.trim_error
_decode_json_text = tasks_facade_runtime.decode_json_text
_load_review_payload = tasks_facade_runtime.load_review_payload
_persist_updated_result = tasks_facade_runtime.persist_updated_result


def _normalize_smoke_kind(payload: dict[str, Any]) -> str:
    return tasks_facade_runtime.normalize_smoke_kind(payload, smoke_kind_scripts=_SMOKE_KIND_SCRIPTS)


def _collect_bootstrap_diagnostics(cwd: Path) -> dict[str, Any]:
    return tasks_facade_runtime.collect_bootstrap_diagnostics(
        cwd,
        bootstrap_dependency_files=_BOOTSTRAP_DEPENDENCY_FILES,
    )


_background_terminal_state = tasks_delegates_runtime.background_terminal_state
_paths_outside_policy = tasks_delegates_runtime.paths_outside_policy
_prepare_stage_workspace = tasks_delegates_runtime.prepare_stage_workspace
_diff_preview = tasks_delegates_runtime.diff_preview
_collect_workspace_changes = tasks_delegates_runtime.collect_workspace_changes
_teammate_review_commands = tasks_delegates_runtime.teammate_review_commands
_worker_heartbeat_callback = tasks_delegates_runtime.worker_heartbeat_callback
_consume_teammate_stdout_line = tasks_delegates_runtime.consume_teammate_stdout_line
_ensure_teammate_running_snapshot = tasks_delegates_runtime.ensure_teammate_running_snapshot
apply_staged_teammate_result = tasks_delegates_runtime.apply_staged_teammate_result
reject_staged_teammate_result = tasks_delegates_runtime.reject_staged_teammate_result

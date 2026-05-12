from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from . import tasks_execution_result_runtime
from . import tasks_execution_staged_result_runtime as tasks_execution_staged_result_runtime_service
from . import tasks_execution_teammate_result_runtime as teammate_result_runtime
from .models import BackgroundTaskStatus, TaskResult


def teammate_running_snapshot_metadata(*, results_dir: Path, task_id: str) -> dict[str, Any]:
    return tasks_execution_staged_result_runtime_service.teammate_running_snapshot_metadata(
        results_dir=results_dir,
        task_id=task_id,
    )


def build_teammate_bootstrap_failure_result(
    *,
    envelope: Any,
    storage: Any,
    started_at: str,
    retry_count: int,
    task_text: str,
    live_cwd: Path,
    allowed_paths: list[str],
    blocked_paths: list[str],
    staged_workspace: bool,
    timeout_seconds: float | None,
    provider: str,
    model: str,
    reasoning_effort: str,
    bootstrap_artifact: dict[str, Any],
    error_text: str,
    subprocess_progress_payload_fn: Callable[..., dict[str, Any]],
    background_terminal_state_fn: Callable[..., str],
    subprocess_artifact_fn: Callable[[dict[str, Any]], dict[str, Any]],
    task_artifact_fn: Callable[..., dict[str, Any]],
    utc_now_iso_fn: Callable[[], str],
) -> TaskResult:
    finished_at = utc_now_iso_fn()
    summary = "teammate workspace bootstrap failed"
    progress_payload = subprocess_progress_payload_fn(
        title="teammate workspace bootstrap",
        goal=task_text,
        command=[],
        returncode=2,
        started_at=started_at,
        finished_at=finished_at,
        status=BackgroundTaskStatus.FAILED,
        summary=summary,
        error=error_text,
    )
    terminal_state = background_terminal_state_fn(
        status=BackgroundTaskStatus.FAILED,
        cancelled=False,
        timed_out=False,
    )
    snapshot_payload = tasks_execution_result_runtime.bootstrap_snapshot_payload(
        envelope=envelope,
        status=BackgroundTaskStatus.FAILED,
        task_text=task_text,
        live_cwd=live_cwd,
        allowed_paths=allowed_paths,
        blocked_paths=blocked_paths,
        staged_workspace=staged_workspace,
        timeout_seconds=timeout_seconds,
        bootstrap_artifact=bootstrap_artifact,
        progress_payload=progress_payload,
        terminal_state=terminal_state,
    )
    snapshot_path = storage.write_result_snapshot(envelope.task_id, snapshot_payload, suffix="teammate")
    artifact = task_artifact_fn(
        envelope,
        queue_state=BackgroundTaskStatus.FAILED.value,
        cancel_requested=False,
        extra={
            "snapshot_path": str(snapshot_path),
            **tasks_execution_result_runtime.bootstrap_artifact_extra(
                provider=provider,
                model=model,
                reasoning_effort=reasoning_effort,
                live_cwd=live_cwd,
                allowed_paths=allowed_paths,
                blocked_paths=blocked_paths,
                staged_workspace=staged_workspace,
                timed_out=False,
                timeout_seconds=timeout_seconds,
                terminal_state=terminal_state,
                bootstrap_artifact=bootstrap_artifact,
                subprocess_artifact=subprocess_artifact_fn(progress_payload),
            ),
        },
    )
    return TaskResult(
        task_id=envelope.task_id,
        status=BackgroundTaskStatus.FAILED,
        started_at=started_at,
        finished_at=finished_at,
        summary=summary,
        artifact=artifact,
        error=error_text,
        retry_count=retry_count,
    )


def build_teammate_task_result(
    *,
    envelope: Any,
    storage: Any,
    run: Any,
    started_at: str,
    finished_at: str,
    retry_count: int,
    status: BackgroundTaskStatus,
    summary: str,
    error_text: str,
    task_text: str,
    response_payload: dict[str, Any] | None,
    provider: str,
    model: str,
    reasoning_effort: str,
    live_cwd: Path,
    allowed_paths: list[str],
    blocked_paths: list[str],
    staged_workspace: bool,
    bootstrap_artifact: dict[str, Any],
    response_status: dict[str, Any],
    protocol_diagnostics: dict[str, Any],
    route_report: dict[str, Any],
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
    stage_cwd: Path | None,
    review_path: str,
    assistant_text: str,
    commentary_preview_text: str,
    subprocess_progress_payload_fn: Callable[..., dict[str, Any]],
    background_terminal_state_fn: Callable[..., str],
    subprocess_artifact_fn: Callable[[dict[str, Any]], dict[str, Any]],
    task_artifact_fn: Callable[..., dict[str, Any]],
    trim_error_fn: Callable[..., str],
) -> TaskResult:
    running_snapshot_metadata = teammate_running_snapshot_metadata(
        results_dir=storage.results_dir,
        task_id=envelope.task_id,
    )
    progress_payload = subprocess_progress_payload_fn(
        title="teammate headless turn",
        goal=task_text,
        command=run.command,
        returncode=run.returncode,
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        summary=summary,
        error=error_text,
    )
    terminal_state = background_terminal_state_fn(
        status=status,
        cancelled=bool(run.cancelled),
        timed_out=bool(run.timed_out),
    )
    response_path = storage.write_result_snapshot(
        envelope.task_id,
        response_payload if isinstance(response_payload, dict) else {"stdout": run.stdout},
        suffix="teammate_response",
    )
    snapshot_payload = tasks_execution_result_runtime.teammate_snapshot_payload(
        envelope=envelope,
        status=status,
        task_text=task_text,
        run=run,
        response_path=str(response_path),
        live_cwd=live_cwd,
        allowed_paths=allowed_paths,
        blocked_paths=blocked_paths,
        staged_workspace=staged_workspace,
        terminal_state=terminal_state,
        tool_event_names=tool_event_names,
        modified_files=modified_files,
        commands=commands,
        test_commands=test_commands,
        command_policies=command_policies,
        final_apply_pending=final_apply_pending,
        final_apply_state=final_apply_state,
        out_of_scope_files=out_of_scope_files,
        review_commands=review_commands,
        stream_event_count=stream_event_count,
        progress_payload=progress_payload,
        bootstrap_artifact=bootstrap_artifact,
    )
    snapshot_payload = teammate_result_runtime.enrich_snapshot_payload(
        snapshot_payload=snapshot_payload,
        response_payload=response_payload,
        protocol_diagnostics=protocol_diagnostics,
        response_status=response_status,
        route_report=route_report,
        stage_cwd=stage_cwd,
        review_path=review_path,
        run_stdout_path=run.stdout_path,
        run_stderr_path=run.stderr_path,
        running_snapshot_metadata=running_snapshot_metadata,
    )
    snapshot_path = storage.write_result_snapshot(envelope.task_id, snapshot_payload, suffix="teammate")
    artifact = task_artifact_fn(
        envelope,
        queue_state=status.value,
        cancel_requested=False,
        extra=tasks_execution_result_runtime.teammate_artifact_extra(
            response_path=str(response_path),
            snapshot_path=str(snapshot_path),
            provider=provider,
            model=model,
            reasoning_effort=reasoning_effort,
            tool_event_names=tool_event_names,
            modified_files=modified_files,
            commands=commands,
            test_commands=test_commands,
            command_policies=command_policies,
            live_cwd=live_cwd,
            allowed_paths=allowed_paths,
            blocked_paths=blocked_paths,
            staged_workspace=staged_workspace,
            run=run,
            terminal_state=terminal_state,
            response_status=response_status,
            route_report=route_report,
            final_apply_pending=final_apply_pending,
            final_apply_state=final_apply_state,
            out_of_scope_files=out_of_scope_files,
            review_commands=review_commands,
            stream_event_count=stream_event_count,
            bootstrap_artifact=bootstrap_artifact,
            subprocess_artifact=subprocess_artifact_fn(progress_payload),
            running_snapshot_metadata=running_snapshot_metadata,
        ),
    )
    artifact = teammate_result_runtime.enrich_artifact(
        artifact=artifact,
        response_payload=response_payload,
        assistant_text=assistant_text,
        commentary_preview_text=commentary_preview_text,
        stage_cwd=stage_cwd,
        review_path=review_path,
        run_stdout_path=run.stdout_path,
        run_stderr_path=run.stderr_path,
        trim_error_fn=trim_error_fn,
    )
    return TaskResult(
        task_id=envelope.task_id,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        summary=summary,
        artifact=artifact,
        error=error_text,
        retry_count=retry_count,
    )

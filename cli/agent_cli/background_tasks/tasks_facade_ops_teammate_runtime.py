from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from . import tasks_execution_runtime
from . import tasks_facade_ops_teammate_helpers_runtime
from . import tasks_flow_runtime
from . import tasks_stream_runtime
from . import tasks_teammate_flow_runtime
from . import tasks_teammate_runtime
from .models import TaskEnvelope, TaskResult, utc_now_iso
from .queue_runtime import _subprocess_artifact, _subprocess_progress_payload, _task_artifact
from .storage import BackgroundTaskStorage


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
    payload = dict(envelope.payload or {})
    teammate_request = tasks_execution_runtime.normalize_teammate_request(
        payload=payload,
        metadata=envelope.metadata,
        workspace_root=workspace_root,
        parse_path_list_fn=parse_path_list_fn,
        dedupe_compact_items_fn=dedupe_compact_items_fn,
        normalize_policy_path_fn=normalize_policy_path_fn,
        task_timeout_seconds_fn=task_timeout_seconds_fn,
    )
    task_text = str(teammate_request["task_text"] or "")
    if not task_text:
        raise ValueError("teammate task requires payload.task")
    live_cwd = teammate_request["live_cwd"]
    provider = str(teammate_request["provider"] or "")
    model = str(teammate_request["model"] or "")
    reasoning_effort = str(teammate_request["reasoning_effort"] or "")
    sandbox_mode = str(teammate_request["sandbox_mode"] or "read-only")
    allowed_paths = list(teammate_request["allowed_paths"] or [])
    blocked_paths = list(teammate_request["blocked_paths"] or [])
    timeout_seconds = teammate_request["timeout_seconds"]
    staged_workspace = bool(teammate_request["staged_workspace"])
    bootstrap_diagnostics = collect_bootstrap_diagnostics_fn(
        live_cwd,
        bootstrap_dependency_files=bootstrap_dependency_files,
    )
    bootstrap_artifact = bootstrap_diagnostic_artifact_fields_fn(bootstrap_diagnostics)
    bootstrap_error_category = str(bootstrap_diagnostics.get("bootstrap_error_category") or "").strip()
    if bootstrap_error_category:
        return tasks_execution_runtime.build_teammate_bootstrap_failure_result(
            envelope=envelope,
            storage=storage,
            started_at=started_at,
            retry_count=retry_count,
            task_text=task_text,
            live_cwd=live_cwd,
            allowed_paths=allowed_paths,
            blocked_paths=blocked_paths,
            staged_workspace=staged_workspace,
            timeout_seconds=timeout_seconds,
            provider=provider,
            model=model,
            reasoning_effort=reasoning_effort,
            bootstrap_artifact=bootstrap_artifact,
            error_text=bootstrap_failure_error_fn(bootstrap_diagnostics),
            subprocess_progress_payload_fn=_subprocess_progress_payload,
            background_terminal_state_fn=background_terminal_state_fn,
            subprocess_artifact_fn=_subprocess_artifact,
            task_artifact_fn=_task_artifact,
            utc_now_iso_fn=utc_now_iso,
        )
    stage_cwd = prepare_stage_workspace_fn(envelope.task_id, source_root=live_cwd, storage=storage) if staged_workspace else None
    execution_cwd = stage_cwd or live_cwd
    response_sidecar_path = storage.results_dir / f"{envelope.task_id}_teammate_response.json"
    subprocess_request = tasks_stream_runtime.build_teammate_subprocess_request(
        cli_root=cli_root,
        payload=payload,
        sandbox_mode=sandbox_mode,
        task_text=task_text,
        provider=provider,
        model=model,
        reasoning_effort=reasoning_effort,
        response_sidecar_path=response_sidecar_path,
        os_environ=dict(os.environ),
        python_executable=sys.executable,
        response_path_env_name=headless_response_path_env,
    )
    stream_state = tasks_teammate_runtime.new_headless_jsonl_state()
    stream_progress = {"last_persist_monotonic": 0.0}
    from .tasks import _run_logged_subprocess

    run = _run_logged_subprocess(
        envelope,
        command=subprocess_request["command"],
        cwd=execution_cwd,
        env=subprocess_request["env"],
        storage=storage,
        runner_token=runner_token,
        log_prefix="teammate",
        timeout_seconds=timeout_seconds,
        stdout_line_callback=lambda line: consume_teammate_stdout_line_fn(
            line,
            state=stream_state,
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
        ),
        heartbeat_callback=worker_heartbeat_callback_fn(
            storage=storage,
            envelope=envelope,
            on_heartbeat_callback=lambda: ensure_teammate_running_snapshot_fn(
                state=stream_state,
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
            ),
        ),
    )
    finished_at = utc_now_iso()
    response_payload = tasks_stream_runtime.load_headless_response_payload(
        response_sidecar_path=response_sidecar_path,
        stdout_text=run.stdout,
        stream_state=stream_state,
        decode_json_text_fn=decode_json_text_fn,
        synthetic_response_payload_fn=tasks_teammate_runtime.synthetic_response_payload_from_jsonl_state,
    )
    finalized = tasks_teammate_flow_runtime.finalize_teammate_run_state(
        envelope_task_id=envelope.task_id,
        run=run,
        response_payload=response_payload,
        stream_state=stream_state,
        staged_workspace=staged_workspace,
        stage_cwd=stage_cwd,
        task_text=task_text,
        live_cwd=live_cwd,
        bootstrap_diagnostics=bootstrap_diagnostics,
        allowed_paths=allowed_paths,
        blocked_paths=blocked_paths,
        collect_workspace_changes_fn=collect_workspace_changes_fn,
        teammate_response_projection_fn=tasks_teammate_runtime.teammate_response_projection,
        staged_review_projection_fn=tasks_teammate_runtime.staged_review_projection,
        teammate_task_outcome_fn=tasks_teammate_runtime.teammate_task_outcome,
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
        running_summary_text_fn=tasks_teammate_runtime.running_summary_text,
    )
    review_payload = dict(finalized["review_payload"] or {}) if isinstance(finalized.get("review_payload"), dict) else None
    review_path = ""
    if review_payload is not None:
        review_payload["final_apply_pending"] = bool(finalized["final_apply_pending"])
        review_payload["final_apply_state"] = str(finalized["final_apply_state"] or "")
        review_payload["review_commands"] = list(finalized["review_commands"] or [])
        review_path = str(storage.write_result_snapshot(envelope.task_id, review_payload, suffix="teammate_review"))
    return tasks_execution_runtime.build_teammate_task_result(
        envelope=envelope,
        storage=storage,
        run=run,
        started_at=started_at,
        finished_at=finished_at,
        retry_count=retry_count,
        status=finalized["status"],
        summary=str(finalized["summary"] or ""),
        error_text=str(finalized["error_text"] or ""),
        task_text=task_text,
        response_payload=response_payload if isinstance(response_payload, dict) else None,
        provider=provider,
        model=model,
        reasoning_effort=reasoning_effort,
        live_cwd=live_cwd,
        allowed_paths=allowed_paths,
        blocked_paths=blocked_paths,
        staged_workspace=staged_workspace,
        bootstrap_artifact=bootstrap_artifact,
        response_status=dict(finalized["response_status"] or {}),
        protocol_diagnostics=dict(finalized["protocol_diagnostics"] or {}),
        route_report=dict(finalized["route_report"] or {}),
        tool_event_names=list(finalized["tool_event_names"] or []),
        modified_files=list(finalized["modified_files"] or []),
        commands=list(finalized["commands"] or []),
        test_commands=list(finalized["test_commands"] or []),
        command_policies=list(finalized.get("command_policies") or []),
        final_apply_pending=bool(finalized["final_apply_pending"]),
        final_apply_state=str(finalized["final_apply_state"] or ""),
        out_of_scope_files=list(finalized["out_of_scope_files"] or []),
        review_commands=list(finalized["review_commands"] or []),
        stream_event_count=int(stream_state.get("event_count") or 0),
        stage_cwd=stage_cwd,
        review_path=review_path,
        assistant_text=str(finalized["assistant_text"] or ""),
        commentary_preview_text=str(finalized["commentary_preview_text"] or ""),
        subprocess_progress_payload_fn=_subprocess_progress_payload,
        background_terminal_state_fn=background_terminal_state_fn,
        subprocess_artifact_fn=_subprocess_artifact,
        task_artifact_fn=_task_artifact,
        trim_error_fn=trim_error_fn,
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
    return tasks_facade_ops_teammate_helpers_runtime.apply_staged_teammate_result(
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
    current = storage.get_result(task_id)
    if current is None:
        return None
    artifact = dict(current.artifact or {})
    if not artifact.get("staged_workspace"):
        return current
    if str(artifact.get("final_apply_state") or "").strip() in {"applied", "rejected"}:
        return current
    rejected_at = utc_now_iso()
    result = tasks_execution_runtime.build_staged_reject_result(
        current=current,
        artifact=artifact,
        rejected_at=rejected_at,
    )
    review_path = str(artifact.get("review_path") or "").strip()
    if review_path:
        review_payload = load_review_payload_fn(review_path)
        storage.write_result_snapshot(
            task_id,
            tasks_flow_runtime.updated_review_payload(
                review_payload,
                final_apply_pending=False,
                final_apply_state="rejected",
                review_commands=[],
                final_apply_decided_at=rejected_at,
            ),
            suffix="teammate_review",
        )
    return persist_updated_result_fn(storage, result)

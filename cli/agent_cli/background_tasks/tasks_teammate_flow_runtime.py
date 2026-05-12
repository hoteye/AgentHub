from __future__ import annotations

from typing import Any, Callable


def finalize_teammate_run_state(
    *,
    envelope_task_id: str,
    run: Any,
    response_payload: dict[str, Any],
    stream_state: dict[str, Any],
    staged_workspace: bool,
    stage_cwd: Any,
    task_text: str,
    live_cwd: Any,
    bootstrap_diagnostics: dict[str, Any],
    allowed_paths: list[str],
    blocked_paths: list[str],
    collect_workspace_changes_fn: Callable[[Any, Any], list[dict[str, Any]]],
    teammate_response_projection_fn: Callable[..., dict[str, Any]],
    staged_review_projection_fn: Callable[..., dict[str, Any]],
    teammate_task_outcome_fn: Callable[..., dict[str, Any]],
    response_status_mapping_fn: Callable[[Any], dict[str, Any]],
    mapping_dict_fn: Callable[[Any], dict[str, Any]],
    route_report_from_status_fn: Callable[[dict[str, Any]], dict[str, Any]],
    teammate_commands_fn: Callable[[dict[str, Any]], list[str]],
    teammate_test_commands_fn: Callable[[list[str]], list[str]],
    teammate_modified_files_fn: Callable[[dict[str, Any], Any], list[str]],
    paths_outside_policy_fn: Callable[..., list[str]],
    teammate_review_commands_fn: Callable[[str, bool], list[str]],
    trim_error_fn: Callable[..., str],
    timeout_error_text_fn: Callable[[str, float | None], str],
    running_summary_text_fn: Callable[[dict[str, Any]], str],
) -> dict[str, Any]:
    response_projection = teammate_response_projection_fn(
        response_payload=response_payload,
        live_cwd=live_cwd,
        response_status_mapping_fn=response_status_mapping_fn,
        mapping_dict_fn=mapping_dict_fn,
        route_report_from_status_fn=route_report_from_status_fn,
        teammate_commands_fn=teammate_commands_fn,
        teammate_test_commands_fn=teammate_test_commands_fn,
        teammate_modified_files_fn=teammate_modified_files_fn,
    )
    assistant_text = str(response_projection["assistant_text"] or "")
    commentary_preview_text = str((response_payload or {}).get("commentary_text") or "").strip()
    if not commentary_preview_text:
        commentary_preview_text = running_summary_text_fn(stream_state)
    tool_event_names = list(response_projection["tool_event_names"] or [])
    modified_files = list(response_projection["modified_files"] or [])
    commands = list(response_projection["commands"] or [])
    test_commands = list(response_projection["test_commands"] or [])
    command_policies = list(response_projection.get("command_policies") or [])
    response_status = dict(response_projection["response_status"] or {})
    protocol_diagnostics = dict(response_projection["protocol_diagnostics"] or {})
    route_report = dict(response_projection["route_report"] or {})
    review_payload: dict[str, Any] | None = None
    final_apply_pending = False
    final_apply_state = ""
    out_of_scope_files: list[str] = []
    review_commands: list[str] = []
    if staged_workspace and stage_cwd is not None:
        workspace_changes = collect_workspace_changes_fn(live_cwd, stage_cwd)
        review_projection = staged_review_projection_fn(
            envelope_task_id=envelope_task_id,
            task_text=task_text,
            live_cwd=live_cwd,
            stage_cwd=stage_cwd,
            bootstrap_diagnostics=bootstrap_diagnostics,
            route_report=route_report,
            allowed_paths=allowed_paths,
            blocked_paths=blocked_paths,
            commands=commands,
            test_commands=test_commands,
            workspace_changes=workspace_changes,
            paths_outside_policy_fn=paths_outside_policy_fn,
            teammate_review_commands_fn=teammate_review_commands_fn,
        )
        modified_files = list(review_projection["modified_files"] or [])
        out_of_scope_files = list(review_projection["out_of_scope_files"] or [])
        final_apply_pending = bool(review_projection["final_apply_pending"])
        final_apply_state = str(review_projection["final_apply_state"] or "")
        review_commands = list(review_projection["review_commands"] or [])
        review_payload = dict(review_projection["review_payload"] or {})
    outcome = teammate_task_outcome_fn(
        task_id=envelope_task_id,
        run=run,
        assistant_text=assistant_text,
        staged_workspace=staged_workspace,
        out_of_scope_files=out_of_scope_files,
        final_apply_pending=final_apply_pending,
        final_apply_state=final_apply_state,
        modified_files=modified_files,
        trim_error_fn=trim_error_fn,
        timeout_error_text_fn=timeout_error_text_fn,
    )
    final_apply_pending = bool(outcome["final_apply_pending"])
    final_apply_state = str(outcome["final_apply_state"] or "")
    if outcome["review_commands"]:
        review_commands = list(outcome["review_commands"] or [])
    return {
        "assistant_text": assistant_text,
        "commentary_preview_text": commentary_preview_text,
        "tool_event_names": tool_event_names,
        "modified_files": modified_files,
        "commands": commands,
        "test_commands": test_commands,
        "command_policies": command_policies,
        "response_status": response_status,
        "protocol_diagnostics": protocol_diagnostics,
        "route_report": route_report,
        "review_payload": review_payload,
        "summary": str(outcome["summary"] or ""),
        "status": outcome["status"],
        "error_text": str(outcome["error_text"] or ""),
        "final_apply_pending": final_apply_pending,
        "final_apply_state": final_apply_state,
        "out_of_scope_files": out_of_scope_files,
        "review_commands": review_commands,
    }

from __future__ import annotations

from typing import Any, Callable

from cli.agent_cli.runtime_core.background_task_commands_text_helpers_runtime import (
    append_bootstrap_lines as _append_bootstrap_lines,
    append_lifecycle_lines as _append_lifecycle_lines,
    append_observability_surface_lines as _append_observability_surface_lines,
    observability_trace_from_route_report as _observability_trace_from_route_report,
)


_BOOL_TRUE = {"1", "true", "yes", "on"}
_BOOL_FALSE = {"0", "false", "no", "off"}
_EVIDENCE_PENDING_REVIEW_NEXT_ACTIONS = {
    "manual_review_required",
    "review_or_adopt_teammate_result",
    "wait_agent_to_adopt",
}
_EVIDENCE_BLOCKED_NEXT_ACTIONS = {
    "execution_cancelled",
    "execution_failed",
    "execution_failed_with_blockers",
    "execution_timed_out",
    "failure_observed",
    "inspect_error_or_retry",
    "inspect_or_retry_empty_result",
}
_EVIDENCE_ADOPTED_NEXT_ACTIONS = {"already_adopted"}
_EVIDENCE_PENDING_REVIEW_COMPLETION_STATES = {"awaiting_join", "pending_review"}
_STATUS_SCALAR_KEYS = ("status", "task_type", "queue_state", "summary", "error")
_STRUCTURED_STATE_KEYS = (
    "result_state",
    "completion_state",
    "adoption_expectation",
    "notification_state",
    "terminal_state",
    "terminal_reason",
)
_ARTIFACT_SCALAR_KEYS = (
    "report_path",
    "response_path",
    "snapshot_path",
    "running_snapshot_path",
    "review_path",
    "provider",
    "model",
    "reasoning_effort",
    "timeout_seconds",
    "live_cwd",
    "stage_cwd",
    "queue_source_of_truth",
    "queue_provider",
    "runtime_provider_name",
    "runtime_provider_model",
    "runtime_timing_summary",
    "wall_time_ms",
    "current_step_wall_time_ms",
    "timeout_budget_seconds",
    "last_wait_blocked_ms",
    "timeout_reason",
    "timeout_source",
    "last_wait_decision",
    "last_wait_reason",
    "last_wait_at",
    "foreground_taken_over_at",
    "policy_helper_profile",
    "policy_helper_helper_combo_count",
)
_ARTIFACT_BOOL_KEYS = ("staged_workspace", "final_apply_pending", "timed_out", "timeout_hit", "last_wait_timed_out")


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _structured_text_value(value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    return str(value).strip()


def _structured_state_value(*sources: dict[str, Any], key: str) -> str:
    for source in sources:
        if not isinstance(source, dict):
            continue
        value = _structured_text_value(source.get(key))
        if value:
            return value
    return ""


def _structured_bool_value(*sources: dict[str, Any], key: str) -> bool | None:
    for source in sources:
        if not isinstance(source, dict) or key not in source:
            continue
        value = source.get(key)
        if isinstance(value, bool):
            return value
        text = str(value or "").strip().lower()
        if text in _BOOL_TRUE:
            return True
        if text in _BOOL_FALSE:
            return False
        if value in (None, "", [], {}):
            return None
        return bool(value)
    return None


def _structured_lower_state_value(*sources: dict[str, Any], key: str) -> str:
    return _structured_state_value(*sources, key=key).lower()


def _background_evidence_result_state(
    *,
    payload: dict[str, Any],
    lifecycle: dict[str, Any],
    artifact: dict[str, Any],
    result: dict[str, Any],
    result_artifact: dict[str, Any],
) -> str:
    structured_sources = (lifecycle, payload, artifact, result_artifact, result)
    status = str(payload.get("status") or "").strip().lower()
    terminal_state = _structured_lower_state_value(*structured_sources, key="terminal_state") or status
    explicit_state = _structured_lower_state_value(*structured_sources, key="result_state")
    completion_state = _structured_lower_state_value(*structured_sources, key="completion_state")
    next_action = _structured_lower_state_value(*structured_sources, key="adoption_expectation")
    notification_state = _structured_lower_state_value(*structured_sources, key="notification_state")
    final_apply_state = _structured_lower_state_value(*structured_sources, key="final_apply_state")
    task_type = _structured_lower_state_value(*structured_sources, key="task_type")
    adopted = _structured_bool_value(*structured_sources, key="adopted") is True
    final_apply_pending = final_apply_state == "pending" or _structured_bool_value(
        *structured_sources,
        key="final_apply_pending",
    ) is True

    blocked = (
        explicit_state in {"blocked", "block", "rejected", "reject"}
        or final_apply_state in {"blocked", "rejected"}
        or next_action in _EVIDENCE_BLOCKED_NEXT_ACTIONS
        or terminal_state in {"failed", "timed_out", "cancelled"}
    )
    if blocked:
        return "blocked"

    pending_review = (
        explicit_state in {"pending_review", "review_pending"}
        or final_apply_pending
        or next_action in _EVIDENCE_PENDING_REVIEW_NEXT_ACTIONS
        or completion_state in _EVIDENCE_PENDING_REVIEW_COMPLETION_STATES
        or (completion_state == "ready_to_adopt" and task_type == "teammate")
    )
    if pending_review:
        return "pending_review"

    adopted_signal = (
        explicit_state == "adopted"
        or adopted
        or completion_state == "adopted"
        or next_action in _EVIDENCE_ADOPTED_NEXT_ACTIONS
        or notification_state == "foreground_adopted"
        or final_apply_state == "applied"
    )
    if adopted_signal:
        return "adopted"

    if explicit_state == "returned":
        return "returned"
    if completion_state == "ready_to_adopt":
        return "returned"
    if terminal_state == "completed" or status == "completed":
        return "returned"
    return "pending"


def _append_payload_scalar_lines(lines: list[str], payload: dict[str, Any]) -> None:
    for key in _STATUS_SCALAR_KEYS:
        value = str(payload.get(key) or "").strip()
        if value:
            lines.append(f"{key}={value}")
    if payload.get("dispatch_id") not in (None, "", 0):
        lines.append(f"dispatch_id={payload['dispatch_id']}")
    lines.append(f"cancel_requested={'true' if payload.get('cancel_requested') else 'false'}")
    if payload.get("runner_pid") not in (None, "", 0):
        lines.append(f"runner_pid={payload['runner_pid']}")
    if payload.get("retry_count") not in (None, ""):
        lines.append(f"retry_count={payload['retry_count']}")


def _status_payload_parts(
    payload: dict[str, Any],
    *,
    mapping_fn: Callable[[Any], dict[str, Any]],
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]],
]:
    lifecycle = mapping_fn(payload.get("lifecycle"))
    result = mapping_fn(payload.get("result"))
    result_artifact = mapping_fn(result.get("artifact"))
    artifact = mapping_fn(payload.get("artifact"))
    if not artifact and result_artifact:
        artifact = dict(result_artifact)
    structured_sources = (lifecycle, payload, artifact, result_artifact, result)
    return lifecycle, result, result_artifact, artifact, structured_sources


def _append_structured_state_lines(
    lines: list[str],
    *,
    payload: dict[str, Any],
    lifecycle: dict[str, Any],
    result: dict[str, Any],
    result_artifact: dict[str, Any],
    artifact: dict[str, Any],
    structured_sources: tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]],
    structured_state_value_fn: Callable[..., str],
    structured_bool_value_fn: Callable[..., bool | None],
    background_evidence_result_state_fn: Callable[..., str],
) -> None:
    for key in _STRUCTURED_STATE_KEYS:
        value = structured_state_value_fn(*structured_sources, key=key)
        if value:
            lines.append(f"{key}={value}")
    final_apply_state = structured_state_value_fn(*structured_sources, key="final_apply_state")
    if not final_apply_state and structured_bool_value_fn(*structured_sources, key="final_apply_pending") is True:
        final_apply_state = "pending"
    if final_apply_state:
        lines.append(f"final_apply_state={final_apply_state}")
    adopted = structured_bool_value_fn(*structured_sources, key="adopted")
    if adopted is not None:
        lines.append(f"adopted={'true' if adopted else 'false'}")
    evidence_result_state = background_evidence_result_state_fn(
        payload=payload,
        lifecycle=lifecycle,
        artifact=artifact,
        result=result,
        result_artifact=result_artifact,
    )
    if evidence_result_state:
        lines.append(f"evidence_result_state={evidence_result_state}")


def _append_initial_tenant_scope_lines(
    lines: list[str],
    *,
    payload: dict[str, Any],
    lifecycle: dict[str, Any],
) -> tuple[str, str, bool, bool]:
    tenant_id = str(payload.get("tenant_id") or lifecycle.get("tenant_id") or "").strip()
    workspace_scope = str(payload.get("workspace_scope") or lifecycle.get("workspace_scope") or "").strip()
    has_tenant_id = False
    has_workspace_scope = False
    if tenant_id:
        lines.append(f"tenant_id={tenant_id}")
        has_tenant_id = True
    if workspace_scope:
        lines.append(f"workspace_scope={workspace_scope}")
        has_workspace_scope = True
    return tenant_id, workspace_scope, has_tenant_id, has_workspace_scope


def _tenant_scope_profile(tenant_id: str, workspace_scope: str) -> str:
    if tenant_id.strip().lower() == "default" and workspace_scope.strip().lower() == "default":
        return "default"
    return "isolated"


def _append_tenant_scope_profile_line(lines: list[str], *, tenant_id: str, workspace_scope: str) -> None:
    if tenant_id or workspace_scope:
        lines.append(f"tenant_scope_profile={_tenant_scope_profile(tenant_id, workspace_scope)}")


def _append_artifact_scalar_lines(lines: list[str], artifact: dict[str, Any]) -> None:
    for key in _ARTIFACT_SCALAR_KEYS:
        value = str(artifact.get(key) or "").strip()
        if value:
            lines.append(f"{key}={value}")


def _append_artifact_tenant_scope_lines(
    lines: list[str],
    *,
    artifact: dict[str, Any],
    tenant_id: str,
    workspace_scope: str,
    has_tenant_id: bool,
    has_workspace_scope: bool,
) -> tuple[str, str, bool, bool]:
    if not has_tenant_id:
        artifact_tenant_id = str(artifact.get("tenant_id") or "").strip()
        if artifact_tenant_id:
            lines.append(f"tenant_id={artifact_tenant_id}")
            has_tenant_id = True
    if not has_workspace_scope:
        artifact_workspace_scope = str(artifact.get("workspace_scope") or "").strip()
        if artifact_workspace_scope:
            lines.append(f"workspace_scope={artifact_workspace_scope}")
            workspace_scope = artifact_workspace_scope
            has_workspace_scope = True
    if not has_tenant_id:
        tenant_id = ""
    if not has_workspace_scope:
        workspace_scope = ""
    return tenant_id, workspace_scope, has_tenant_id, has_workspace_scope


def _append_artifact_process_lines(lines: list[str], artifact: dict[str, Any]) -> None:
    for key in ("worker_pid",):
        value = artifact.get(key)
        if value not in (None, "", 0):
            lines.append(f"{key}={value}")


def _append_artifact_bool_lines(
    lines: list[str],
    *,
    structured_sources: tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]],
    structured_bool_value_fn: Callable[..., bool | None],
) -> None:
    for key in _ARTIFACT_BOOL_KEYS:
        value = structured_bool_value_fn(*structured_sources, key=key)
        if value is not None:
            lines.append(f"{key}={'true' if value else 'false'}")


def background_task_status_text(
    payload: dict[str, Any],
    *,
    task_id: str,
    mapping_fn: Callable[[Any], dict[str, Any]] = _mapping,
    structured_state_value_fn: Callable[..., str] = _structured_state_value,
    structured_bool_value_fn: Callable[..., bool | None] = _structured_bool_value,
    background_evidence_result_state_fn: Callable[..., str] = _background_evidence_result_state,
    append_lifecycle_lines_fn: Callable[..., None] = _append_lifecycle_lines,
    append_bootstrap_lines_fn: Callable[..., None] = _append_bootstrap_lines,
    append_observability_surface_lines_fn: Callable[..., None] = _append_observability_surface_lines,
    observability_trace_from_route_report_fn: Callable[..., dict[str, Any]] = _observability_trace_from_route_report,
) -> str:
    lines = ["background task status", f"task_id={task_id}"]
    _append_payload_scalar_lines(lines, payload)

    lifecycle, result, result_artifact, artifact, structured_sources = _status_payload_parts(
        payload,
        mapping_fn=mapping_fn,
    )
    _append_structured_state_lines(
        lines,
        payload=payload,
        lifecycle=lifecycle,
        result=result,
        result_artifact=result_artifact,
        artifact=artifact,
        structured_sources=structured_sources,
        structured_state_value_fn=structured_state_value_fn,
        structured_bool_value_fn=structured_bool_value_fn,
        background_evidence_result_state_fn=background_evidence_result_state_fn,
    )
    tenant_id, workspace_scope, has_tenant_id, has_workspace_scope = _append_initial_tenant_scope_lines(
        lines,
        payload=payload,
        lifecycle=lifecycle,
    )

    if not artifact:
        _append_tenant_scope_profile_line(lines, tenant_id=tenant_id, workspace_scope=workspace_scope)
        append_lifecycle_lines_fn(lines, lifecycle=lifecycle, payload=payload, artifact={})
        return "\n".join(lines)

    _append_artifact_scalar_lines(lines, artifact)
    tenant_id, workspace_scope, _, _ = _append_artifact_tenant_scope_lines(
        lines,
        artifact=artifact,
        tenant_id=tenant_id,
        workspace_scope=workspace_scope,
        has_tenant_id=has_tenant_id,
        has_workspace_scope=has_workspace_scope,
    )
    _append_tenant_scope_profile_line(lines, tenant_id=tenant_id, workspace_scope=workspace_scope)

    route_trace_payload = observability_trace_from_route_report_fn(artifact)
    append_observability_surface_lines_fn(
        lines,
        artifact=artifact,
        payload=payload,
        trace_payload=route_trace_payload,
    )
    _append_artifact_process_lines(lines, artifact)
    _append_artifact_bool_lines(
        lines,
        structured_sources=structured_sources,
        structured_bool_value_fn=structured_bool_value_fn,
    )
    append_lifecycle_lines_fn(lines, lifecycle=lifecycle, payload=payload, artifact=artifact)

    bootstrap = artifact.get("bootstrap_diagnostics")
    if isinstance(bootstrap, dict):
        append_bootstrap_lines_fn(lines, bootstrap=bootstrap)
    return "\n".join(lines)

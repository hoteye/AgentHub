from __future__ import annotations

from collections.abc import Callable
from typing import Any

from cli.agent_cli.runtime_services import (
    delegated_agent_workflow_render_helpers_runtime as workflow_render_helpers_runtime,
)
from cli.agent_cli.runtime_services import (
    delegated_agent_workflow_render_text_helpers_runtime as workflow_render_text_helpers_runtime,
)
from cli.agent_cli.runtime_services import (
    delegated_agent_workflow_status_runtime as workflow_status_runtime,
)

_ACTIVE_WORKFLOW_STATUSES = workflow_status_runtime.ACTIVE_WORKFLOW_STATUSES
_TERMINAL_WORKFLOW_STATUSES = workflow_status_runtime.TERMINAL_WORKFLOW_STATUSES
_normalized_status = workflow_status_runtime.normalized_status
_normalized_optional_text = workflow_status_runtime.normalized_optional_text
_child_identity_payload = workflow_status_runtime.child_identity_payload
_subagent_status_for_payload = workflow_status_runtime.subagent_status_for_payload
_subagent_protocol_payload = workflow_status_runtime.subagent_protocol_payload
_resolved_session_status = workflow_status_runtime.resolved_session_status
_completion_state_for_status = workflow_status_runtime.completion_state_for_status
_result_state_for_status = workflow_status_runtime.result_state_for_status
_next_action_for_state = workflow_status_runtime.next_action_for_state
_resolved_result_artifact = workflow_status_runtime.resolved_result_artifact


def _command_policy_projection_from_tool_events(tool_events: Any) -> dict[str, Any]:
    return workflow_render_helpers_runtime.command_policy_projection_from_tool_events(
        tool_events,
        normalized_optional_text_fn=_normalized_optional_text,
    )


def _resolve_result_contract(
    result_contract: dict[str, Any],
    *,
    status: str,
    completion_policy: str,
    completion_state: str,
    adopted: bool,
    assistant_text: str,
    error: str,
) -> dict[str, Any]:
    contract = dict(result_contract or {})
    if not contract:
        return contract
    previous_status = _normalized_status(contract.get("status"))
    previous_completion_state = str(contract.get("completion_state") or "").strip().lower()
    previous_artifact_kind = ""
    if isinstance(contract.get("artifact"), dict):
        previous_artifact_kind = str(contract["artifact"].get("kind") or "").strip().lower()
    contract["status"] = status
    contract["completion_policy"] = completion_policy
    contract["completion_state"] = completion_state
    contract_needs_refresh = (
        previous_status != status or previous_completion_state != completion_state
    )
    artifact_needs_refresh = not previous_artifact_kind or (
        previous_artifact_kind == "pending" and status not in _ACTIVE_WORKFLOW_STATUSES
    )
    if contract_needs_refresh:
        contract["next_action"] = _next_action_for_state(
            status=status,
            completion_state=completion_state,
            adopted=adopted,
        )
    if contract_needs_refresh or artifact_needs_refresh:
        contract["artifact"] = _resolved_result_artifact(
            status=status,
            assistant_text=assistant_text,
            error=error,
            current=contract.get("artifact"),
        )
    if contract_needs_refresh:
        if (
            str(contract.get("confidence") or "").strip().lower() == "pending"
            and status not in _ACTIVE_WORKFLOW_STATUSES
        ):
            contract["confidence"] = "low" if status == "failed" else "medium"
        previous_summary = str(contract.get("summary") or "").strip()
        if not previous_summary or previous_status in _ACTIVE_WORKFLOW_STATUSES:
            if status == "completed":
                contract["summary"] = assistant_text or "delegated task completed"
            elif status == "failed":
                contract["summary"] = error or "delegated agent failed"
            elif status == "closed":
                contract["summary"] = (
                    assistant_text or error or "delegated task closed before producing a result"
                )
            elif status in _ACTIVE_WORKFLOW_STATUSES:
                contract["summary"] = f"delegated task {status}"
            else:
                contract["summary"] = "delegated task queued"
    if not str(contract.get("next_action") or "").strip():
        contract["next_action"] = _next_action_for_state(
            status=status,
            completion_state=completion_state,
            adopted=adopted,
        )
    return contract


def apply_scheduler_decision(
    session: Any,
    decision: dict[str, Any],
    *,
    now_iso_fn: Callable[[], str],
) -> dict[str, Any]:
    if session.closed:
        session.scheduler_reason = ""
        return {**decision, "allowed": False, "reason": "session_closed"}
    if session.close_requested and not session.queued_inputs and session.active_input is None:
        session.scheduler_reason = ""
        return {**decision, "allowed": False, "reason": "session_closing"}
    session.parallel_group = str(decision.get("parallel_group") or session.parallel_group or "")
    if decision["allowed"]:
        session.scheduler_reason = ""
        if session.status not in {"closing", "closed"}:
            session.status = "starting"
    else:
        session.scheduler_reason = str(decision.get("reason") or "")
        if session.status not in {"closing", "closed"}:
            session.status = "queued"
    session.updated_at = now_iso_fn()
    session.condition.notify_all()
    return decision


def build_delegated_agent_payload(
    session: Any,
    *,
    config: Any,
    parallel_group: str,
    parallel_limit: int,
    result_ready: bool,
    wall_time_ms: int | None,
    current_step_wall_time_ms: int | None,
    timeout_metadata: dict[str, Any],
    last_wait_metadata: dict[str, Any],
    completion_policy: str,
    completion_state: str,
    result_state: str,
    result_state_metrics: dict[str, int],
    terminal_state: str,
    result_contract: dict[str, Any],
    progress_payload: dict[str, Any],
) -> dict[str, Any]:
    resolved_status = _resolved_session_status(session)
    adopted = bool(session.adopted)
    resolved_completion_state = _completion_state_for_status(
        status=resolved_status,
        adopted=adopted,
        completion_policy=str(completion_policy or "").strip(),
    )
    resolved_result_state = _result_state_for_status(
        status=resolved_status,
        completion_state=resolved_completion_state,
        adopted=adopted,
    )
    resolved_result_contract = _resolve_result_contract(
        dict(result_contract or {}),
        status=resolved_status,
        completion_policy=str(completion_policy or "").strip(),
        completion_state=resolved_completion_state,
        adopted=adopted,
        assistant_text=str(session.assistant_text or "").strip(),
        error=str(session.error or "").strip(),
    )
    payload: dict[str, Any] = {
        "agent_id": session.agent_id,
        "role": str(session.role or "").strip() or "subagent",
        **(
            {"subagent_type": str(getattr(session, "subagent_type", "") or "").strip()}
            if str(getattr(session, "subagent_type", "") or "").strip()
            else {}
        ),
        "status": resolved_status,
        "provider_name": str(getattr(config, "provider_name", "") or ""),
        "base_url": str(getattr(config, "base_url", "") or ""),
        "model_key": str(getattr(config, "model_key", "") or ""),
        "planner_kind": str(getattr(config, "planner_kind", "") or ""),
        "wire_api": str(getattr(config, "wire_api", "") or ""),
        "model": str(getattr(config, "model", "") or ""),
        "reasoning_effort": str(getattr(config, "reasoning_effort", "") or ""),
        "source": str(session.source or ""),
        "timeout": session.timeout,
        "created_at": str(session.created_at or ""),
        "updated_at": str(session.updated_at or ""),
        "turn_count": int(session.turn_count or 0),
        "parallel_group": parallel_group,
        "parallel_limit": parallel_limit,
        "pending_input_count": len(list(session.queued_inputs or []))
        + (1 if session.active_input else 0),
        "close_requested": bool(session.close_requested),
        "closed": bool(session.closed),
        "result_ready": result_ready,
        "adopted": bool(session.adopted),
        "last_input_text": str(session.last_input_text or ""),
        "tool_event_count": len(list(session.last_tool_events or [])),
        "tool_names": [
            str(item.name or "")
            for item in list(session.last_tool_events or [])
            if str(item.name or "").strip()
        ],
        "completion_policy": completion_policy,
        "completion_state": resolved_completion_state,
        "result_state": resolved_result_state,
        "result_contract": resolved_result_contract,
    }
    payload.update(
        {key: int(value) for key, value in dict(result_state_metrics or {}).items() if key}
    )
    if wall_time_ms is not None:
        payload["wall_time_ms"] = wall_time_ms
    if current_step_wall_time_ms is not None:
        payload["current_step_wall_time_ms"] = current_step_wall_time_ms
    payload.update(timeout_metadata)
    payload.update(last_wait_metadata)
    if str(session.terminal_reason or "").strip():
        payload["terminal_reason"] = str(session.terminal_reason or "").strip()
    if terminal_state:
        payload["terminal_state"] = terminal_state
    child_identity = _child_identity_payload(session)
    payload["child_identity"] = child_identity
    resume_source = (
        _normalized_optional_text(getattr(session, "resume_source", "")) or "spawn_agent"
    )
    payload["resume_source"] = resume_source
    adoption_expectation = str(resolved_result_contract.get("next_action") or "").strip()
    if adoption_expectation:
        payload["adoption_expectation"] = adoption_expectation
    payload.update(progress_payload)
    current_step_id = _normalized_optional_text(
        progress_payload.get("current_step_id")
        or payload.get("current_step_id")
        or payload.get("live_current_step_id")
    )
    current_step_status = _normalized_optional_text(
        progress_payload.get("current_step_status")
        or payload.get("current_step_status")
        or payload.get("live_current_step_status")
    )
    current_step_title = _normalized_optional_text(
        progress_payload.get("current_step_title")
        or payload.get("current_step_title")
        or payload.get("live_current_step_title")
    )
    if current_step_id:
        payload["live_current_step_id"] = current_step_id
    payload["live_current_step_status"] = current_step_status
    payload["live_current_step_title"] = current_step_title
    payload["live_queued_input_count"] = max(
        0, len(list(getattr(session, "queued_inputs", None) or []))
    )
    payload["live_has_active_input"] = getattr(session, "active_input", None) is not None
    payload["live_last_tool_event_count"] = len(
        list(getattr(session, "last_tool_events", None) or [])
    )
    payload["live_last_item_event_count"] = len(
        list(getattr(session, "last_item_events", None) or [])
    )
    payload["live_last_turn_event_count"] = len(
        list(getattr(session, "last_turn_events", None) or [])
    )
    payload["live_snapshot_version"] = 1
    payload["live_snapshot_exported_at"] = _normalized_optional_text(
        payload.get("updated_at") or payload.get("created_at")
    )
    payload.update(
        _command_policy_projection_from_tool_events(getattr(session, "last_tool_events", None))
    )
    if str(session.delegation_reason or "").strip():
        payload["delegation_reason"] = str(session.delegation_reason or "").strip()
    if str(session.delegation_mode or "").strip():
        payload["delegation_mode"] = str(session.delegation_mode or "").strip()
    if session.wait_required is not None:
        payload["wait_required"] = bool(session.wait_required)
    if str(session.task_shape or "").strip():
        payload["task_shape"] = str(session.task_shape or "").strip()
    if str(getattr(session, "background_priority", "") or "").strip():
        payload["background_priority"] = str(
            getattr(session, "background_priority", "") or ""
        ).strip()
    if str(session.scheduler_reason or "").strip():
        payload["scheduler_reason"] = str(session.scheduler_reason or "").strip()
    if str(session.adopted_at or "").strip():
        payload["adopted_at"] = str(session.adopted_at or "").strip()
    timeout_hit = bool(payload.get("timeout_hit"))
    timeout_reason = _normalized_optional_text(payload.get("timeout_reason"))
    error_text = _normalized_optional_text(getattr(session, "error", ""))
    protocol_adopted = bool(session.adopted)
    protocol_payload = _subagent_protocol_payload(
        session,
        status=resolved_status,
        timeout_hit=timeout_hit,
        adopted=protocol_adopted,
        timeout_reason=timeout_reason,
        error=error_text,
    )
    payload["subagent_protocol"] = protocol_payload
    payload["subagent_protocol_event_type"] = _normalized_optional_text(
        protocol_payload.get("event_type")
    )
    payload["subagent_protocol_status"] = _normalized_optional_text(protocol_payload.get("status"))
    payload["subagent_protocol_terminal_state"] = _normalized_optional_text(
        protocol_payload.get("terminal_state")
    )
    payload["subagent_protocol_terminal"] = bool(protocol_payload.get("terminal"))
    payload["subagent_protocol_adopted"] = bool(protocol_payload.get("adopted"))
    run_id = _normalized_optional_text(child_identity.get("run_id"))
    parent_run_id = _normalized_optional_text(child_identity.get("parent_run_id"))
    thread_id = _normalized_optional_text(child_identity.get("thread_id"))
    if run_id:
        payload["run_id"] = run_id
        payload["live_run_id"] = run_id
    if parent_run_id:
        payload["parent_run_id"] = parent_run_id
        payload["live_parent_run_id"] = parent_run_id
    if thread_id:
        payload["thread_id"] = thread_id
        payload["live_thread_id"] = thread_id
    return payload


def apply_optional_payload_fields(
    payload: dict[str, Any],
    *,
    active_input: dict[str, Any] | None,
    assistant_text: str,
    error: str,
) -> dict[str, Any]:
    return workflow_render_helpers_runtime.apply_optional_payload_fields(
        payload, active_input=active_input, assistant_text=assistant_text, error=error
    )


def build_delegated_workflow_payload(
    payload: dict[str, Any],
    *,
    progress_payload: dict[str, Any],
    steps_limit: int,
    checkpoints_limit: int,
) -> dict[str, Any]:
    return workflow_render_helpers_runtime.build_delegated_workflow_payload(
        payload,
        progress_payload=progress_payload,
        steps_limit=steps_limit,
        checkpoints_limit=checkpoints_limit,
    )


def delegated_workflow_text(payload: dict[str, Any]) -> str:
    return workflow_render_text_helpers_runtime.delegated_workflow_text(payload)


def delegated_agent_summary_text(payload: dict[str, Any]) -> str:
    return workflow_render_text_helpers_runtime.delegated_agent_summary_text(payload)

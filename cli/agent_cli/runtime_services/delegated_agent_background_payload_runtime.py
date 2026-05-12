from __future__ import annotations

from typing import Any, Callable, Dict, List

from cli.agent_cli.runtime_services import delegated_agent_background_payload_helpers_runtime as payload_helpers_runtime


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _resolved_live_queued_input_count(
    *,
    payload: Dict[str, Any],
) -> int:
    explicit = payload.get("live_queued_input_count")
    if explicit not in (None, ""):
        return _safe_int(explicit, default=0)
    pending = _safe_int(payload.get("pending_input_count"), default=0)
    has_active = payload.get("live_has_active_input")
    if isinstance(has_active, bool):
        return max(0, pending - (1 if has_active else 0))
    return max(0, pending)


def _resolved_live_has_active_input(
    *,
    payload: Dict[str, Any],
) -> bool:
    if isinstance(payload.get("live_has_active_input"), bool):
        return bool(payload.get("live_has_active_input"))
    return bool(_normalized_text(payload.get("active_input_text")))


def _live_snapshot_surface(
    *,
    payload: Dict[str, Any],
    progress_payload: Dict[str, Any],
) -> Dict[str, Any]:
    return payload_helpers_runtime.live_snapshot_surface(payload=payload, progress_payload=progress_payload)


def _protocol_projection(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload_helpers_runtime.protocol_projection(payload)


def _command_policy_projection(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload_helpers_runtime.command_policy_projection(payload)


def _child_identity_projection(payload: Dict[str, Any]) -> Dict[str, Any]:
    return payload_helpers_runtime.child_identity_projection(payload)


def stabilized_notification_state(
    *,
    candidate_state: str,
    checkpoint_count: Any,
    previous_artifact: Dict[str, Any] | None,
) -> str:
    normalized_candidate = str(candidate_state or "").strip() or "pending"
    previous = dict(previous_artifact or {})
    previous_state = str(previous.get("notification_state") or "").strip()
    if previous_state == "orphaned" or normalized_candidate == "orphaned":
        return "orphaned"
    if not previous_state:
        return normalized_candidate
    candidate_checkpoint = _safe_int(checkpoint_count, default=0)
    previous_checkpoint = _safe_int(previous.get("checkpoint_count"), default=0)
    if candidate_checkpoint <= previous_checkpoint:
        if previous_state == "foreground_adopted" and normalized_candidate in {"pending", "ready", "closed"}:
            return "foreground_adopted"
        if previous_state == "ready" and normalized_candidate == "pending":
            return "ready"
    return normalized_candidate


def stabilize_orphan_snapshot_payload(
    *,
    snapshot_payload: Dict[str, Any],
    payload: Dict[str, Any],
    previous_artifact: Dict[str, Any] | None,
) -> Dict[str, Any]:
    merged = dict(snapshot_payload)
    if str(merged.get("notification_state") or "").strip() != "orphaned":
        return merged
    previous = dict(previous_artifact or {})
    terminal_state = str(merged.get("terminal_state") or "").strip()
    if not terminal_state:
        merged["terminal_state"] = (
            str(payload.get("terminal_state") or "").strip()
            or str(previous.get("terminal_state") or "").strip()
            or "orphaned"
        )
    terminal_reason = str(merged.get("terminal_reason") or "").strip()
    if not terminal_reason:
        reason = str(payload.get("terminal_reason") or "").strip() or str(previous.get("terminal_reason") or "").strip()
        if reason:
            merged["terminal_reason"] = reason
    return merged


def stabilize_orphan_result_artifact(
    *,
    artifact: Dict[str, Any],
    payload: Dict[str, Any],
    previous_artifact: Dict[str, Any] | None,
) -> Dict[str, Any]:
    merged = dict(artifact)
    if str(merged.get("notification_state") or "").strip() != "orphaned":
        return merged
    previous = dict(previous_artifact or {})
    terminal_state = str(merged.get("terminal_state") or "").strip()
    if not terminal_state:
        merged["terminal_state"] = (
            str(payload.get("terminal_state") or "").strip()
            or str(previous.get("terminal_state") or "").strip()
            or "orphaned"
        )
    terminal_reason = str(merged.get("terminal_reason") or "").strip()
    if not terminal_reason:
        reason = str(payload.get("terminal_reason") or "").strip() or str(previous.get("terminal_reason") or "").strip()
        if reason:
            merged["terminal_reason"] = reason
    return merged


def sync_snapshot_payload(
    runtime: Any,
    session: Any,
    *,
    payload: Dict[str, Any],
    progress_payload: Dict[str, Any],
    task_id: str,
    notification_state: str,
) -> Dict[str, Any]:
    result_contract = dict(payload.get("result_contract") or {})
    live_surface = _live_snapshot_surface(payload=payload, progress_payload=progress_payload)
    protocol_projection = _protocol_projection(payload)
    child_identity_projection = _child_identity_projection(payload)
    command_policy_projection = _command_policy_projection(payload)
    snapshot_payload = {
        "task_id": task_id,
        "task_type": "teammate",
        "goal": runtime._delegated_goal_text(session),
        "delegated_agent": payload,
        "result_contract": result_contract,
        "notification_state": notification_state,
        **progress_payload,
        **live_surface,
        **protocol_projection,
        **child_identity_projection,
        **command_policy_projection,
    }
    if str(payload.get("terminal_state") or "").strip():
        snapshot_payload["terminal_state"] = str(payload.get("terminal_state") or "").strip()
    if isinstance(payload.get("subagent_protocol"), dict):
        snapshot_payload["subagent_protocol"] = dict(payload.get("subagent_protocol") or {})
    for key in ("run_id", "parent_run_id", "thread_id"):
        if str(payload.get(key) or "").strip():
            snapshot_payload[key] = str(payload.get(key) or "").strip()
    return snapshot_payload


def sync_result_artifact(
    *,
    session: Any,
    payload: Dict[str, Any],
    progress_payload: Dict[str, Any],
    snapshot_path: Any,
    notification_state: str,
    text: str,
    error: str,
    preview_text_fn: Callable[..., str],
) -> Dict[str, Any]:
    live_surface = _live_snapshot_surface(payload=payload, progress_payload=progress_payload)
    protocol_projection = _protocol_projection(payload)
    child_identity_projection = _child_identity_projection(payload)
    command_policy_projection = _command_policy_projection(payload)
    artifact = {
        "snapshot_path": str(snapshot_path),
        "agent_id": str(session.agent_id or ""),
        "role": str(session.role or ""),
        "step_count": int(progress_payload.get("step_count") or 0),
        "checkpoint_count": int(progress_payload.get("checkpoint_count") or 0),
        "workflow_state": str(progress_payload.get("workflow_state") or "").strip(),
        "recovery_action_count": int(progress_payload.get("recovery_action_count") or 0),
        "notification_state": notification_state,
        **live_surface,
        **protocol_projection,
        **child_identity_projection,
        **command_policy_projection,
    }
    if payload.get("wall_time_ms") not in (None, ""):
        artifact["wall_time_ms"] = int(payload["wall_time_ms"])
    if payload.get("current_step_wall_time_ms") not in (None, ""):
        artifact["current_step_wall_time_ms"] = int(payload["current_step_wall_time_ms"])
    if payload.get("timeout_budget_seconds") not in (None, ""):
        artifact["timeout_budget_seconds"] = payload["timeout_budget_seconds"]
    if "timeout_hit" in payload:
        artifact["timeout_hit"] = bool(payload.get("timeout_hit"))
    if str(payload.get("timeout_reason") or "").strip():
        artifact["timeout_reason"] = str(payload.get("timeout_reason") or "").strip()
    if str(payload.get("timeout_source") or "").strip():
        artifact["timeout_source"] = str(payload.get("timeout_source") or "").strip()
    if str(payload.get("last_wait_decision") or "").strip():
        artifact["last_wait_decision"] = str(payload.get("last_wait_decision") or "").strip()
    if payload.get("last_wait_blocked_ms") not in (None, ""):
        artifact["last_wait_blocked_ms"] = int(payload["last_wait_blocked_ms"])
    if "last_wait_timed_out" in payload:
        artifact["last_wait_timed_out"] = bool(payload.get("last_wait_timed_out"))
    if str(payload.get("last_wait_reason") or "").strip():
        artifact["last_wait_reason"] = str(payload.get("last_wait_reason") or "").strip()
    if str(payload.get("last_wait_at") or "").strip():
        artifact["last_wait_at"] = str(payload.get("last_wait_at") or "").strip()
    if str(payload.get("terminal_state") or "").strip():
        artifact["terminal_state"] = str(payload.get("terminal_state") or "").strip()
    if str(payload.get("terminal_reason") or "").strip():
        artifact["terminal_reason"] = str(payload.get("terminal_reason") or "").strip()
    if str(payload.get("adopted_at") or "").strip():
        artifact["foreground_taken_over_at"] = str(payload.get("adopted_at") or "").strip()
    if isinstance(payload.get("subagent_protocol"), dict):
        protocol = dict(payload.get("subagent_protocol") or {})
        artifact["subagent_protocol_event_type"] = str(protocol.get("event_type") or "").strip()
        artifact["subagent_protocol_status"] = str(protocol.get("status") or "").strip()
    for key in ("run_id", "parent_run_id", "thread_id"):
        if str(payload.get(key) or "").strip():
            artifact[key] = str(payload.get(key) or "").strip()
    if str(progress_payload.get("current_step_id") or "").strip():
        artifact["current_step_id"] = str(progress_payload.get("current_step_id") or "").strip()
    if str(progress_payload.get("current_step_status") or "").strip():
        artifact["current_step_status"] = str(progress_payload.get("current_step_status") or "").strip()
    if str(progress_payload.get("current_step_title") or "").strip():
        artifact["current_step_title"] = str(progress_payload.get("current_step_title") or "").strip()
    if isinstance(progress_payload.get("latest_checkpoint"), dict):
        artifact["latest_checkpoint"] = dict(progress_payload.get("latest_checkpoint") or {})
    if text:
        artifact["text_preview"] = preview_text_fn(text, max_chars=160)
    if error:
        artifact["error_preview"] = preview_text_fn(error, max_chars=160)
    return artifact


def orphan_goal(raw_session: Dict[str, Any], queued_inputs: List[Dict[str, Any]], active_input: Dict[str, Any] | None) -> str:
    goal = ""
    if isinstance(active_input, dict):
        goal = str(active_input.get("message") or "").strip()
    if not goal:
        for item in queued_inputs:
            if isinstance(item, dict) and str(item.get("message") or "").strip():
                goal = str(item.get("message") or "").strip()
                break
    if not goal:
        goal = str(raw_session.get("last_input_text") or "").strip()
    return goal


def orphan_snapshot_payload(
    *,
    raw_session: Dict[str, Any],
    task_id: str,
    goal: str,
    agent_id: str,
    role: str,
    reason: str,
    summary: str,
) -> Dict[str, Any]:
    run_id = str(raw_session.get("protocol_run_id") or raw_session.get("run_id") or "").strip() or f"delegated:{agent_id or 'unknown'}"
    return {
        "task_id": task_id,
        "task_type": "teammate",
        "goal": goal,
        "child_identity": {
            "agent_id": agent_id,
            "run_id": run_id,
            "parent_run_id": str(raw_session.get("protocol_parent_run_id") or raw_session.get("parent_run_id") or ""),
            "thread_id": str(raw_session.get("protocol_thread_id") or raw_session.get("thread_id") or ""),
        },
        "resume_source": "thread_resume_restore",
        "delegated_agent": {
            "agent_id": agent_id,
            "role": role,
            "status": "closed",
            "source": str(raw_session.get("source") or ""),
            "provider_name": str(raw_session.get("provider_name") or ""),
            "model": str(raw_session.get("model") or ""),
            "terminal_reason": reason,
        },
        "result_contract": {
            "goal": goal,
            "status": "closed",
            "summary": summary,
            "artifact": {"kind": "empty"},
            "confidence": "low",
            "touched_scope": [],
            "next_action": "resume_agent_to_continue",
        },
        "notification_state": "orphaned",
        "terminal_state": "orphaned",
        "orphaned_session": dict(raw_session),
    }


def orphan_result_artifact(
    *,
    raw_session: Dict[str, Any],
    snapshot_path: Any,
    agent_id: str,
    role: str,
    reason: str,
    error: str,
    preview_text_fn: Callable[..., str],
) -> Dict[str, Any]:
    run_id = str(raw_session.get("protocol_run_id") or raw_session.get("run_id") or "").strip() or f"delegated:{agent_id or 'unknown'}"
    artifact = {
        "snapshot_path": str(snapshot_path),
        "agent_id": agent_id,
        "role": role,
        "child_identity": {
            "agent_id": agent_id,
            "run_id": run_id,
            "parent_run_id": str(raw_session.get("protocol_parent_run_id") or raw_session.get("parent_run_id") or ""),
            "thread_id": str(raw_session.get("protocol_thread_id") or raw_session.get("thread_id") or ""),
        },
        "resume_source": "thread_resume_restore",
        "step_count": len(list(raw_session.get("progress_steps") or [])),
        "checkpoint_count": len(list(raw_session.get("progress_checkpoints") or [])),
        "notification_state": "orphaned",
        "terminal_state": "orphaned",
        "terminal_reason": reason,
    }
    if error:
        artifact["error_preview"] = preview_text_fn(error, max_chars=160)
    return artifact

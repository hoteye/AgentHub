from __future__ import annotations

from typing import Any, Dict


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


def live_snapshot_surface(
    *,
    payload: Dict[str, Any],
    progress_payload: Dict[str, Any],
) -> Dict[str, Any]:
    current_step_id = _normalized_text(
        progress_payload.get("current_step_id") or payload.get("current_step_id") or payload.get("live_current_step_id")
    )
    current_step_status = _normalized_text(
        progress_payload.get("current_step_status")
        or payload.get("current_step_status")
        or payload.get("live_current_step_status")
    )
    current_step_title = _normalized_text(
        progress_payload.get("current_step_title")
        or payload.get("current_step_title")
        or payload.get("live_current_step_title")
    )
    exported_at = _normalized_text(
        payload.get("live_snapshot_exported_at")
        or payload.get("updated_at")
        or payload.get("created_at")
    )
    run_id = _normalized_text(payload.get("run_id"))
    parent_run_id = _normalized_text(payload.get("parent_run_id"))
    thread_id = _normalized_text(payload.get("thread_id"))
    live_surface: Dict[str, Any] = {
        "live_snapshot_version": _safe_int(payload.get("live_snapshot_version"), default=1),
        "live_current_step_status": current_step_status,
        "live_current_step_title": current_step_title,
        "live_queued_input_count": _resolved_live_queued_input_count(payload=payload),
        "live_has_active_input": _resolved_live_has_active_input(payload=payload),
        "live_last_tool_event_count": _safe_int(
            payload.get("live_last_tool_event_count", payload.get("tool_event_count")),
            default=0,
        ),
        "live_last_item_event_count": _safe_int(payload.get("live_last_item_event_count"), default=0),
        "live_last_turn_event_count": _safe_int(payload.get("live_last_turn_event_count"), default=0),
    }
    if current_step_id:
        live_surface["live_current_step_id"] = current_step_id
    if exported_at:
        live_surface["live_snapshot_exported_at"] = exported_at
    if run_id:
        live_surface["live_run_id"] = run_id
    if parent_run_id:
        live_surface["live_parent_run_id"] = parent_run_id
    if thread_id:
        live_surface["live_thread_id"] = thread_id
    return live_surface


def protocol_projection(payload: Dict[str, Any]) -> Dict[str, Any]:
    protocol = payload.get("subagent_protocol")
    if not isinstance(protocol, dict):
        return {}
    projection: Dict[str, Any] = {
        "subagent_protocol_event_type": _normalized_text(protocol.get("event_type")),
        "subagent_protocol_status": _normalized_text(protocol.get("status")),
        "subagent_protocol_terminal_state": _normalized_text(protocol.get("terminal_state")),
    }
    if "terminal" in protocol:
        projection["subagent_protocol_terminal"] = bool(protocol.get("terminal"))
    if "adopted" in protocol:
        projection["subagent_protocol_adopted"] = bool(protocol.get("adopted"))
    return projection


def child_identity_projection(payload: Dict[str, Any]) -> Dict[str, Any]:
    projection: Dict[str, Any] = {}
    child_identity = payload.get("child_identity")
    if isinstance(child_identity, dict):
        agent_id = _normalized_text(child_identity.get("agent_id"))
        projection["child_identity"] = {
            "agent_id": agent_id,
            "run_id": _normalized_text(child_identity.get("run_id")) or f"delegated:{agent_id or 'unknown'}",
            "parent_run_id": _normalized_text(child_identity.get("parent_run_id")),
            "thread_id": _normalized_text(child_identity.get("thread_id")),
        }
    for key in ("run_id", "parent_run_id", "thread_id"):
        value = _normalized_text(payload.get(key))
        if value:
            projection[key] = value
    resume_source = _normalized_text(payload.get("resume_source"))
    if resume_source:
        projection["resume_source"] = resume_source
    return projection


def command_policy_projection(payload: Dict[str, Any]) -> Dict[str, Any]:
    projection: Dict[str, Any] = {}
    command_policies = payload.get("command_policies")
    if isinstance(command_policies, list):
        projection["command_policies"] = [dict(item) for item in command_policies if isinstance(item, dict)]
        projection["command_policies_count"] = len(projection["command_policies"])
    for key in (
        "command_policy_denied_count",
        "command_policy_rewrite_count",
        "command_policy_checked_count",
    ):
        if key in payload and payload.get(key) not in (None, ""):
            projection[key] = _safe_int(payload.get(key), default=0)
    surface = _normalized_text(payload.get("command_policy_surface"))
    if surface:
        projection["command_policy_surface"] = surface
    return projection

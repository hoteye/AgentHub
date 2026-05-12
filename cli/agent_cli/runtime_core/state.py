from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from cli.agent_cli.models import ToolEvent, tool_event_is_soft_failure


def state_value(state: Dict[str, Any], key: str) -> Optional[str]:
    value = str(state.get(key) or "").strip()
    if value in {"", "-"}:
        return None
    return value


def apply_tool_state(
    *,
    selected_conversation: Optional[str],
    pending_send_text: str,
    send_ready: bool,
    event: ToolEvent,
) -> Tuple[Optional[str], str, bool]:
    payload = event.payload or {}
    selected = (
        payload.get("selected_conversation")
        or (payload.get("selected") or {}).get("name")
        or (payload.get("selected_after") or {}).get("name")
        or payload.get("conversation_name")
    )
    if selected:
        selected_conversation = str(selected)

    if event.name == "draft_reply":
        draft_text = str(payload.get("draft_reply") or "").strip()
        if draft_text:
            pending_send_text = draft_text
            send_ready = False
    elif event.name == "prepare_send":
        draft_text = str(payload.get("draft_text") or "").strip()
        if draft_text:
            pending_send_text = draft_text
        send_ready = bool(event.ok)
    elif event.name == "send_reply":
        if event.ok:
            pending_send_text = ""
            send_ready = False
        else:
            draft_text = str(payload.get("draft_text") or "").strip()
            if draft_text:
                pending_send_text = draft_text
            send_ready = False
    elif event.name == "bootstrap":
        conversations = payload.get("conversations") or {}
        selected_item = (conversations.get("selected") or {}).get("name")
        if selected_item:
            selected_conversation = str(selected_item)

    return selected_conversation, pending_send_text, send_ready


def build_status_payload(
    *,
    source_text: str,
    events: List[ToolEvent],
    timings: Optional[Dict[str, Any]] = None,
    terminal_state: str | None = None,
    error_message: str | None = None,
    provider_status: Dict[str, str],
    runtime_policy_status: Optional[Dict[str, str]] = None,
    approval_status: Optional[Dict[str, str]] = None,
    selected_conversation: Optional[str],
    send_ready: bool,
    pending_send_text: str,
    active_run_token: Optional[str],
    thread_id: Optional[str],
    thread_name: str,
) -> Dict[str, str]:
    last_event = events[-1] if events else None
    status = {
        "last_input": source_text,
        "last_tool": last_event.name if last_event else "-",
        "last_ok": (
            ("soft-fail" if tool_event_is_soft_failure(last_event) else str(last_event.ok))
            if last_event
            else "-"
        ),
        "last_summary": last_event.summary if last_event else "-",
        "selected_conversation": selected_conversation or "-",
        "send_ready": str(send_ready).lower(),
        "has_pending_draft": str(bool(pending_send_text)).lower(),
        "pending_send_preview": (pending_send_text[:80] if pending_send_text else "-"),
        "busy": str(active_run_token is not None).lower(),
        "active_run_token": active_run_token or "-",
        "thread_id": thread_id or "-",
        "thread_name": thread_name or "-",
        **provider_status,
    }
    if runtime_policy_status:
        status.update(runtime_policy_status)
    if approval_status:
        status.update(approval_status)
    timing_payload = dict(timings or {})
    for key in ("initial_model_ms", "tool_execution_ms", "synthesis_model_ms", "total_ms"):
        value = timing_payload.get(key)
        if value is None:
            continue
        status[f"timing_{key}"] = str(int(value))
    if timing_payload:
        parts: List[str] = []
        for key in ("initial_model_ms", "tool_execution_ms", "synthesis_model_ms", "total_ms"):
            value = timing_payload.get(key)
            if value is None:
                continue
            label = key.removesuffix("_ms")
            parts.append(f"{label}={int(value) / 1000:.2f}s")
        if parts:
            status["timing_summary"] = " | ".join(parts)
    normalized_terminal_state = str(terminal_state or "").strip().lower()
    if normalized_terminal_state:
        status["terminal_state"] = normalized_terminal_state
    normalized_error_message = str(error_message or "").strip()
    if normalized_error_message:
        status["error"] = normalized_error_message
    return status


def snapshot_thread_state_payload(
    *,
    provider_status: Dict[str, str],
    runtime_policy_status: Optional[Dict[str, str]] = None,
    approval_status: Optional[Dict[str, str]] = None,
    selected_conversation: Optional[str],
    pending_send_text: str,
    send_ready: bool,
    thread_id: Optional[str],
    thread_name: str,
) -> Dict[str, Any]:
    payload = {
        "selected_conversation": selected_conversation or "",
        "pending_send_text": pending_send_text,
        "send_ready": str(send_ready).lower(),
        "thread_id": thread_id or "",
        "thread_name": thread_name or "",
        **provider_status,
    }
    if runtime_policy_status:
        payload.update(runtime_policy_status)
    if approval_status:
        payload.update(approval_status)
    return payload

from __future__ import annotations

import json
from typing import Any, Callable


def terminal_wait_status_hint(session: Any, *, terminal_wait_statuses: set[str]) -> str:
    normalized_status = str(getattr(session, "status", "") or "").strip().lower()
    if normalized_status in terminal_wait_statuses:
        return normalized_status
    has_active_input = getattr(session, "active_input", None) is not None
    has_queued_inputs = bool(getattr(session, "queued_inputs", None))
    if has_active_input or has_queued_inputs:
        return ""
    terminal_reason = str(getattr(session, "terminal_reason", "") or "").strip().lower()
    if terminal_reason in {
        "close_requested",
        "orphan_cleanup",
        "restore_resolution_failed",
        "role_override_changed",
    }:
        return "closed"
    if terminal_reason == "failed" or str(getattr(session, "error", "") or "").strip():
        return "failed"
    if terminal_reason == "completed":
        return "completed"
    if bool(getattr(session, "adopted", False)) or str(getattr(session, "assistant_text", "") or "").strip():
        return "completed"
    return ""


def promote_terminal_wait_status(
    session: Any,
    *,
    terminal_wait_status_hint_fn: Callable[[Any], str],
    now_iso_fn: Callable[[], str],
) -> bool:
    terminal_status = terminal_wait_status_hint_fn(session)
    if not terminal_status:
        return False
    normalized_status = str(getattr(session, "status", "") or "").strip().lower() or "queued"
    changed = False
    if normalized_status != terminal_status:
        session.status = terminal_status
        changed = True
    terminal_reason = str(getattr(session, "terminal_reason", "") or "").strip()
    if terminal_status == "completed" and not terminal_reason:
        session.terminal_reason = "completed"
        changed = True
    elif terminal_status == "failed" and not terminal_reason:
        session.terminal_reason = "failed"
        changed = True
    if changed:
        session.updated_at = now_iso_fn()
        session.condition.notify_all()
    return True


def codex_wait_status_wire(
    session: Any,
    *,
    terminal_wait_status_hint_fn: Callable[[Any], str],
) -> Any | None:
    terminal_status = terminal_wait_status_hint_fn(session)
    if not terminal_status:
        return None
    if terminal_status == "completed":
        message = str(getattr(session, "assistant_text", "") or "").strip()
        return {"completed": message or None}
    if terminal_status == "failed":
        error_text = (
            str(getattr(session, "error", "") or "").strip()
            or str(getattr(session, "terminal_reason", "") or "").strip()
            or "errored"
        )
        return {"errored": error_text}
    if terminal_status == "closed":
        return "shutdown"
    return None


def codex_wait_result(
    *,
    agent_ids: list[str],
    statuses: dict[str, Any],
    timed_out: bool,
    timeout_ms: int,
    tool_event_factory: Callable[..., Any],
    command_result_factory: Callable[..., Any],
    generic_tool_call_item_events_fn: Callable[..., list[Any]],
) -> Any:
    payload = {
        "status": dict(statuses),
        "timed_out": bool(timed_out),
    }
    payload["text"] = json.dumps(
        {
            "status": dict(statuses),
            "timed_out": bool(timed_out),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    summary = "wait timed out" if timed_out else "wait completed"
    event = tool_event_factory(
        name="wait",
        ok=True,
        summary=summary,
        payload=payload,
    )
    return command_result_factory(
        assistant_text=str(payload["text"]),
        tool_events=[event],
        item_events=generic_tool_call_item_events_fn(
            tool_name="wait",
            arguments={
                "ids": list(agent_ids),
                "timeout_ms": int(timeout_ms),
            },
            ok=True,
            summary=summary,
            structured_content=dict(event.payload or {}),
        ),
    )


def codex_wait_status_snapshot(
    runtime: Any,
    agent_ids: list[str],
    *,
    delegated_session_if_present_fn: Callable[[Any, str], Any | None],
    promote_terminal_wait_status_fn: Callable[[Any], bool],
    codex_wait_status_wire_fn: Callable[[Any], Any | None],
) -> tuple[dict[str, Any], list[tuple[str, Any]]]:
    statuses: dict[str, Any] = {}
    pending: list[tuple[str, Any]] = []
    for agent_id in list(agent_ids):
        session = delegated_session_if_present_fn(runtime, agent_id)
        if session is None:
            statuses[agent_id] = "not_found"
            continue
        with session.condition:
            promote_terminal_wait_status_fn(session)
            wire_status = codex_wait_status_wire_fn(session)
        if wire_status is not None:
            statuses[agent_id] = wire_status
            continue
        pending.append((agent_id, session))
    return statuses, pending

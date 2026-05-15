from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cli.agent_cli.models import (
    PromptResponse,
    tool_events_include_approval_requests,
    tool_events_include_interrupt,
)

if TYPE_CHECKING:
    from cli.agent_cli.ui.tab_task_run import (
        TabTaskRun,
        TaskObjectiveState,
        TaskRunState,
        TaskTerminalState,
    )

TERMINAL_STATES: frozenset[str] = frozenset(
    {"completed", "failed", "interrupted", "cancelled", "timed_out", "unknown"}
)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _clean_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _event_type(event: Any) -> str:
    if not isinstance(event, dict):
        return ""
    return _clean_text(event.get("type")).lower()


def _terminal_event_from_turn_events(turn_events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in reversed([item for item in list(turn_events or []) if isinstance(item, dict)]):
        event_type = _event_type(event)
        if event_type in {
            "turn.completed",
            "turn.failed",
            "turn.interrupted",
            "turn.cancelled",
            "turn.canceled",
            "turn.timed_out",
            "turn.timeout",
            "turn.unknown",
        }:
            return dict(event)
    return {}


def _terminal_state_from_turn_event(event: dict[str, Any]) -> TaskTerminalState:
    event_type = _event_type(event)
    if event_type == "turn.completed":
        return "completed"
    if event_type == "turn.failed":
        return "failed"
    if event_type == "turn.interrupted":
        return "interrupted"
    if event_type in {"turn.cancelled", "turn.canceled"}:
        return "cancelled"
    if event_type in {"turn.timed_out", "turn.timeout"}:
        return "timed_out"
    if event_type == "turn.unknown":
        return "unknown"
    return ""


def _terminal_reason_from_response(
    response: PromptResponse,
    *,
    terminal_state: str,
    terminal_event: dict[str, Any],
) -> str:
    diagnostics = _clean_mapping(getattr(response, "protocol_diagnostics", None))
    protocol_path = _clean_mapping(diagnostics.get("protocol_path"))
    path_kind = _clean_text(protocol_path.get("kind"))
    if path_kind == "provider_degraded_fallback":
        return "provider_degraded"
    if _clean_text(diagnostics.get("provider_degraded")):
        return "provider_degraded"
    if _clean_text(diagnostics.get("anthropic_streaming_fallback_reason")):
        return "provider_stream_fallback"
    status = _clean_mapping(getattr(response, "status", None))
    status_terminal = _clean_text(status.get("terminal_state")).lower()
    if status_terminal == "failed":
        return "provider_error"
    if terminal_event:
        event_type = _event_type(terminal_event)
        if event_type:
            return event_type.replace(".", "_")
    if terminal_state == "completed" and bool(getattr(response, "handled_as_command", False)):
        return "slash_command_completed"
    if terminal_state:
        return f"provider_{terminal_state}"
    return ""


def objective_state_from_response(response: PromptResponse) -> TaskObjectiveState:
    status = _clean_mapping(getattr(response, "status", None))
    for key in ("objective_state", "task_objective_state"):
        value = _clean_text(status.get(key)).lower()
        if value in {
            "not_reported",
            "claimed_done",
            "claimed_partial",
            "claimed_blocked",
            "claimed_failed",
        }:
            return value  # type: ignore[return-value]
    diagnostics = _clean_mapping(getattr(response, "protocol_diagnostics", None))
    task_report = _clean_mapping(diagnostics.get("task_report"))
    value = _clean_text(task_report.get("objective_state")).lower()
    if value in {
        "not_reported",
        "claimed_done",
        "claimed_partial",
        "claimed_blocked",
        "claimed_failed",
    }:
        return value  # type: ignore[return-value]
    return "not_reported"


def summary_from_response(response: PromptResponse) -> str:
    status = _clean_mapping(getattr(response, "status", None))
    for key in ("task_summary", "summary"):
        text = _clean_text(status.get(key))
        if text:
            return text
    diagnostics = _clean_mapping(getattr(response, "protocol_diagnostics", None))
    task_report = _clean_mapping(diagnostics.get("task_report"))
    text = _clean_text(task_report.get("summary"))
    if text:
        return text
    assistant_text = _clean_text(getattr(response, "assistant_text", ""))
    if assistant_text:
        return assistant_text
    return _clean_text(getattr(response, "commentary_text", ""))


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return _safe_float(value)


def _normalize_state(value: Any) -> TaskRunState:
    state = _clean_text(value).lower()
    if state in {
        "queued",
        "running",
        "waiting_approval",
        "waiting_input",
        "completed",
        "failed",
        "interrupted",
        "cancelled",
        "timed_out",
        "unknown",
    }:
        return state  # type: ignore[return-value]
    return "unknown"


def _normalize_terminal_state(value: Any) -> TaskTerminalState:
    state = _clean_text(value).lower()
    if not state:
        return ""
    if state == "canceled":
        return "cancelled"
    if state in TERMINAL_STATES:
        return state  # type: ignore[return-value]
    return "unknown"


def _normalize_objective_state(value: Any) -> TaskObjectiveState:
    state = _clean_text(value).lower()
    if state in {
        "not_reported",
        "claimed_done",
        "claimed_partial",
        "claimed_blocked",
        "claimed_failed",
    }:
        return state  # type: ignore[return-value]
    return "not_reported"


def task_run_from_response(
    base: TabTaskRun,
    response: PromptResponse,
    *,
    transcript_range: tuple[int, int] | None = None,
) -> TabTaskRun:
    terminal_event = _terminal_event_from_turn_events(
        list(getattr(response, "turn_events", []) or [])
    )
    terminal_state = _terminal_state_from_turn_event(terminal_event) or "completed"
    if tool_events_include_interrupt(list(getattr(response, "tool_events", []) or [])):
        terminal_state = "interrupted"
        if not terminal_event:
            terminal_event = {"type": "tool.interrupted"}
    if terminal_state == "completed" and tool_events_include_approval_requests(
        list(getattr(response, "tool_events", []) or [])
    ):
        base.mark_waiting_approval()
        base.terminal_state = ""
        base.terminal_reason = "waiting_approval"
        base.objective_state = "not_reported"
        base.summary = summary_from_response(response)
        base.error_message = ""
        base.provider_terminal_event = {"type": "tool.approval_requested"}
        base.status_snapshot = _clean_mapping(getattr(response, "status", None))
        if transcript_range is not None:
            base.transcript_range = transcript_range
        return base
    status = _clean_mapping(getattr(response, "status", None))
    reason = _terminal_reason_from_response(
        response,
        terminal_state=terminal_state,
        terminal_event=terminal_event,
    )
    if terminal_event and terminal_state in {"failed", "interrupted", "cancelled", "timed_out"}:
        error = _clean_mapping(terminal_event.get("error"))
        error_message = _clean_text(error.get("message")) or _clean_text(status.get("error"))
    else:
        error_message = _clean_text(status.get("error")) if terminal_state == "failed" else ""
    base.finish(
        terminal_state=terminal_state,
        terminal_reason=reason,
        objective_state=objective_state_from_response(response),
        summary=summary_from_response(response),
        error_message=error_message,
        provider_terminal_event=terminal_event or None,
        status_snapshot=status,
        transcript_range=transcript_range,
    )
    return base


def task_run_from_exception(
    base: TabTaskRun,
    error: BaseException,
    *,
    transcript_range: tuple[int, int] | None = None,
) -> TabTaskRun:
    base.finish(
        terminal_state="failed",
        terminal_reason="runtime_exception",
        objective_state="not_reported",
        summary="",
        error_message=str(error),
        provider_terminal_event={"type": "runtime.exception", "error": {"message": str(error)}},
        status_snapshot={},
        transcript_range=transcript_range,
    )
    return base


def queued_task_run(
    *,
    run_id: str,
    tab_id: str,
    parent_tab_id: str = "",
    provider: str = "",
    engine: str = "",
    user_prompt: str = "",
    transcript_start_index: int = 0,
    assignment_ref: dict[str, Any] | None = None,
) -> TabTaskRun:
    from cli.agent_cli.ui.tab_task_run import TabTaskRun

    return TabTaskRun(
        run_id=run_id,
        tab_id=tab_id,
        parent_tab_id=parent_tab_id,
        provider=provider,
        engine=engine,
        state="queued",
        user_prompt=user_prompt,
        transcript_range=(max(0, int(transcript_start_index)), max(0, int(transcript_start_index))),
        assignment_ref=dict(assignment_ref or {}),
    )

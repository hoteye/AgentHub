from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

from cli.agent_cli.models import (
    PromptResponse,
    tool_events_include_approval_requests,
    tool_events_include_interrupt,
)

TabRole = Literal["standalone", "master", "child"]
TaskRunState = Literal[
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
]
TaskTerminalState = Literal[
    "",
    "completed",
    "failed",
    "interrupted",
    "cancelled",
    "timed_out",
    "unknown",
]
TaskObjectiveState = Literal[
    "not_reported",
    "claimed_done",
    "claimed_partial",
    "claimed_blocked",
    "claimed_failed",
]

TERMINAL_STATES: frozenset[str] = frozenset(
    {"completed", "failed", "interrupted", "cancelled", "timed_out", "unknown"}
)


def current_time() -> float:
    return time.time()


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


@dataclass(slots=True)
class TabTaskRun:
    run_id: str
    tab_id: str
    parent_tab_id: str = ""
    provider: str = ""
    engine: str = ""
    state: TaskRunState = "queued"
    terminal_state: TaskTerminalState = ""
    terminal_reason: str = ""
    objective_state: TaskObjectiveState = "not_reported"
    started_at: float = 0.0
    finished_at: float | None = None
    user_prompt: str = ""
    summary: str = ""
    error_message: str = ""
    transcript_range: tuple[int, int] = (0, 0)
    provider_terminal_event: dict[str, Any] | None = None
    status_snapshot: dict[str, Any] = field(default_factory=dict)
    assignment_ref: dict[str, Any] = field(default_factory=dict)

    @property
    def is_terminal(self) -> bool:
        return bool(self.terminal_state and self.terminal_state in TERMINAL_STATES)

    def mark_running(self, *, started_at: float | None = None) -> None:
        self.state = "running"
        self.started_at = current_time() if started_at is None else float(started_at)

    def mark_waiting_approval(self) -> None:
        self.state = "waiting_approval"

    def mark_waiting_input(self) -> None:
        self.state = "waiting_input"

    def finish(
        self,
        *,
        terminal_state: TaskTerminalState,
        terminal_reason: str,
        objective_state: TaskObjectiveState = "not_reported",
        summary: str = "",
        error_message: str = "",
        provider_terminal_event: dict[str, Any] | None = None,
        status_snapshot: dict[str, Any] | None = None,
        transcript_range: tuple[int, int] | None = None,
        finished_at: float | None = None,
    ) -> None:
        self.terminal_state = terminal_state
        self.terminal_reason = terminal_reason
        self.objective_state = objective_state
        self.summary = summary
        self.error_message = error_message
        self.provider_terminal_event = provider_terminal_event
        self.status_snapshot = dict(status_snapshot or {})
        if transcript_range is not None:
            self.transcript_range = transcript_range
        self.finished_at = current_time() if finished_at is None else float(finished_at)
        self.state = terminal_state if terminal_state in TERMINAL_STATES else "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "tab_id": self.tab_id,
            "parent_tab_id": self.parent_tab_id,
            "provider": self.provider,
            "engine": self.engine,
            "state": self.state,
            "terminal_state": self.terminal_state,
            "terminal_reason": self.terminal_reason,
            "objective_state": self.objective_state,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "user_prompt": self.user_prompt,
            "summary": self.summary,
            "error_message": self.error_message,
            "transcript_range": list(self.transcript_range),
            "provider_terminal_event": self.provider_terminal_event,
            "status_snapshot": dict(self.status_snapshot),
            "assignment_ref": dict(self.assignment_ref),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> TabTaskRun | None:
        run_id = _clean_text(payload.get("run_id"))
        tab_id = _clean_text(payload.get("tab_id"))
        if not run_id or not tab_id:
            return None
        raw_range = payload.get("transcript_range")
        transcript_range = (0, 0)
        if isinstance(raw_range, list | tuple) and len(raw_range) >= 2:
            try:
                transcript_range = (max(0, int(raw_range[0])), max(0, int(raw_range[1])))
            except (TypeError, ValueError):
                transcript_range = (0, 0)
        return cls(
            run_id=run_id,
            tab_id=tab_id,
            parent_tab_id=_clean_text(payload.get("parent_tab_id")),
            provider=_clean_text(payload.get("provider")),
            engine=_clean_text(payload.get("engine")),
            state=_normalize_state(payload.get("state")),
            terminal_state=_normalize_terminal_state(payload.get("terminal_state")),
            terminal_reason=_clean_text(payload.get("terminal_reason")),
            objective_state=_normalize_objective_state(payload.get("objective_state")),
            started_at=_safe_float(payload.get("started_at")),
            finished_at=_safe_optional_float(payload.get("finished_at")),
            user_prompt=str(payload.get("user_prompt") or ""),
            summary=str(payload.get("summary") or ""),
            error_message=str(payload.get("error_message") or ""),
            transcript_range=transcript_range,
            provider_terminal_event=(
                dict(payload.get("provider_terminal_event"))
                if isinstance(payload.get("provider_terminal_event"), dict)
                else None
            ),
            status_snapshot=_clean_mapping(payload.get("status_snapshot")),
            assignment_ref=_clean_mapping(payload.get("assignment_ref")),
        )


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

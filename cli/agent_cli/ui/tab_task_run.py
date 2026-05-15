from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal

from cli.agent_cli.ui.tab_task_run_projection_runtime import (
    _clean_mapping,
    _clean_text,
    _event_type,
    _normalize_objective_state,
    _normalize_state,
    _normalize_terminal_state,
    _safe_float,
    _safe_optional_float,
    _terminal_event_from_turn_events,
    _terminal_reason_from_response,
    _terminal_state_from_turn_event,
    objective_state_from_response,
    queued_task_run,
    summary_from_response,
    task_run_from_exception,
    task_run_from_response,
)

__all__ = [
    "TERMINAL_STATES",
    "TabRole",
    "TabTaskRun",
    "TaskObjectiveState",
    "TaskRunState",
    "TaskTerminalState",
    "_clean_mapping",
    "_clean_text",
    "_event_type",
    "_normalize_objective_state",
    "_normalize_state",
    "_normalize_terminal_state",
    "_safe_float",
    "_safe_optional_float",
    "_terminal_event_from_turn_events",
    "_terminal_reason_from_response",
    "_terminal_state_from_turn_event",
    "current_time",
    "objective_state_from_response",
    "queued_task_run",
    "summary_from_response",
    "task_run_from_exception",
    "task_run_from_response",
]

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

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from cli.agent_cli.ui.transcript_browsing_runtime import (
    TranscriptBrowsingState,
    find_transcript_matches,
)


@dataclass(slots=True, frozen=True)
class RequestUserInputPendingProjection:
    payload: dict[str, Any]
    question_ids: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class RequestUserInputNoticeProjection:
    key: str
    legacy_en: str
    kwargs: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class ExitRequestProjection:
    thread_id: str
    resume_command: str


def build_transcript_search_state(
    *,
    transcript_entries: list[Any],
    query: str,
    current_state: TranscriptBrowsingState,
) -> TranscriptBrowsingState:
    matches = tuple(find_transcript_matches(transcript_entries, query))
    active_index = 0 if matches else -1
    active_entry_id = matches[active_index] if matches else None
    sticky_hint = str(getattr(current_state, "sticky_task_hint", "") or "")
    anchor_entry_id = active_entry_id or getattr(current_state, "anchor_entry_id", None)
    return TranscriptBrowsingState(
        query=str(query or ""),
        match_entry_ids=matches,
        active_match_index=active_index,
        anchor_entry_id=anchor_entry_id,
        sticky_task_hint=sticky_hint,
    )


def build_request_user_input_pending(
    questions: Iterable[Mapping[str, Any]],
) -> RequestUserInputPendingProjection:
    items = [dict(item) for item in questions]
    return RequestUserInputPendingProjection(
        payload={"questions": items},
        question_ids=tuple(str(item.get("id") or "").strip() for item in items),
    )


def request_user_input_requested_notice(question_count: int) -> RequestUserInputNoticeProjection:
    if int(question_count) == 1:
        return RequestUserInputNoticeProjection(
            key="system.request_user_input.requested.one",
            legacy_en="Model requested user input (1 question).",
        )
    return RequestUserInputNoticeProjection(
        key="system.request_user_input.requested.other",
        legacy_en="Model requested user input ({count} questions).",
        kwargs={"count": int(question_count)},
    )


def request_user_input_interactive_unavailable_notice() -> RequestUserInputNoticeProjection:
    return RequestUserInputNoticeProjection(
        key="system.request_user_input.cancelled.interactive_unavailable",
        legacy_en="request_user_input cancelled: interactive UI unavailable.",
    )


def request_user_input_user_cancelled_notice() -> RequestUserInputNoticeProjection:
    return RequestUserInputNoticeProjection(
        key="system.request_user_input.cancelled.user",
        legacy_en="User cancelled input request.",
    )


def request_user_input_cancelled_reason_notice(reason_label: str) -> RequestUserInputNoticeProjection:
    return RequestUserInputNoticeProjection(
        key="system.request_user_input.cancelled.reason",
        legacy_en="request_user_input cancelled: {reason}.",
        kwargs={"reason": reason_label},
    )


def request_user_input_modal_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(payload or {})


def fallback_exit_payload(runtime: Any) -> dict[str, str]:
    thread_id = str(getattr(runtime, "thread_id", "") or "").strip()
    return {
        "thread_id": thread_id,
        "thread_name": str(getattr(runtime, "thread_name", "") or "").strip(),
        "resume_command": f"agenthub resume {thread_id}" if thread_id else "",
    }


def exit_request_projection(payload: Mapping[str, Any] | None) -> ExitRequestProjection:
    values = dict(payload or {})
    return ExitRequestProjection(
        thread_id=str(values.get("thread_id") or "").strip(),
        resume_command=str(values.get("resume_command") or "").strip(),
    )


__all__ = [
    "ExitRequestProjection",
    "RequestUserInputNoticeProjection",
    "RequestUserInputPendingProjection",
    "build_request_user_input_pending",
    "build_transcript_search_state",
    "exit_request_projection",
    "fallback_exit_payload",
    "request_user_input_cancelled_reason_notice",
    "request_user_input_interactive_unavailable_notice",
    "request_user_input_modal_payload",
    "request_user_input_requested_notice",
    "request_user_input_user_cancelled_notice",
]

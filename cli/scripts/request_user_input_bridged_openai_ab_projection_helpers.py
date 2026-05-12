from __future__ import annotations

from typing import Any

try:
    from cli.scripts.request_user_input_bridged_openai_ab_runtime_helpers import ProbeResult
except ModuleNotFoundError:  # pragma: no cover - direct script path
    from request_user_input_bridged_openai_ab_runtime_helpers import ProbeResult  # type: ignore[no-redef]


def _public_request_shape(message: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(message, dict):
        return None
    params = dict(message.get("params") or {})
    questions = list(params.get("questions") or [])
    return {
        "method": message.get("method"),
        "threadId": params.get("threadId"),
        "turnId": params.get("turnId"),
        "itemId": params.get("itemId"),
        "questionCount": len(questions),
        "questions": questions,
    }


def _completed_status(message: dict[str, Any]) -> dict[str, Any]:
    params = dict(message.get("params") or {})
    turn = dict(params.get("turn") or {})
    return {
        "method": message.get("method"),
        "synthetic": bool(message.get("synthetic")),
        "threadId": params.get("threadId"),
        "turnId": turn.get("id"),
        "status": turn.get("status"),
        "error": turn.get("error"),
        "items": turn.get("items"),
    }


def _final_answer_summary(message: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(message, dict):
        return None
    params = dict(message.get("params") or {})
    item = dict(params.get("item") or {})
    if not item:
        return None
    text = item.get("text")
    if text is None:
        content = list(item.get("content") or [])
        if content and isinstance(content[0], dict):
            text = content[0].get("text")
    return {
        "method": message.get("method"),
        "threadId": params.get("threadId"),
        "turnId": params.get("turnId"),
        "itemId": item.get("id"),
        "phase": item.get("phase"),
        "text": text,
    }


def _is_completed(message: dict[str, Any]) -> bool:
    return _completed_status(message).get("status") == "completed"


def _is_missing_turn_completed_after_final_answer(probe: ProbeResult) -> bool:
    return probe.final_answer_message is not None and not _is_completed(probe.completed_message)


def _turn_completion_outcome(agenthub: ProbeResult, codex: ProbeResult) -> str:
    agenthub_missing = _is_missing_turn_completed_after_final_answer(agenthub)
    codex_missing = _is_missing_turn_completed_after_final_answer(codex)
    if _is_completed(agenthub.completed_message) and _is_completed(codex.completed_message):
        return "both_completed"
    if agenthub_missing and codex_missing:
        return "both_missing_after_final_answer"
    if agenthub_missing:
        return "agenthub_missing_after_final_answer"
    if codex_missing:
        return "codex_missing_after_final_answer"
    return "other_non_completed_outcome"


def _parity_verdict(agenthub: ProbeResult, codex: ProbeResult) -> dict[str, str]:
    both_requested = bool(agenthub.request_user_input_message and codex.request_user_input_message)
    both_resolved = bool(agenthub.resolved_message and codex.resolved_message)
    both_final_answer = bool(agenthub.final_answer_message and codex.final_answer_message)
    outcome = _turn_completion_outcome(agenthub, codex)
    if both_requested and both_resolved and both_final_answer and outcome == "both_completed":
        return {
            "code": "pass",
            "reason": "Both AgentHub and codex_ref completed the bridged request_user_input turn end-to-end.",
        }
    if both_requested and both_resolved and both_final_answer and outcome in {
        "agenthub_missing_after_final_answer",
        "codex_missing_after_final_answer",
        "both_missing_after_final_answer",
    }:
        return {
            "code": "inconclusive_live_close_instability",
            "reason": "Final answer was observed, but turn/completed was missing on at least one side within timeout; do not treat a single run as product attribution.",
        }
    return {
        "code": "contract_or_bridge_gap",
        "reason": "The two sides diverged before stable final-answer-and-close behavior, so inspect tool contract or bridge semantics first.",
    }

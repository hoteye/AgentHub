from __future__ import annotations

from typing import Any


OPERATOR_STATUS_KEYS = (
    "agent_id",
    "task_id",
    "role",
    "status",
    "workflow_state",
    "queue_state",
    "scheduler_reason",
    "adopted",
    "adopted_at",
    "completion_state",
    "result_state",
    "adoption_expectation",
    "terminal_state",
    "terminal_reason",
    "pending_input_count",
    "final_apply_state",
    "timed_out",
    "timeout_hit",
    "summary",
    "command_policies",
)
OPERATOR_HINT_KEYS = ("operator_hint_text",)
OPERATOR_EVIDENCE_KEYS = (
    "operator_evidence_subject_kind",
    "operator_evidence_subject_id",
    "operator_evidence_lifecycle_state",
    "operator_evidence_review_state",
    "operator_evidence_state_source",
    "operator_evidence_subject_source",
)
OPERATOR_PAYLOAD_KEYS = frozenset(
    {
        "agent_id",
        "task_id",
        "role",
        "workflow_state",
        "queue_state",
        "scheduler_reason",
        "completion_state",
        "result_state",
        "adoption_expectation",
        "terminal_state",
        "terminal_reason",
        "pending_input_count",
        "final_apply_state",
        "adopted_at",
    }
)

_OPERATOR_QUEUED_STATES = frozenset({"queued", "starting"})
_OPERATOR_RUNNING_STATES = frozenset({"running", "closing"})
_OPERATOR_RETURNED_COMPLETION_STATES = frozenset({"ready_to_adopt", "awaiting_join"})
_OPERATOR_EVIDENCE_STATE_KEYS = (
    "operator_evidence_lifecycle_state",
    "operator_evidence_review_state",
)
_OPERATOR_EVIDENCE_SUBJECT_KEYS = (
    "operator_evidence_subject_kind",
    "operator_evidence_subject_id",
)
_OPERATOR_ARTIFACT_STATUS_KEYS = (
    "status",
    "workflow_state",
    "queue_state",
    "scheduler_reason",
    "completion_state",
    "result_state",
    "adoption_expectation",
    "adopted",
    "adopted_at",
    "terminal_state",
    "terminal_reason",
    "summary",
    "final_apply_state",
    "timed_out",
    "timeout_hit",
    "command_policies",
)


def status_text(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value or "").strip()
    return text or "-"


def boolish_status(value: Any) -> bool | None:
    normalized = str(value or "").strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return None


def normalized_status(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"", "-", "none", "null"}:
        return ""
    return normalized


def operator_primary_state(
    *,
    status: Any,
    workflow_state: Any,
    queue_state: Any,
    completion_state: Any,
    result_state: Any,
    adoption_expectation: Any,
    terminal_state: Any,
    adopted: bool | None,
    timed_out: bool | None,
    timeout_hit: bool | None,
) -> str:
    status_normalized = normalized_status(status)
    workflow_normalized = normalized_status(workflow_state)
    queue_normalized = normalized_status(queue_state)
    completion_normalized = normalized_status(completion_state)
    result_normalized = normalized_status(result_state)
    expectation_normalized = normalized_status(adoption_expectation)
    terminal_normalized = normalized_status(terminal_state)
    terminal_candidates = (
        terminal_normalized,
        status_normalized,
        workflow_normalized,
        queue_normalized,
        completion_normalized,
    )
    if timed_out is True or timeout_hit is True or "timed_out" in terminal_candidates:
        return "timed_out"
    if any(item == "failed" for item in terminal_candidates):
        return "failed"
    if any(item == "cancelled" for item in terminal_candidates):
        return "cancelled"
    if adopted is True or completion_normalized == "adopted" or result_normalized == "adopted":
        return "adopted"
    if result_normalized in {"blocked", "block", "rejected", "reject"}:
        return "blocked"
    if result_normalized in {"returned", "pending_review", "review_pending"}:
        return "returned"
    if completion_normalized in _OPERATOR_RETURNED_COMPLETION_STATES:
        return "returned"
    if completion_normalized == "completed" and adopted is False and expectation_normalized:
        return "returned"
    if any(item in _OPERATOR_QUEUED_STATES for item in terminal_candidates):
        return "queued"
    if any(item in _OPERATOR_RUNNING_STATES for item in terminal_candidates):
        return "running"
    if any(item == "completed" for item in terminal_candidates):
        return "completed"
    for candidate in terminal_candidates:
        if candidate:
            return candidate
    return ""


def merged_operator_key_values(*mappings: Any) -> dict[str, str]:
    merged: dict[str, str] = {}
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        for raw_key, raw_value in mapping.items():
            key = str(raw_key or "").strip()
            if not key:
                continue
            value = status_text(raw_value)
            if key not in merged:
                merged[key] = value
                continue
            if merged[key] in {"", "-"} and value not in {"", "-"}:
                merged[key] = value
    return merged


def operator_primary_state_from_mapping(values: dict[str, Any]) -> str:
    mapping = dict(values or {})
    return operator_primary_state(
        status=mapping.get("status"),
        workflow_state=mapping.get("workflow_state"),
        queue_state=mapping.get("queue_state"),
        completion_state=mapping.get("completion_state"),
        result_state=mapping.get("result_state"),
        adoption_expectation=mapping.get("adoption_expectation"),
        terminal_state=mapping.get("terminal_state"),
        adopted=boolish_status(mapping.get("adopted")),
        timed_out=boolish_status(mapping.get("timed_out")),
        timeout_hit=boolish_status(mapping.get("timeout_hit")),
    )


def operator_review_state(
    *,
    result_state: Any,
    completion_state: Any,
    final_apply_state: Any,
) -> str:
    normalized_result = normalized_status(result_state)
    normalized_completion = normalized_status(completion_state)
    normalized_review = normalized_status(final_apply_state)
    if normalized_review == "blocked" or normalized_result in {"blocked", "block", "rejected", "reject"}:
        return "blocked"
    if normalized_review in {"pending", "review_pending"}:
        return "pending"
    if normalized_result in {"pending_review", "review_pending"}:
        return "pending"
    if normalized_result:
        return ""
    if normalized_completion in {"ready_to_adopt", "awaiting_join", "pending_review"}:
        return "pending"
    return ""


def operator_review_state_from_mapping(values: dict[str, Any]) -> str:
    mapping = dict(values or {})
    return operator_review_state(
        result_state=mapping.get("result_state"),
        completion_state=mapping.get("completion_state"),
        final_apply_state=mapping.get("final_apply_state"),
    )


def operator_review_evidence_state(
    *,
    result_state: Any,
    completion_state: Any,
    final_apply_state: Any,
) -> str:
    review_state = normalized_status(
        operator_review_state(
            result_state=result_state,
            completion_state=completion_state,
            final_apply_state=final_apply_state,
        )
    )
    if review_state == "pending":
        return "review_pending"
    return review_state


def operator_review_evidence_state_from_mapping(values: dict[str, Any]) -> str:
    mapping = dict(values or {})
    return operator_review_evidence_state(
        result_state=mapping.get("result_state"),
        completion_state=mapping.get("completion_state"),
        final_apply_state=mapping.get("final_apply_state"),
    )


def normalized_count(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text == "-":
        return "-"
    try:
        return str(max(0, int(text)))
    except (TypeError, ValueError):
        return text

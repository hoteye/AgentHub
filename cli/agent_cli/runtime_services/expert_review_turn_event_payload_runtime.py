from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from cli.agent_cli.runtime_services.expert_review_result_runtime import (
    EXPERT_REVIEW_FOCUS_AREAS,
    EXPERT_REVIEW_RESULT_CONTRACT_VERSION,
    EXPERT_REVIEW_STRICTNESS_LEVELS,
    EXPERT_REVIEW_TOOL_FAMILY,
)
from cli.agent_cli.runtime_services.expert_review_reviewer_capability_runtime import (
    EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY,
    EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE,
)

EXPERT_REVIEW_TURN_ITEM_TYPE = "expert_review"
EXPERT_REVIEW_TURN_PHASES = ("requested", "running", "completed", "failed")

DEFAULT_SCOPE = "current_task"
DEFAULT_STRICTNESS = "medium"
DEFAULT_MAX_FINDINGS = 5
_TRUE_VALUES = {"1", "true", "yes", "on", "enabled"}
_FALSE_VALUES = {"0", "false", "no", "off", "disabled"}


def normalized_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalized_choice(value: Any, *, allowed: tuple[str, ...], default: str) -> str:
    normalized = normalized_text(value).lower()
    if normalized in allowed:
        return normalized
    return default


def sequence_items(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, (set, frozenset)):
        return sorted(list(value), key=lambda item: str(item))
    return [value]


def normalized_string_list(value: Any, *, allowed: tuple[str, ...] | None = None) -> list[str]:
    items: list[str] = []
    allowed_values = set(allowed or ())
    for raw_item in sequence_items(value):
        normalized = normalized_text(raw_item)
        if not normalized:
            continue
        if allowed_values:
            normalized = normalized.lower()
            if normalized not in allowed_values:
                continue
        if normalized not in items:
            items.append(normalized)
    return items


def normalized_optional_bool(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    normalized = normalized_text(value).lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    return bool(value)


def normalized_nonnegative_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, normalized)


def normalize_scope(value: Any) -> str:
    normalized = normalized_text(value).lower()
    if normalized in {"latest_turn", "current_task", "selected_artifacts"}:
        return normalized
    return DEFAULT_SCOPE


def normalize_max_findings(value: Any) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MAX_FINDINGS
    return max(1, min(10, normalized))


def request_payload(
    *,
    task: Any,
    scope: Any,
    focus: Sequence[Any] | Any = None,
    artifact_paths: Sequence[Any] | Any = None,
    max_findings: Any = DEFAULT_MAX_FINDINGS,
    strictness: Any = DEFAULT_STRICTNESS,
) -> dict[str, Any]:
    return {
        "task": normalized_text(task),
        "scope": normalize_scope(scope),
        "focus": normalized_string_list(focus, allowed=EXPERT_REVIEW_FOCUS_AREAS),
        "artifact_paths": normalized_string_list(artifact_paths),
        "max_findings": normalize_max_findings(max_findings),
        "strictness": normalized_choice(
            strictness,
            allowed=EXPERT_REVIEW_STRICTNESS_LEVELS,
            default=DEFAULT_STRICTNESS,
        ),
    }


def reviewer_payload(
    *,
    reviewer_provider: Any = "",
    reviewer_model: Any = "",
    reviewer_reasoning_strategy: Any = "",
    reviewer_reasoning_effort: Any = "",
    reviewer_reasoning_mode: Any = "",
    reviewer_capability_policy: Any = EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY,
    reviewer_capability_source: Any = EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE,
    cross_provider: Any = None,
    cross_vendor: Any = None,
    selection_reason: Any = "",
) -> dict[str, Any]:
    return {
        "provider": normalized_text(reviewer_provider),
        "model": normalized_text(reviewer_model),
        "reasoning_strategy": normalized_text(reviewer_reasoning_strategy),
        "reasoning_effort": normalized_text(reviewer_reasoning_effort),
        "reasoning_mode": normalized_text(reviewer_reasoning_mode),
        "capability_policy": normalized_text(reviewer_capability_policy)
        or EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY,
        "capability_source": normalized_text(reviewer_capability_source)
        or EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE,
        "cross_provider": normalized_optional_bool(cross_provider),
        "cross_vendor": normalized_optional_bool(cross_vendor),
        "selection_reason": normalized_text(selection_reason),
    }


def outcome_payload(
    *,
    status: str,
    verdict: Any = "",
    finding_count: Any = 0,
    error_code: Any = "",
    retryable: Any = False,
    review_elapsed_ms: Any = None,
) -> dict[str, Any]:
    normalized_finding_count = normalized_nonnegative_int(finding_count)
    return {
        "status": normalized_text(status),
        "verdict": normalized_text(verdict).lower(),
        "finding_count": normalized_finding_count if normalized_finding_count is not None else 0,
        "error_code": normalized_text(error_code).lower(),
        "retryable": bool(retryable),
        "review_elapsed_ms": normalized_nonnegative_int(review_elapsed_ms),
    }


def item_payload(
    *,
    item_id: Any,
    call_id: Any = "",
    phase: str,
    item_status: str,
    summary: Any,
    request: dict[str, Any],
    reviewer: dict[str, Any],
    outcome: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": normalized_text(item_id),
        "call_id": normalized_text(call_id) or None,
        "type": EXPERT_REVIEW_TURN_ITEM_TYPE,
        "tool_family": EXPERT_REVIEW_TOOL_FAMILY,
        "contract_version": EXPERT_REVIEW_RESULT_CONTRACT_VERSION,
        "advisory": True,
        "phase": phase,
        "event_name": f"expert_review_{phase}",
        "status": item_status,
        "summary": normalized_text(summary),
        "request": request,
        "reviewer": reviewer,
        "outcome": outcome,
    }

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from cli.agent_cli.runtime_services.expert_review_result_runtime import (
    build_expert_review_failure_result,
    build_expert_review_success_result,
    expert_review_reviewer_identity,
)
from cli.agent_cli.runtime_services.expert_review_reviewer_capability_runtime import (
    EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY,
    EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE,
)
from cli.agent_cli.runtime_services.expert_review_turn_event_payload_runtime import (
    DEFAULT_MAX_FINDINGS as _DEFAULT_MAX_FINDINGS,
    DEFAULT_SCOPE as _DEFAULT_SCOPE,
    DEFAULT_STRICTNESS as _DEFAULT_STRICTNESS,
    EXPERT_REVIEW_TURN_ITEM_TYPE,
    EXPERT_REVIEW_TURN_PHASES,
    item_payload as _item_payload,
    normalized_optional_bool as _normalized_optional_bool,
    normalized_text as _normalized_text,
    outcome_payload as _outcome_payload,
    request_payload as _request_payload,
    reviewer_payload as _reviewer_payload,
)


def build_expert_review_requested_turn_event(
    *,
    item_id: Any,
    call_id: Any = "",
    task: Any,
    scope: Any = _DEFAULT_SCOPE,
    focus: Sequence[Any] | Any = None,
    artifact_paths: Sequence[Any] | Any = None,
    max_findings: Any = _DEFAULT_MAX_FINDINGS,
    strictness: Any = _DEFAULT_STRICTNESS,
    summary: Any = "",
) -> dict[str, Any]:
    item = _item_payload(
        item_id=item_id,
        call_id=call_id,
        phase="requested",
        item_status="in_progress",
        summary=_normalized_text(summary) or "Expert review requested.",
        request=_request_payload(
            task=task,
            scope=scope,
            focus=focus,
            artifact_paths=artifact_paths,
            max_findings=max_findings,
            strictness=strictness,
        ),
        reviewer=_reviewer_payload(),
        outcome=_outcome_payload(status="pending"),
    )
    return {"type": "item.started", "item": item}


def build_expert_review_running_turn_event(
    *,
    item_id: Any,
    call_id: Any = "",
    task: Any,
    scope: Any = _DEFAULT_SCOPE,
    focus: Sequence[Any] | Any = None,
    artifact_paths: Sequence[Any] | Any = None,
    max_findings: Any = _DEFAULT_MAX_FINDINGS,
    strictness: Any = _DEFAULT_STRICTNESS,
    reviewer_provider: Any = "",
    reviewer_model: Any = "",
    reviewer_reasoning_strategy: Any = "",
    reviewer_reasoning_effort: Any = "",
    reviewer_reasoning_mode: Any = "",
    reviewer_capability_policy: Any = EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY,
    reviewer_capability_source: Any = EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE,
    cross_provider: Any = True,
    cross_vendor: Any = False,
    selection_reason: Any = "",
    summary: Any = "",
) -> dict[str, Any]:
    item = _item_payload(
        item_id=item_id,
        call_id=call_id,
        phase="running",
        item_status="in_progress",
        summary=_normalized_text(summary) or "Expert review running.",
        request=_request_payload(
            task=task,
            scope=scope,
            focus=focus,
            artifact_paths=artifact_paths,
            max_findings=max_findings,
            strictness=strictness,
        ),
        reviewer=_reviewer_payload(
            reviewer_provider=reviewer_provider,
            reviewer_model=reviewer_model,
            reviewer_reasoning_strategy=reviewer_reasoning_strategy,
            reviewer_reasoning_effort=reviewer_reasoning_effort,
            reviewer_reasoning_mode=reviewer_reasoning_mode,
            reviewer_capability_policy=reviewer_capability_policy,
            reviewer_capability_source=reviewer_capability_source,
            cross_provider=cross_provider,
            cross_vendor=cross_vendor,
            selection_reason=selection_reason,
        ),
        outcome=_outcome_payload(status="running"),
    )
    return {
        "type": "item.updated",
        "item": item,
        "updated": {
            "phase": item["phase"],
            "event_name": item["event_name"],
            "status": item["status"],
            "summary": item["summary"],
        },
    }


def build_expert_review_completed_turn_event(
    *,
    item_id: Any,
    call_id: Any = "",
    task: Any,
    verdict: Any,
    confidence: Any = "medium",
    findings: Any = None,
    reviewer_provider: Any = "",
    reviewer_model: Any = "",
    reviewer_reasoning_strategy: Any = "",
    reviewer_reasoning_effort: Any = "",
    reviewer_reasoning_mode: Any = "",
    reviewer_capability_policy: Any = EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY,
    reviewer_capability_source: Any = EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE,
    cross_provider: Any = True,
    cross_vendor: Any = False,
    scope: Any = _DEFAULT_SCOPE,
    focus: Sequence[Any] | Any = None,
    artifact_paths: Sequence[Any] | Any = None,
    max_findings: Any = _DEFAULT_MAX_FINDINGS,
    strictness: Any = _DEFAULT_STRICTNESS,
    recommended_action: Any = "",
    review_elapsed_ms: Any = None,
    summary: Any = "",
    selection_reason: Any = "",
) -> dict[str, Any]:
    normalized_cross_provider = _normalized_optional_bool(cross_provider)
    normalized_cross_vendor = _normalized_optional_bool(cross_vendor)
    result = build_expert_review_success_result(
        verdict=verdict,
        confidence=confidence,
        findings=findings,
        reviewer_provider=reviewer_provider,
        reviewer_model=reviewer_model,
        reviewer_reasoning_strategy=reviewer_reasoning_strategy,
        reviewer_reasoning_effort=reviewer_reasoning_effort,
        reviewer_reasoning_mode=reviewer_reasoning_mode,
        reviewer_capability_policy=reviewer_capability_policy,
        reviewer_capability_source=reviewer_capability_source,
        cross_provider=True if normalized_cross_provider is None else normalized_cross_provider,
        cross_vendor=False if normalized_cross_vendor is None else normalized_cross_vendor,
        scope=scope,
        focus=focus,
        strictness=strictness,
        recommended_action=recommended_action,
        review_elapsed_ms=review_elapsed_ms,
        summary=summary,
    )
    structured_payload = dict(result.get("structured_payload") or {})
    reviewer = expert_review_reviewer_identity(structured_payload)
    item = _item_payload(
        item_id=item_id,
        call_id=call_id,
        phase="completed",
        item_status="completed",
        summary=result.get("summary"),
        request=_request_payload(
            task=task,
            scope=scope,
            focus=focus,
            artifact_paths=artifact_paths,
            max_findings=max_findings,
            strictness=strictness,
        ),
        reviewer=_reviewer_payload(
            reviewer_provider=reviewer.get("provider"),
            reviewer_model=reviewer.get("model"),
            reviewer_reasoning_strategy=reviewer.get("reasoning_strategy"),
            reviewer_reasoning_effort=reviewer.get("reasoning_effort"),
            reviewer_reasoning_mode=reviewer.get("reasoning_mode"),
            reviewer_capability_policy=reviewer.get("capability_policy"),
            reviewer_capability_source=reviewer.get("capability_source"),
            cross_provider=structured_payload.get("cross_provider"),
            cross_vendor=structured_payload.get("cross_vendor"),
            selection_reason=selection_reason,
        ),
        outcome=_outcome_payload(
            status=result.get("status") or "ok",
            verdict=structured_payload.get("verdict"),
            finding_count=structured_payload.get("finding_count"),
            review_elapsed_ms=structured_payload.get("review_elapsed_ms"),
        ),
    )
    return {"type": "item.completed", "item": item, "result": result}


def build_expert_review_failed_turn_event(
    *,
    item_id: Any,
    call_id: Any = "",
    task: Any,
    error_code: Any,
    retryable: bool = False,
    detail: Any = "",
    reviewer_provider: Any = "",
    reviewer_model: Any = "",
    reviewer_reasoning_strategy: Any = "",
    reviewer_reasoning_effort: Any = "",
    reviewer_reasoning_mode: Any = "",
    reviewer_capability_policy: Any = EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY,
    reviewer_capability_source: Any = EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE,
    cross_provider: Any = None,
    cross_vendor: Any = None,
    scope: Any = _DEFAULT_SCOPE,
    focus: Sequence[Any] | Any = None,
    artifact_paths: Sequence[Any] | Any = None,
    max_findings: Any = _DEFAULT_MAX_FINDINGS,
    strictness: Any = _DEFAULT_STRICTNESS,
    stage: Any = "",
    review_elapsed_ms: Any = None,
    summary: Any = "",
    selection_reason: Any = "",
) -> dict[str, Any]:
    result = build_expert_review_failure_result(
        error_code=error_code,
        retryable=retryable,
        detail=detail,
        reviewer_provider=reviewer_provider,
        reviewer_model=reviewer_model,
        reviewer_reasoning_strategy=reviewer_reasoning_strategy,
        reviewer_reasoning_effort=reviewer_reasoning_effort,
        reviewer_reasoning_mode=reviewer_reasoning_mode,
        reviewer_capability_policy=reviewer_capability_policy,
        reviewer_capability_source=reviewer_capability_source,
        scope=scope,
        focus=focus,
        strictness=strictness,
        stage=stage,
        review_elapsed_ms=review_elapsed_ms,
        summary=summary,
    )
    structured_payload = dict(result.get("structured_payload") or {})
    reviewer = expert_review_reviewer_identity(structured_payload)
    item = _item_payload(
        item_id=item_id,
        call_id=call_id,
        phase="failed",
        item_status="failed",
        summary=result.get("summary"),
        request=_request_payload(
            task=task,
            scope=scope,
            focus=focus,
            artifact_paths=artifact_paths,
            max_findings=max_findings,
            strictness=strictness,
        ),
        reviewer=_reviewer_payload(
            reviewer_provider=reviewer.get("provider"),
            reviewer_model=reviewer.get("model"),
            reviewer_reasoning_strategy=reviewer.get("reasoning_strategy"),
            reviewer_reasoning_effort=reviewer.get("reasoning_effort"),
            reviewer_reasoning_mode=reviewer.get("reasoning_mode"),
            reviewer_capability_policy=reviewer.get("capability_policy"),
            reviewer_capability_source=reviewer.get("capability_source"),
            cross_provider=cross_provider,
            cross_vendor=cross_vendor,
            selection_reason=selection_reason,
        ),
        outcome=_outcome_payload(
            status=result.get("status") or "error",
            error_code=structured_payload.get("error_code"),
            retryable=structured_payload.get("retryable"),
            review_elapsed_ms=structured_payload.get("review_elapsed_ms"),
        ),
    )
    return {"type": "item.completed", "item": item, "result": result}


__all__ = [
    "EXPERT_REVIEW_TURN_ITEM_TYPE",
    "EXPERT_REVIEW_TURN_PHASES",
    "build_expert_review_completed_turn_event",
    "build_expert_review_failed_turn_event",
    "build_expert_review_requested_turn_event",
    "build_expert_review_running_turn_event",
]

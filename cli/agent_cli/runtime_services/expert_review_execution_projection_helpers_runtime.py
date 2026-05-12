from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

from cli.agent_cli.runtime_services.expert_review_execution_pure_helpers_runtime import (
    ReviewerExecutionMetadata,
)


def build_execution_failure_result_and_event(
    *,
    request_payload: Mapping[str, Any],
    item_id: str,
    call_id: str,
    error_code: str,
    detail: str,
    review_elapsed_ms: int,
    failure_result_builder: Callable[..., dict[str, Any]],
    failed_event_builder: Callable[..., dict[str, Any]],
    selection_reason: str = "",
    reviewer_metadata: ReviewerExecutionMetadata | None = None,
    stage: str = "",
) -> tuple[dict[str, Any], dict[str, Any]]:
    failure_kwargs: dict[str, Any] = {
        "error_code": error_code,
        "detail": detail,
        "scope": request_payload["scope"],
        "focus": request_payload["focus"],
        "strictness": request_payload["strictness"],
        "review_elapsed_ms": review_elapsed_ms,
    }
    if reviewer_metadata is not None:
        failure_kwargs.update(reviewer_metadata.failure_result_kwargs())
    if stage:
        failure_kwargs["stage"] = stage
    failure = failure_result_builder(**failure_kwargs)

    event_kwargs: dict[str, Any] = {
        "item_id": item_id,
        "call_id": call_id,
        **dict(request_payload),
        "error_code": error_code,
        "detail": detail,
        "review_elapsed_ms": review_elapsed_ms,
        "summary": failure.get("summary"),
        "selection_reason": selection_reason,
    }
    if reviewer_metadata is not None:
        event_kwargs.update(reviewer_metadata.event_kwargs())
    if stage:
        event_kwargs["stage"] = stage
    return failure, failed_event_builder(**event_kwargs)


def build_review_running_event(
    *,
    request_payload: Mapping[str, Any],
    item_id: str,
    call_id: str,
    reviewer_metadata: ReviewerExecutionMetadata,
    running_event_builder: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    return running_event_builder(
        item_id=item_id,
        call_id=call_id,
        **dict(request_payload),
        **reviewer_metadata.event_kwargs(),
    )


def build_parsed_review_result_event(
    *,
    parsed_result: Mapping[str, Any],
    request_payload: Mapping[str, Any],
    item_id: str,
    call_id: str,
    reviewer_metadata: ReviewerExecutionMetadata,
    review_elapsed_ms: int,
    wait_failure_detail: str,
    default_parse_error_code: str,
    reviewer_identity_fn: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    completed_event_builder: Callable[..., dict[str, Any]],
    failed_event_builder: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    structured_payload = dict(parsed_result.get("structured_payload") or {})
    reviewer = dict(reviewer_identity_fn(structured_payload) or {})
    reviewer_provider = reviewer.get("provider") or reviewer_metadata.reviewer_provider
    reviewer_model = reviewer.get("model") or reviewer_metadata.reviewer_model
    if str(parsed_result.get("status") or "").strip().lower() == "ok":
        return completed_event_builder(
            item_id=item_id,
            call_id=call_id,
            **dict(request_payload),
            verdict=structured_payload.get("verdict"),
            confidence=structured_payload.get("confidence"),
            findings=structured_payload.get("findings"),
            reviewer_provider=reviewer_provider,
            reviewer_model=reviewer_model,
            reviewer_reasoning_strategy=reviewer.get("reasoning_strategy"),
            reviewer_reasoning_effort=reviewer.get("reasoning_effort"),
            reviewer_reasoning_mode=reviewer.get("reasoning_mode"),
            reviewer_capability_policy=reviewer.get("capability_policy"),
            reviewer_capability_source=reviewer.get("capability_source"),
            cross_provider=structured_payload.get("cross_provider"),
            cross_vendor=structured_payload.get("cross_vendor"),
            recommended_action=structured_payload.get("recommended_action"),
            review_elapsed_ms=structured_payload.get("review_elapsed_ms") or review_elapsed_ms,
            summary=parsed_result.get("summary"),
            selection_reason=reviewer_metadata.selection_reason,
        )
    return failed_event_builder(
        item_id=item_id,
        call_id=call_id,
        **dict(request_payload),
        error_code=structured_payload.get("error_code") or default_parse_error_code,
        detail=structured_payload.get("detail") or wait_failure_detail,
        reviewer_provider=reviewer_provider,
        reviewer_model=reviewer_model,
        reviewer_reasoning_strategy=reviewer.get("reasoning_strategy"),
        reviewer_reasoning_effort=reviewer.get("reasoning_effort"),
        reviewer_reasoning_mode=reviewer.get("reasoning_mode"),
        reviewer_capability_policy=reviewer.get("capability_policy"),
        reviewer_capability_source=reviewer.get("capability_source"),
        cross_provider=reviewer_metadata.cross_provider,
        cross_vendor=reviewer_metadata.cross_vendor,
        stage=structured_payload.get("stage") or "parse",
        review_elapsed_ms=structured_payload.get("review_elapsed_ms") or review_elapsed_ms,
        summary=parsed_result.get("summary"),
        selection_reason=reviewer_metadata.selection_reason,
    )


__all__ = [
    "build_execution_failure_result_and_event",
    "build_parsed_review_result_event",
    "build_review_running_event",
]

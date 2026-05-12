from __future__ import annotations

from typing import Any, Dict, Mapping

from cli.agent_cli.runtime_services.expert_review_reviewer_capability_runtime import (
    EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY,
    EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE,
)
from cli.agent_cli.runtime_services.expert_review_result_helpers_runtime import (
    EXPERT_REVIEW_CONFIDENCE_LEVELS,
    EXPERT_REVIEW_ERROR_CODES,
    EXPERT_REVIEW_ERROR_DELEGATE_FAILED,
    EXPERT_REVIEW_ERROR_NO_ELIGIBLE_PROVIDER,
    EXPERT_REVIEW_ERROR_NO_REVIEWER_CANDIDATE,
    EXPERT_REVIEW_ERROR_PACKET_BUILD_FAILED,
    EXPERT_REVIEW_ERROR_PARSE_FAILED,
    EXPERT_REVIEW_ERROR_UNAVAILABLE,
    EXPERT_REVIEW_FINDING_CATEGORIES,
    EXPERT_REVIEW_FINDING_SEVERITIES,
    EXPERT_REVIEW_FOCUS_AREAS,
    EXPERT_REVIEW_RESULT_CONTRACT_VERSION,
    EXPERT_REVIEW_STRICTNESS_LEVELS,
    EXPERT_REVIEW_TOOL_FAMILY,
    EXPERT_REVIEW_VERDICTS,
    _DEFAULT_CONFIDENCE,
    _DEFAULT_ERROR_CODE,
    _DEFAULT_RECOMMENDED_ACTION_BY_VERDICT,
    _DEFAULT_SCOPE,
    _DEFAULT_STAGE_BY_ERROR_CODE,
    _DEFAULT_STRICTNESS,
    _DEFAULT_VERDICT,
    _findings_metadata,
    _json_safe,
    _normalized_choice,
    _normalized_findings,
    _normalized_nonnegative_int,
    _normalized_string_list,
    _normalized_text,
    _reviewer_identity_payload,
    _verdict_metadata,
    expert_review_error_summary,
    expert_review_reviewer_identity as _expert_review_reviewer_identity,
    expert_review_success_summary,
    normalize_expert_review_finding as _normalize_expert_review_finding,
)


def normalize_expert_review_finding(
    finding: Mapping[str, Any] | Any,
    *,
    index: int,
) -> Dict[str, Any]:
    return _normalize_expert_review_finding(finding, index=index)


def expert_review_reviewer_identity(payload: Mapping[str, Any] | Any) -> Dict[str, Any]:
    return _expert_review_reviewer_identity(payload)


def build_expert_review_success_payload(
    *,
    verdict: Any,
    confidence: Any = _DEFAULT_CONFIDENCE,
    findings: Any = None,
    reviewer_provider: Any = "",
    reviewer_model: Any = "",
    cross_provider: bool = True,
    cross_vendor: bool = False,
    scope: Any = _DEFAULT_SCOPE,
    focus: Any = None,
    strictness: Any = _DEFAULT_STRICTNESS,
    recommended_action: Any = "",
    review_elapsed_ms: Any = None,
    reviewer_reasoning_strategy: Any = "",
    reviewer_reasoning_effort: Any = "",
    reviewer_reasoning_mode: Any = "",
    reviewer_capability_policy: Any = EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY,
    reviewer_capability_source: Any = EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE,
) -> Dict[str, Any]:
    normalized_verdict = _normalized_choice(
        verdict,
        allowed=EXPERT_REVIEW_VERDICTS,
        default=_DEFAULT_VERDICT,
    )
    normalized_confidence = _normalized_choice(
        confidence,
        allowed=EXPERT_REVIEW_CONFIDENCE_LEVELS,
        default=_DEFAULT_CONFIDENCE,
    )
    normalized_findings = _normalized_findings(findings)
    normalized_focus = _normalized_string_list(
        focus,
        allowed=EXPERT_REVIEW_FOCUS_AREAS,
    )
    normalized_recommended_action = (
        _normalized_text(recommended_action)
        or _DEFAULT_RECOMMENDED_ACTION_BY_VERDICT[normalized_verdict]
    )
    payload: Dict[str, Any] = {
        "tool_family": EXPERT_REVIEW_TOOL_FAMILY,
        "contract_version": EXPERT_REVIEW_RESULT_CONTRACT_VERSION,
        "advisory": True,
        "verdict": normalized_verdict,
        "confidence": normalized_confidence,
        "cross_provider": bool(cross_provider),
        "cross_vendor": bool(cross_vendor),
        "reviewer": _reviewer_identity_payload(
            reviewer_provider=reviewer_provider,
            reviewer_model=reviewer_model,
            reviewer_reasoning_strategy=reviewer_reasoning_strategy,
            reviewer_reasoning_effort=reviewer_reasoning_effort,
            reviewer_reasoning_mode=reviewer_reasoning_mode,
            reviewer_capability_policy=reviewer_capability_policy,
            reviewer_capability_source=reviewer_capability_source,
        ),
        "scope": _normalized_text(scope) or _DEFAULT_SCOPE,
        "focus": normalized_focus,
        "strictness": _normalized_choice(
            strictness,
            allowed=EXPERT_REVIEW_STRICTNESS_LEVELS,
            default=_DEFAULT_STRICTNESS,
        ),
        "findings": normalized_findings,
        "finding_count": len(normalized_findings),
        "recommended_action": normalized_recommended_action,
        "verdict_metadata": _verdict_metadata(
            verdict=normalized_verdict,
            confidence=normalized_confidence,
            findings=normalized_findings,
            recommended_action=normalized_recommended_action,
        ),
        "findings_metadata": _findings_metadata(normalized_findings),
    }
    normalized_elapsed_ms = _normalized_nonnegative_int(review_elapsed_ms)
    if normalized_elapsed_ms is not None:
        payload["review_elapsed_ms"] = normalized_elapsed_ms
    return _json_safe(payload)


def build_expert_review_success_result(
    *,
    verdict: Any,
    confidence: Any = _DEFAULT_CONFIDENCE,
    findings: Any = None,
    reviewer_provider: Any = "",
    reviewer_model: Any = "",
    cross_provider: bool = True,
    cross_vendor: bool = False,
    scope: Any = _DEFAULT_SCOPE,
    focus: Any = None,
    strictness: Any = _DEFAULT_STRICTNESS,
    recommended_action: Any = "",
    review_elapsed_ms: Any = None,
    summary: Any = "",
    reviewer_reasoning_strategy: Any = "",
    reviewer_reasoning_effort: Any = "",
    reviewer_reasoning_mode: Any = "",
    reviewer_capability_policy: Any = EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY,
    reviewer_capability_source: Any = EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE,
) -> Dict[str, Any]:
    payload = build_expert_review_success_payload(
        verdict=verdict,
        confidence=confidence,
        findings=findings,
        reviewer_provider=reviewer_provider,
        reviewer_model=reviewer_model,
        cross_provider=cross_provider,
        cross_vendor=cross_vendor,
        scope=scope,
        focus=focus,
        strictness=strictness,
        recommended_action=recommended_action,
        review_elapsed_ms=review_elapsed_ms,
        reviewer_reasoning_strategy=reviewer_reasoning_strategy,
        reviewer_reasoning_effort=reviewer_reasoning_effort,
        reviewer_reasoning_mode=reviewer_reasoning_mode,
        reviewer_capability_policy=reviewer_capability_policy,
        reviewer_capability_source=reviewer_capability_source,
    )
    finding_count = int(payload.get("finding_count") or 0)
    normalized_summary = expert_review_success_summary(
        summary,
        finding_count=finding_count,
    )
    return {
        "status": "ok",
        "summary": normalized_summary,
        "structured_payload": payload,
    }


def build_expert_review_error_payload(
    *,
    error_code: Any,
    retryable: bool = False,
    detail: Any = "",
    reviewer_provider: Any = "",
    reviewer_model: Any = "",
    scope: Any = _DEFAULT_SCOPE,
    focus: Any = None,
    strictness: Any = _DEFAULT_STRICTNESS,
    stage: Any = "",
    review_elapsed_ms: Any = None,
    reviewer_reasoning_strategy: Any = "",
    reviewer_reasoning_effort: Any = "",
    reviewer_reasoning_mode: Any = "",
    reviewer_capability_policy: Any = EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY,
    reviewer_capability_source: Any = EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE,
) -> Dict[str, Any]:
    raw_error_code = _normalized_text(error_code).lower()
    normalized_error_code = (
        raw_error_code if raw_error_code in EXPERT_REVIEW_ERROR_CODES else _DEFAULT_ERROR_CODE
    )
    normalized_stage = _normalized_text(stage).lower() or _DEFAULT_STAGE_BY_ERROR_CODE[
        normalized_error_code
    ]
    normalized_focus = _normalized_string_list(
        focus,
        allowed=EXPERT_REVIEW_FOCUS_AREAS,
    )
    payload: Dict[str, Any] = {
        "tool_family": EXPERT_REVIEW_TOOL_FAMILY,
        "contract_version": EXPERT_REVIEW_RESULT_CONTRACT_VERSION,
        "advisory": True,
        "error_code": normalized_error_code,
        "retryable": bool(retryable),
        "stage": normalized_stage,
        "detail": _normalized_text(detail),
        "reviewer": _reviewer_identity_payload(
            reviewer_provider=reviewer_provider,
            reviewer_model=reviewer_model,
            reviewer_reasoning_strategy=reviewer_reasoning_strategy,
            reviewer_reasoning_effort=reviewer_reasoning_effort,
            reviewer_reasoning_mode=reviewer_reasoning_mode,
            reviewer_capability_policy=reviewer_capability_policy,
            reviewer_capability_source=reviewer_capability_source,
        ),
        "scope": _normalized_text(scope) or _DEFAULT_SCOPE,
        "focus": normalized_focus,
        "strictness": _normalized_choice(
            strictness,
            allowed=EXPERT_REVIEW_STRICTNESS_LEVELS,
            default=_DEFAULT_STRICTNESS,
        ),
        "error_metadata": {
            "stage": normalized_stage,
            "has_reviewer": bool(
                _normalized_text(reviewer_provider) or _normalized_text(reviewer_model)
            ),
        },
    }
    if raw_error_code and raw_error_code != normalized_error_code:
        payload["error_metadata"]["raw_error_code"] = raw_error_code
    normalized_elapsed_ms = _normalized_nonnegative_int(review_elapsed_ms)
    if normalized_elapsed_ms is not None:
        payload["review_elapsed_ms"] = normalized_elapsed_ms
        payload["error_metadata"]["review_elapsed_ms"] = normalized_elapsed_ms
    return _json_safe(payload)


def build_expert_review_failure_result(
    *,
    error_code: Any,
    retryable: bool = False,
    detail: Any = "",
    reviewer_provider: Any = "",
    reviewer_model: Any = "",
    scope: Any = _DEFAULT_SCOPE,
    focus: Any = None,
    strictness: Any = _DEFAULT_STRICTNESS,
    stage: Any = "",
    review_elapsed_ms: Any = None,
    summary: Any = "",
    reviewer_reasoning_strategy: Any = "",
    reviewer_reasoning_effort: Any = "",
    reviewer_reasoning_mode: Any = "",
    reviewer_capability_policy: Any = EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY,
    reviewer_capability_source: Any = EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE,
) -> Dict[str, Any]:
    payload = build_expert_review_error_payload(
        error_code=error_code,
        retryable=retryable,
        detail=detail,
        reviewer_provider=reviewer_provider,
        reviewer_model=reviewer_model,
        scope=scope,
        focus=focus,
        strictness=strictness,
        stage=stage,
        review_elapsed_ms=review_elapsed_ms,
        reviewer_reasoning_strategy=reviewer_reasoning_strategy,
        reviewer_reasoning_effort=reviewer_reasoning_effort,
        reviewer_reasoning_mode=reviewer_reasoning_mode,
        reviewer_capability_policy=reviewer_capability_policy,
        reviewer_capability_source=reviewer_capability_source,
    )
    normalized_error_code = str(payload.get("error_code") or _DEFAULT_ERROR_CODE)
    normalized_summary = expert_review_error_summary(
        summary,
        error_code=normalized_error_code,
    )
    return {
        "status": "error",
        "summary": normalized_summary,
        "structured_payload": payload,
    }


__all__ = [
    "EXPERT_REVIEW_CONFIDENCE_LEVELS",
    "EXPERT_REVIEW_ERROR_CODES",
    "EXPERT_REVIEW_ERROR_DELEGATE_FAILED",
    "EXPERT_REVIEW_ERROR_NO_ELIGIBLE_PROVIDER",
    "EXPERT_REVIEW_ERROR_NO_REVIEWER_CANDIDATE",
    "EXPERT_REVIEW_ERROR_PACKET_BUILD_FAILED",
    "EXPERT_REVIEW_ERROR_PARSE_FAILED",
    "EXPERT_REVIEW_ERROR_UNAVAILABLE",
    "EXPERT_REVIEW_FINDING_CATEGORIES",
    "EXPERT_REVIEW_FINDING_SEVERITIES",
    "EXPERT_REVIEW_FOCUS_AREAS",
    "EXPERT_REVIEW_RESULT_CONTRACT_VERSION",
    "EXPERT_REVIEW_STRICTNESS_LEVELS",
    "EXPERT_REVIEW_TOOL_FAMILY",
    "EXPERT_REVIEW_VERDICTS",
    "build_expert_review_error_payload",
    "build_expert_review_failure_result",
    "build_expert_review_success_payload",
    "build_expert_review_success_result",
    "expert_review_reviewer_identity",
    "normalize_expert_review_finding",
]

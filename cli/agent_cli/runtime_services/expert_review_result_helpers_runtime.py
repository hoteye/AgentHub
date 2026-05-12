from __future__ import annotations

import math
import os
from typing import Any, Dict, Mapping

from cli.agent_cli.runtime_services.expert_review_reviewer_capability_runtime import (
    EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY,
    EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE,
)


EXPERT_REVIEW_TOOL_FAMILY = "expert_review"
EXPERT_REVIEW_RESULT_CONTRACT_VERSION = "v2"

EXPERT_REVIEW_VERDICTS = ("accept", "revise", "block", "uncertain")
EXPERT_REVIEW_CONFIDENCE_LEVELS = ("low", "medium", "high")
EXPERT_REVIEW_FINDING_SEVERITIES = ("low", "medium", "high", "critical")
EXPERT_REVIEW_FINDING_CATEGORIES = (
    "correctness",
    "risk",
    "regression",
    "evidence",
    "completeness",
    "policy",
    "code_quality",
    "other",
)
EXPERT_REVIEW_FOCUS_AREAS = tuple(
    category for category in EXPERT_REVIEW_FINDING_CATEGORIES if category != "other"
)
EXPERT_REVIEW_STRICTNESS_LEVELS = ("low", "medium", "high")
EXPERT_REVIEW_ERROR_UNAVAILABLE = "expert_review_unavailable"
EXPERT_REVIEW_ERROR_NO_ELIGIBLE_PROVIDER = "expert_review_no_eligible_provider"
EXPERT_REVIEW_ERROR_NO_REVIEWER_CANDIDATE = "expert_review_no_reviewer_candidate"
EXPERT_REVIEW_ERROR_PACKET_BUILD_FAILED = "expert_review_packet_build_failed"
EXPERT_REVIEW_ERROR_DELEGATE_FAILED = "expert_review_delegate_failed"
EXPERT_REVIEW_ERROR_PARSE_FAILED = "expert_review_parse_failed"
EXPERT_REVIEW_ERROR_CODES = (
    EXPERT_REVIEW_ERROR_UNAVAILABLE,
    EXPERT_REVIEW_ERROR_NO_ELIGIBLE_PROVIDER,
    EXPERT_REVIEW_ERROR_NO_REVIEWER_CANDIDATE,
    EXPERT_REVIEW_ERROR_PACKET_BUILD_FAILED,
    EXPERT_REVIEW_ERROR_DELEGATE_FAILED,
    EXPERT_REVIEW_ERROR_PARSE_FAILED,
)

_DEFAULT_SCOPE = "current_task"
_DEFAULT_STRICTNESS = "medium"
_DEFAULT_CONFIDENCE = "medium"
_DEFAULT_VERDICT = "uncertain"
_DEFAULT_ERROR_CODE = EXPERT_REVIEW_ERROR_UNAVAILABLE
_SEVERITY_RANK = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
    "none": 0,
}
_DEFAULT_RECOMMENDED_ACTION_BY_VERDICT = {
    "accept": "accept_mainline_output",
    "revise": "revise_and_recheck",
    "block": "block_and_revise",
    "uncertain": "gather_more_evidence",
}
_DEFAULT_ERROR_SUMMARY_BY_CODE = {
    EXPERT_REVIEW_ERROR_UNAVAILABLE: "Expert review is unavailable.",
    EXPERT_REVIEW_ERROR_NO_ELIGIBLE_PROVIDER: (
        "Expert review is unavailable: fewer than two eligible providers."
    ),
    EXPERT_REVIEW_ERROR_NO_REVIEWER_CANDIDATE: (
        "Expert review is unavailable: no reviewer candidate is available."
    ),
    EXPERT_REVIEW_ERROR_PACKET_BUILD_FAILED: (
        "Expert review failed while building the review packet."
    ),
    EXPERT_REVIEW_ERROR_DELEGATE_FAILED: "Expert review failed while running the reviewer.",
    EXPERT_REVIEW_ERROR_PARSE_FAILED: "Expert review failed while parsing reviewer output.",
}
_DEFAULT_STAGE_BY_ERROR_CODE = {
    EXPERT_REVIEW_ERROR_UNAVAILABLE: "gate",
    EXPERT_REVIEW_ERROR_NO_ELIGIBLE_PROVIDER: "gate",
    EXPERT_REVIEW_ERROR_NO_REVIEWER_CANDIDATE: "gate",
    EXPERT_REVIEW_ERROR_PACKET_BUILD_FAILED: "packet_build",
    EXPERT_REVIEW_ERROR_DELEGATE_FAILED: "delegate",
    EXPERT_REVIEW_ERROR_PARSE_FAILED: "parse",
}
_FINDING_KNOWN_KEYS = {
    "severity",
    "category",
    "title",
    "detail",
    "evidence_refs",
    "evidence_ref",
    "metadata",
}


def _normalized_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalized_choice(value: Any, *, allowed: tuple[str, ...], default: str) -> str:
    normalized = _normalized_text(value).lower()
    if normalized in allowed:
        return normalized
    return default


def _sequence_items(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, (set, frozenset)):
        return sorted(list(value), key=lambda item: str(item))
    return [value]


def _normalized_string_list(value: Any, *, allowed: tuple[str, ...] | None = None) -> list[str]:
    normalized_items: list[str] = []
    allowed_values = set(allowed or ())
    for item in _sequence_items(value):
        normalized = _normalized_text(item).lower()
        if not normalized:
            continue
        if allowed_values and normalized not in allowed_values:
            continue
        if normalized not in normalized_items:
            normalized_items.append(normalized)
    return normalized_items


def _normalized_nonnegative_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, normalized)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, os.PathLike):
        return os.fspath(value)
    if isinstance(value, Mapping):
        normalized: Dict[str, Any] = {}
        for key in sorted(value.keys(), key=lambda item: str(item)):
            text_key = _normalized_text(key)
            if not text_key:
                continue
            normalized[text_key] = _json_safe(value[key])
        return normalized
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [_json_safe(item) for item in sorted(list(value), key=lambda item: str(item))]
    return str(value)


def normalize_expert_review_finding(
    finding: Mapping[str, Any] | Any,
    *,
    index: int,
) -> Dict[str, Any]:
    raw_finding = dict(finding) if isinstance(finding, Mapping) else {"detail": finding}
    metadata: Dict[str, Any] = {}
    raw_metadata = raw_finding.get("metadata")
    if isinstance(raw_metadata, Mapping):
        metadata.update(_json_safe(raw_metadata))
    elif raw_metadata is not None and raw_metadata != "":
        metadata["raw_metadata"] = _json_safe(raw_metadata)
    for key in sorted(raw_finding.keys(), key=lambda item: str(item)):
        normalized_key = _normalized_text(key)
        if not normalized_key or normalized_key in _FINDING_KNOWN_KEYS:
            continue
        metadata[normalized_key] = _json_safe(raw_finding[key])
    return {
        "severity": _normalized_choice(
            raw_finding.get("severity"),
            allowed=EXPERT_REVIEW_FINDING_SEVERITIES,
            default="medium",
        ),
        "category": _normalized_choice(
            raw_finding.get("category"),
            allowed=EXPERT_REVIEW_FINDING_CATEGORIES,
            default="other",
        ),
        "title": _normalized_text(raw_finding.get("title")) or f"Finding {index}",
        "detail": _normalized_text(raw_finding.get("detail")),
        "evidence_refs": _normalized_string_list(
            raw_finding.get("evidence_refs")
            if raw_finding.get("evidence_refs") is not None
            else raw_finding.get("evidence_ref")
        ),
        "metadata": metadata,
    }


def _normalized_findings(findings: Any) -> list[Dict[str, Any]]:
    return [
        normalize_expert_review_finding(item, index=index)
        for index, item in enumerate(_sequence_items(findings), start=1)
    ]


def _max_finding_severity(findings: list[Dict[str, Any]]) -> str:
    if not findings:
        return "none"
    return max(
        (
            _normalized_text(item.get("severity")).lower() or "medium"
            for item in findings
        ),
        key=lambda item: _SEVERITY_RANK.get(item, 0),
    )


def _findings_metadata(findings: list[Dict[str, Any]]) -> Dict[str, Any]:
    severity_counts = {
        severity: 0 for severity in EXPERT_REVIEW_FINDING_SEVERITIES
    }
    category_counts = {
        category: 0 for category in EXPERT_REVIEW_FINDING_CATEGORIES
    }
    for finding in findings:
        severity = _normalized_text(finding.get("severity")).lower()
        category = _normalized_text(finding.get("category")).lower()
        if severity in severity_counts:
            severity_counts[severity] += 1
        if category in category_counts:
            category_counts[category] += 1
    return {
        "count": len(findings),
        "severity_counts": severity_counts,
        "category_counts": category_counts,
        "max_severity": _max_finding_severity(findings),
    }


def _reviewer_identity_payload(
    *,
    reviewer_provider: Any = "",
    reviewer_model: Any = "",
    reviewer_reasoning_strategy: Any = "",
    reviewer_reasoning_effort: Any = "",
    reviewer_reasoning_mode: Any = "",
    reviewer_capability_policy: Any = EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY,
    reviewer_capability_source: Any = EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE,
) -> Dict[str, Any]:
    return {
        "provider": _normalized_text(reviewer_provider),
        "model": _normalized_text(reviewer_model),
        "reasoning_strategy": _normalized_text(reviewer_reasoning_strategy),
        "reasoning_effort": _normalized_text(reviewer_reasoning_effort),
        "reasoning_mode": _normalized_text(reviewer_reasoning_mode),
        "capability_policy": _normalized_text(reviewer_capability_policy)
        or EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY,
        "capability_source": _normalized_text(reviewer_capability_source)
        or EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE,
    }


def expert_review_reviewer_identity(payload: Mapping[str, Any] | Any) -> Dict[str, Any]:
    root = dict(payload) if isinstance(payload, Mapping) else {}
    reviewer = root.get("reviewer")
    reviewer_mapping = dict(reviewer) if isinstance(reviewer, Mapping) else {}
    return _reviewer_identity_payload(
        reviewer_provider=(
            reviewer_mapping.get("provider")
            if reviewer_mapping.get("provider") not in (None, "")
            else root.get("reviewer_provider")
        ),
        reviewer_model=(
            reviewer_mapping.get("model")
            if reviewer_mapping.get("model") not in (None, "")
            else root.get("reviewer_model")
        ),
        reviewer_reasoning_strategy=(
            reviewer_mapping.get("reasoning_strategy")
            if reviewer_mapping.get("reasoning_strategy") not in (None, "")
            else root.get("reviewer_reasoning_strategy")
        ),
        reviewer_reasoning_effort=(
            reviewer_mapping.get("reasoning_effort")
            if reviewer_mapping.get("reasoning_effort") not in (None, "")
            else root.get("reviewer_reasoning_effort")
        ),
        reviewer_reasoning_mode=(
            reviewer_mapping.get("reasoning_mode")
            if reviewer_mapping.get("reasoning_mode") not in (None, "")
            else root.get("reviewer_reasoning_mode")
        ),
        reviewer_capability_policy=(
            reviewer_mapping.get("capability_policy")
            if reviewer_mapping.get("capability_policy") not in (None, "")
            else root.get("reviewer_capability_policy")
        ),
        reviewer_capability_source=(
            reviewer_mapping.get("capability_source")
            if reviewer_mapping.get("capability_source") not in (None, "")
            else root.get("reviewer_capability_source")
        ),
    )


def _verdict_metadata(
    *,
    verdict: str,
    confidence: str,
    findings: list[Dict[str, Any]],
    recommended_action: str,
) -> Dict[str, Any]:
    return {
        "advisory": True,
        "confidence": confidence,
        "finding_count": len(findings),
        "has_findings": bool(findings),
        "blocking_verdict": verdict == "block",
        "recommended_action": recommended_action,
    }


def expert_review_success_summary(summary: Any, *, finding_count: int) -> str:
    normalized_summary = _normalized_text(summary)
    if normalized_summary:
        return normalized_summary
    return (
        f"Expert review completed with {finding_count} "
        f"finding{'s' if finding_count != 1 else ''}."
    )


def expert_review_error_summary(summary: Any, *, error_code: str) -> str:
    return _normalized_text(summary) or _DEFAULT_ERROR_SUMMARY_BY_CODE[error_code]

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from cli.agent_cli.runtime_services.expert_review_parse_runtime_normalization_helpers_runtime import (
    _canonical_confidence_candidate,
    _canonical_verdict_candidate,
    _first_line_verdict_candidate,
    _parsed_text_findings,
)
from cli.agent_cli.runtime_services.expert_review_parse_runtime_pure_helpers_runtime import (
    _coerce_mapping,
    _first_present,
    _is_present,
    _text,
)


_PARSE_FAILURE_EMPTY = "reviewer_output_empty"
_PARSE_FAILURE_MISSING_VERDICT = "reviewer_output_missing_verdict"
_PARSE_FAILURE_UNUSABLE = "reviewer_output_unusable"

_CONTAINER_KEYS = (
    "structured_payload",
    "payload",
    "result",
    "review",
    "response",
    "data",
    "output",
)
_SUMMARY_KEYS = ("summary", "review_summary", "rationale", "analysis", "notes", "overview")
_VERDICT_KEYS = ("verdict", "review_verdict", "decision", "recommendation", "recommend")
_CONFIDENCE_KEYS = ("confidence", "confidence_level", "certainty")
_RECOMMENDED_ACTION_KEYS = ("recommended_action", "action", "next_action", "next_step")
_FINDINGS_KEYS = ("findings", "issues", "concerns", "observations", "risks")


def _best_review_mapping(root: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(root, Mapping):
        return {}
    candidates: list[Mapping[str, Any]] = [root]
    for key in _CONTAINER_KEYS:
        nested = root.get(key)
        if isinstance(nested, Mapping):
            candidates.append(nested)
    best_mapping = root
    best_score = _review_mapping_score(root)
    for candidate in candidates[1:]:
        score = _review_mapping_score(candidate)
        if score > best_score:
            best_mapping = candidate
            best_score = score
    return dict(best_mapping)


def _review_mapping_score(value: Mapping[str, Any]) -> int:
    score = 0
    for key in _VERDICT_KEYS:
        if _is_present(value.get(key)):
            score += 6
            break
    for key in _FINDINGS_KEYS:
        if _is_present(value.get(key)):
            score += 3
            break
    for key in _CONFIDENCE_KEYS:
        if _is_present(value.get(key)):
            score += 2
            break
    for key in _SUMMARY_KEYS + _RECOMMENDED_ACTION_KEYS:
        if _is_present(value.get(key)):
            score += 1
            break
    return score


def _structured_review_fields(
    review_mapping: Mapping[str, Any],
    *,
    root: Mapping[str, Any] | None,
) -> dict[str, Any]:
    root_mapping = dict(root) if isinstance(root, Mapping) else {}
    review_root = dict(review_mapping)
    reviewer_root = review_root.get("reviewer")
    if not isinstance(reviewer_root, Mapping):
        reviewer_root = {}
    root_reviewer = root_mapping.get("reviewer")
    if not isinstance(root_reviewer, Mapping):
        root_reviewer = {}
    return {
        "verdict": _canonical_verdict_candidate(
            _first_present(*[review_root.get(key) for key in _VERDICT_KEYS])
        ),
        "confidence": _canonical_confidence_candidate(
            _first_present(*[review_root.get(key) for key in _CONFIDENCE_KEYS])
        ),
        "summary": _first_present(
            *[review_root.get(key) for key in _SUMMARY_KEYS],
            *[root_mapping.get(key) for key in _SUMMARY_KEYS],
        ),
        "recommended_action": _first_present(
            *[review_root.get(key) for key in _RECOMMENDED_ACTION_KEYS]
        ),
        "findings": _first_present(*[review_root.get(key) for key in _FINDINGS_KEYS]),
        "reviewer_provider": _first_present(
            reviewer_root.get("provider"),
            root_reviewer.get("provider"),
            review_root.get("reviewer_provider"),
            root_mapping.get("reviewer_provider"),
        ),
        "reviewer_model": _first_present(
            reviewer_root.get("model"),
            root_reviewer.get("model"),
            review_root.get("reviewer_model"),
            root_mapping.get("reviewer_model"),
        ),
        "cross_provider": _first_present(
            review_root.get("cross_provider"),
            root_mapping.get("cross_provider"),
        ),
        "cross_vendor": _first_present(
            review_root.get("cross_vendor"),
            root_mapping.get("cross_vendor"),
        ),
        "scope": _first_present(
            review_root.get("scope"),
            root_mapping.get("scope"),
        ),
        "focus": _first_present(
            review_root.get("focus"),
            root_mapping.get("focus"),
        ),
        "strictness": _first_present(
            review_root.get("strictness"),
            root_mapping.get("strictness"),
        ),
        "review_elapsed_ms": _first_present(
            review_root.get("review_elapsed_ms"),
            root_mapping.get("review_elapsed_ms"),
        ),
    }


def _text_review_fields(text: str) -> dict[str, Any]:
    verdict_value, has_verdict = _labeled_field_value(
        text,
        labels=("verdict", "decision", "recommendation", "review verdict"),
    )
    if not has_verdict:
        verdict_value = _first_line_verdict_candidate(text)
    confidence_value, _ = _labeled_field_value(
        text,
        labels=("confidence", "certainty"),
    )
    summary_value, _ = _labeled_field_value(
        text,
        labels=("summary", "rationale", "analysis", "notes", "overview"),
    )
    recommended_action_value, _ = _labeled_field_value(
        text,
        labels=("recommended action", "action", "next action", "next step"),
    )
    return {
        "verdict": _canonical_verdict_candidate(verdict_value),
        "confidence": _canonical_confidence_candidate(confidence_value),
        "summary": _text(summary_value),
        "recommended_action": _text(recommended_action_value),
        "findings": _parsed_text_findings(text),
    }


def _labeled_field_value(text: str, *, labels: Sequence[str]) -> tuple[str, bool]:
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        for label in labels:
            label_pattern = re.escape(label).replace(r"\ ", r"\s+")
            pattern = rf"^{label_pattern}\s*(?:[:=-]|\bis\b)\s*(.+?)\s*$"
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                return match.group(1).strip(), True
    return "", False


def _parse_failure_detail(
    *,
    raw_output: Any,
    raw_text: str,
    structured_fields: Mapping[str, Any],
    text_fields: Mapping[str, Any],
) -> str:
    if not raw_text and not any(_is_present(value) for value in structured_fields.values()):
        if raw_output is None or raw_output == "":
            return _PARSE_FAILURE_EMPTY
        if _coerce_mapping(raw_output) is None:
            return _PARSE_FAILURE_UNUSABLE
    if raw_text or any(_is_present(value) for value in structured_fields.values()) or any(
        _is_present(value) for value in text_fields.values()
    ):
        return _PARSE_FAILURE_MISSING_VERDICT
    return _PARSE_FAILURE_UNUSABLE


__all__ = [
    "_CONFIDENCE_KEYS",
    "_CONTAINER_KEYS",
    "_FINDINGS_KEYS",
    "_PARSE_FAILURE_EMPTY",
    "_PARSE_FAILURE_MISSING_VERDICT",
    "_PARSE_FAILURE_UNUSABLE",
    "_RECOMMENDED_ACTION_KEYS",
    "_SUMMARY_KEYS",
    "_VERDICT_KEYS",
    "_best_review_mapping",
    "_labeled_field_value",
    "_parse_failure_detail",
    "_review_mapping_score",
    "_structured_review_fields",
    "_text_review_fields",
]

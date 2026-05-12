from __future__ import annotations

from typing import Any

from cli.agent_cli.runtime_services.expert_review_parse_runtime_helpers import (
    _DEFAULT_SCOPE,
    _DEFAULT_STRICTNESS,
    _best_review_mapping,
    _boolish,
    _coerce_mapping,
    _first_present,
    _jsonish_mapping,
    _normalized_text,
    _parse_failure_detail,
    _structured_review_fields,
    _text_from_value,
    _text_review_fields,
)
from cli.agent_cli.runtime_services.expert_review_result_runtime import (
    EXPERT_REVIEW_ERROR_PARSE_FAILED,
    build_expert_review_failure_result,
    build_expert_review_success_result,
)


def parse_expert_review_output(
    raw_output: Any,
    *,
    reviewer_provider: Any = "",
    reviewer_model: Any = "",
    reviewer_reasoning_strategy: Any = "",
    reviewer_reasoning_effort: Any = "",
    reviewer_reasoning_mode: Any = "",
    reviewer_capability_policy: Any = "",
    reviewer_capability_source: Any = "",
    cross_provider: bool | None = None,
    cross_vendor: bool | None = None,
    scope: Any = None,
    focus: Any = None,
    strictness: Any = None,
    review_elapsed_ms: Any = None,
) -> dict[str, Any]:
    root_mapping = _coerce_mapping(raw_output)
    raw_text = _text_from_value(raw_output)
    if root_mapping is None and raw_text:
        root_mapping = _jsonish_mapping(raw_text)

    review_mapping = _best_review_mapping(root_mapping)
    structured_fields = _structured_review_fields(review_mapping, root=root_mapping)
    text_fields = _text_review_fields(raw_text) if raw_text else {}

    verdict = _first_present(
        structured_fields.get("verdict"),
        text_fields.get("verdict"),
    )
    if not _normalized_text(verdict):
        failure_detail = _parse_failure_detail(
            raw_output=raw_output,
            raw_text=raw_text,
            structured_fields=structured_fields,
            text_fields=text_fields,
        )
        return build_expert_review_failure_result(
            error_code=EXPERT_REVIEW_ERROR_PARSE_FAILED,
            detail=failure_detail,
            reviewer_provider=_first_present(
                reviewer_provider,
                structured_fields.get("reviewer_provider"),
            ),
            reviewer_model=_first_present(
                reviewer_model,
                structured_fields.get("reviewer_model"),
            ),
            reviewer_reasoning_strategy=reviewer_reasoning_strategy,
            reviewer_reasoning_effort=reviewer_reasoning_effort,
            reviewer_reasoning_mode=reviewer_reasoning_mode,
            reviewer_capability_policy=reviewer_capability_policy,
            reviewer_capability_source=reviewer_capability_source,
            scope=_first_present(scope, structured_fields.get("scope"), _DEFAULT_SCOPE),
            focus=_first_present(focus, structured_fields.get("focus")),
            strictness=_first_present(
                strictness,
                structured_fields.get("strictness"),
                _DEFAULT_STRICTNESS,
            ),
            review_elapsed_ms=_first_present(
                review_elapsed_ms,
                structured_fields.get("review_elapsed_ms"),
            ),
        )

    return build_expert_review_success_result(
        verdict=verdict,
        confidence=_first_present(
            structured_fields.get("confidence"),
            text_fields.get("confidence"),
        ),
        findings=_first_present(
            structured_fields.get("findings"),
            text_fields.get("findings"),
            [],
        ),
        reviewer_provider=_first_present(
            reviewer_provider,
            structured_fields.get("reviewer_provider"),
        ),
        reviewer_model=_first_present(
            reviewer_model,
            structured_fields.get("reviewer_model"),
        ),
        reviewer_reasoning_strategy=reviewer_reasoning_strategy,
        reviewer_reasoning_effort=reviewer_reasoning_effort,
        reviewer_reasoning_mode=reviewer_reasoning_mode,
        reviewer_capability_policy=reviewer_capability_policy,
        reviewer_capability_source=reviewer_capability_source,
        cross_provider=_boolish(
            _first_present(
                cross_provider,
                structured_fields.get("cross_provider"),
                True,
            ),
            default=True,
        ),
        cross_vendor=_boolish(
            _first_present(
                cross_vendor,
                structured_fields.get("cross_vendor"),
                False,
            ),
            default=False,
        ),
        scope=_first_present(scope, structured_fields.get("scope"), _DEFAULT_SCOPE),
        focus=_first_present(focus, structured_fields.get("focus")),
        strictness=_first_present(
            strictness,
            structured_fields.get("strictness"),
            _DEFAULT_STRICTNESS,
        ),
        recommended_action=_first_present(
            structured_fields.get("recommended_action"),
            text_fields.get("recommended_action"),
        ),
        review_elapsed_ms=_first_present(
            review_elapsed_ms,
            structured_fields.get("review_elapsed_ms"),
        ),
        summary=_first_present(
            structured_fields.get("summary"),
            text_fields.get("summary"),
        ),
    )


__all__ = ["parse_expert_review_output"]

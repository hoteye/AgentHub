from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable


def selection_failure_error_code(
    selection: Mapping[str, Any],
    *,
    normalized_text_fn: Callable[[Any], str],
    no_eligible_provider_error: str,
    no_reviewer_candidate_error: str,
    unavailable_error: str,
) -> str:
    reason = normalized_text_fn(selection.get("selection_reason")).lower()
    if reason == "insufficient_eligible_providers":
        return no_eligible_provider_error
    if reason in {
        "no_reviewer_candidate",
        "no_cross_vendor_candidate",
        "no_preferred_reviewer_candidate",
    }:
        return no_reviewer_candidate_error
    return unavailable_error


def selection_failure_detail(
    selection: Mapping[str, Any],
    *,
    normalized_text_fn: Callable[[Any], str],
    unavailable_error: str,
) -> str:
    reason = normalized_text_fn(selection.get("selection_reason")) or unavailable_error
    gate_payload = dict(selection.get("gate") or {})
    unavailable_reason = normalized_text_fn(gate_payload.get("expert_review_unavailable_reason"))
    if unavailable_reason and unavailable_reason != "-":
        return unavailable_reason
    return reason


def candidate_provider_selector(
    candidate: Mapping[str, Any],
    *,
    normalized_text_fn: Callable[[Any], str],
) -> str | None:
    selector = normalized_text_fn(candidate.get("config_provider_name")) or normalized_text_fn(
        candidate.get("provider_name")
    )
    return selector or None


def candidate_model_selector(
    candidate: Mapping[str, Any],
    *,
    normalized_text_fn: Callable[[Any], str],
) -> str | None:
    selector = normalized_text_fn(candidate.get("default_model")) or normalized_text_fn(
        candidate.get("provider_default_model_id")
    )
    return selector or None


def candidate_provider_display(
    candidate: Mapping[str, Any],
    *,
    normalized_text_fn: Callable[[Any], str],
) -> str:
    return normalized_text_fn(candidate.get("provider_name")) or normalized_text_fn(
        candidate.get("config_provider_name")
    )


def candidate_model_display(
    candidate: Mapping[str, Any],
    *,
    normalized_text_fn: Callable[[Any], str],
) -> str:
    return normalized_text_fn(candidate.get("provider_default_model_id")) or normalized_text_fn(
        candidate.get("default_model")
    )


def candidate_reviewer_reasoning_strategy(
    candidate: Mapping[str, Any],
    *,
    normalized_text_fn: Callable[[Any], str],
) -> str:
    return normalized_text_fn(candidate.get("reviewer_reasoning_strategy"))


def candidate_reviewer_reasoning_effort(
    candidate: Mapping[str, Any],
    *,
    normalized_text_fn: Callable[[Any], str],
) -> str | None:
    effort = normalized_text_fn(candidate.get("reviewer_reasoning_effort"))
    return effort or None


def candidate_reviewer_reasoning_mode(
    candidate: Mapping[str, Any],
    *,
    normalized_text_fn: Callable[[Any], str],
) -> str:
    return normalized_text_fn(candidate.get("reviewer_reasoning_mode"))


def candidate_reviewer_capability_policy(
    candidate: Mapping[str, Any],
    *,
    normalized_text_fn: Callable[[Any], str],
) -> str:
    return normalized_text_fn(candidate.get("reviewer_capability_policy"))


def candidate_reviewer_capability_source(
    candidate: Mapping[str, Any],
    *,
    normalized_text_fn: Callable[[Any], str],
) -> str:
    return normalized_text_fn(
        candidate.get("reviewer_capability_source")
        or candidate.get("reviewer_capability_policy_source")
    )


def resolved_reviewer_provider(
    candidate: Mapping[str, Any],
    resolution: Any,
    *,
    candidate_provider_display_fn: Callable[[Mapping[str, Any]], str],
    normalized_text_fn: Callable[[Any], str],
) -> str:
    config = getattr(resolution, "config", None)
    return candidate_provider_display_fn(candidate) or normalized_text_fn(
        getattr(config, "provider_name", "")
    )


def resolved_reviewer_model(
    candidate: Mapping[str, Any],
    resolution: Any,
    *,
    candidate_model_display_fn: Callable[[Mapping[str, Any]], str],
    normalized_text_fn: Callable[[Any], str],
) -> str:
    config = getattr(resolution, "config", None)
    return normalized_text_fn(getattr(config, "model", "")) or candidate_model_display_fn(candidate)


def reviewer_task_text(
    prompt_bundle: Mapping[str, Any],
    *,
    normalized_text_fn: Callable[[Any], str],
) -> str:
    system_prompt = normalized_text_fn(prompt_bundle.get("system_prompt"))
    user_prompt = normalized_text_fn(prompt_bundle.get("user_prompt"))
    parts = [
        "Follow the reviewer instructions exactly and return only the requested JSON object.",
    ]
    if system_prompt:
        parts.extend(["[Reviewer System Prompt]", system_prompt])
    if user_prompt:
        parts.extend(["[Reviewer Task]", user_prompt])
    return "\n\n".join(part for part in parts if part)


__all__ = [
    "candidate_model_display",
    "candidate_model_selector",
    "candidate_provider_display",
    "candidate_provider_selector",
    "candidate_reviewer_capability_policy",
    "candidate_reviewer_capability_source",
    "candidate_reviewer_reasoning_effort",
    "candidate_reviewer_reasoning_mode",
    "candidate_reviewer_reasoning_strategy",
    "resolved_reviewer_model",
    "resolved_reviewer_provider",
    "reviewer_task_text",
    "selection_failure_detail",
    "selection_failure_error_code",
]

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from cli.agent_cli.runtime_services.expert_review_prompt_normalization_helpers_runtime import (
    dedupe_strings,
    json_safe,
    mapping_dict,
    normalized_choice,
    normalized_max_findings,
    normalized_scope,
    normalized_string_list,
    normalized_text,
    normalized_text_list,
)


_DEFAULT_SCOPE = "current_task"
_DEFAULT_STRICTNESS = "medium"
_DEFAULT_MAX_FINDINGS = 5
_DEFAULT_TASK = "Review the provided mainline candidate for material issues."
_DEFAULT_POLICY_CONSTRAINTS = (
    "advisory_only",
    "read_only_review",
    "no_raw_reasoning_requests",
)
_SENSITIVE_PACKET_KEYS = {
    "chain_of_thought",
    "commentary",
    "commentary_text",
    "cot",
    "encrypted_content",
    "private_reasoning",
    "raw_reasoning",
    "reasoning",
    "reasoning_content",
    "reasoning_text",
    "reasoning_trace",
    "reasoning_traces",
}
_DROP = object()


def build_reviewer_prompt_context(
    packet: Mapping[str, Any] | Any,
    *,
    policy: Mapping[str, Any],
    focus_areas: Sequence[str],
    strictness_levels: Sequence[str],
) -> dict[str, Any]:
    raw_packet = mapping_dict(packet)
    sanitized_packet, sanitized_fields = sanitize_for_prompt(raw_packet)
    reviewer_packet = mapping_dict(sanitized_packet if sanitized_packet is not _DROP else {})

    review_request = mapping_dict(reviewer_packet.get("review_request"))
    observable_context = mapping_dict(reviewer_packet.get("observable_context"))
    omissions = mapping_dict(reviewer_packet.get("omissions"))

    scope, scope_source = _resolve_scope(review_request=review_request, policy=policy)
    strictness, strictness_source = _resolve_strictness(
        review_request=review_request,
        policy=policy,
        strictness_levels=strictness_levels,
    )
    max_findings, max_findings_source = _resolve_max_findings(
        review_request=review_request,
        policy=policy,
    )
    focus, focus_source = _resolve_focus(
        review_request=review_request,
        policy=policy,
        focus_areas=focus_areas,
    )
    task = normalized_text(review_request.get("task")) or _DEFAULT_TASK
    artifact_paths = normalized_string_list(review_request.get("artifact_paths"))
    if not artifact_paths:
        artifact_paths = normalized_string_list(
            mapping_dict(observable_context.get("artifacts")).get("requested_paths")
        )

    reviewer_packet["review_request"] = {
        "task": task,
        "scope": scope,
        "focus": list(focus),
        "artifact_paths": list(artifact_paths),
        "max_findings": max_findings,
        "strictness": strictness,
    }
    reviewer_packet = dict(json_safe(reviewer_packet))

    runtime_policy_constraints = normalized_string_list(
        mapping_dict(observable_context.get("runtime_constraints")).get("policy_constraints"),
        limit=16,
    )
    policy_constraints = dedupe_strings(
        [
            *_DEFAULT_POLICY_CONSTRAINTS,
            *normalized_string_list(policy.get("policy_constraints"), limit=16),
            *runtime_policy_constraints,
        ],
        limit=16,
    )
    additional_instructions = normalized_text_list(
        policy.get("additional_instructions"),
        limit=8,
    )

    return {
        "reviewer_packet": reviewer_packet,
        "packet_version": normalized_text(reviewer_packet.get("packet_version")),
        "task": task,
        "scope": scope,
        "scope_source": scope_source,
        "focus": list(focus),
        "focus_source": focus_source,
        "artifact_paths": list(artifact_paths),
        "max_findings": max_findings,
        "max_findings_source": max_findings_source,
        "strictness": strictness,
        "strictness_source": strictness_source,
        "policy_constraints": list(policy_constraints),
        "additional_instructions": list(additional_instructions),
        "user_goal_summary": normalized_text(observable_context.get("user_goal_summary")),
        "candidate_summary": normalized_text(observable_context.get("candidate_summary")),
        "excluded_sources": normalized_string_list(omissions.get("excluded_sources"), limit=24),
        "reasoning_traces_excluded": bool(omissions.get("reasoning_traces_excluded")),
        "sanitized_fields": list(sanitized_fields),
    }


def sanitize_for_prompt(
    value: Any,
    *,
    path: tuple[str, ...] = (),
) -> tuple[Any, list[str]]:
    if isinstance(value, Mapping):
        item_type = normalized_text(value.get("type")).lower()
        if item_type == "reasoning":
            return _DROP, [_path_text(path)]

        sanitized: dict[str, Any] = {}
        removed_paths: list[str] = []
        for key in sorted(value.keys(), key=lambda item: str(item)):
            normalized_key = str(key)
            nested_value = value[key]
            if _is_sensitive_packet_key(normalized_key):
                if nested_value not in (None, "", [], {}, ()):
                    removed_paths.append(_path_text(path + (normalized_key,)))
                continue
            sanitized_value, nested_removed = sanitize_for_prompt(
                nested_value,
                path=path + (normalized_key,),
            )
            removed_paths.extend(nested_removed)
            if sanitized_value is _DROP:
                continue
            sanitized[normalized_key] = sanitized_value
        if not sanitized and path:
            return _DROP, removed_paths
        return sanitized, removed_paths

    if isinstance(value, (list, tuple)):
        sanitized_items: list[Any] = []
        removed_paths: list[str] = []
        for index, item in enumerate(value):
            sanitized_item, nested_removed = sanitize_for_prompt(
                item,
                path=path + (str(index),),
            )
            removed_paths.extend(nested_removed)
            if sanitized_item is _DROP:
                continue
            sanitized_items.append(sanitized_item)
        return sanitized_items, removed_paths

    if isinstance(value, (set, frozenset)):
        sanitized_items: list[Any] = []
        removed_paths: list[str] = []
        for index, item in enumerate(sorted(list(value), key=lambda candidate: str(candidate))):
            sanitized_item, nested_removed = sanitize_for_prompt(
                item,
                path=path + (str(index),),
            )
            removed_paths.extend(nested_removed)
            if sanitized_item is _DROP:
                continue
            sanitized_items.append(sanitized_item)
        return sanitized_items, removed_paths

    return json_safe(value), []


def _is_sensitive_packet_key(value: Any) -> bool:
    return normalized_text(value).strip().lower() in _SENSITIVE_PACKET_KEYS


def _path_text(path: tuple[str, ...]) -> str:
    return ".".join(path) if path else "<root>"


def _resolve_scope(
    *,
    review_request: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> tuple[str, str]:
    request_scope = normalized_scope(review_request.get("scope"))
    if request_scope is not None:
        return request_scope, "review_request"
    policy_scope = normalized_scope(policy.get("default_scope"))
    if policy_scope is not None:
        return policy_scope, "policy_default"
    return _DEFAULT_SCOPE, "default"


def _resolve_strictness(
    *,
    review_request: Mapping[str, Any],
    policy: Mapping[str, Any],
    strictness_levels: Sequence[str],
) -> tuple[str, str]:
    request_strictness = normalized_choice(
        review_request.get("strictness"),
        allowed=strictness_levels,
    )
    if request_strictness is not None:
        return request_strictness, "review_request"
    policy_strictness = normalized_choice(
        policy.get("default_strictness"),
        allowed=strictness_levels,
    )
    if policy_strictness is not None:
        return policy_strictness, "policy_default"
    return _DEFAULT_STRICTNESS, "default"


def _resolve_max_findings(
    *,
    review_request: Mapping[str, Any],
    policy: Mapping[str, Any],
) -> tuple[int, str]:
    request_max_findings = normalized_max_findings(review_request.get("max_findings"))
    if request_max_findings is not None:
        return request_max_findings, "review_request"
    policy_max_findings = normalized_max_findings(policy.get("default_max_findings"))
    if policy_max_findings is not None:
        return policy_max_findings, "policy_default"
    return _DEFAULT_MAX_FINDINGS, "default"


def _resolve_focus(
    *,
    review_request: Mapping[str, Any],
    policy: Mapping[str, Any],
    focus_areas: Sequence[str],
) -> tuple[list[str], str]:
    request_focus = normalized_string_list(
        review_request.get("focus"),
        allowed=focus_areas,
        limit=len(focus_areas),
    )
    if request_focus:
        return request_focus, "review_request"
    policy_focus = normalized_string_list(
        policy.get("default_focus"),
        allowed=focus_areas,
        limit=len(focus_areas),
    )
    if policy_focus:
        return policy_focus, "policy_default"
    return list(focus_areas), "default_all"


__all__ = [
    "build_reviewer_prompt_context",
    "sanitize_for_prompt",
]

from __future__ import annotations

from typing import Any, Callable, Dict, Mapping

from cli.agent_cli.runtime_services import expert_review_selector_pure_helpers_runtime
from cli.agent_cli.runtime_services.expert_review_reviewer_capability_runtime import (
    EXPERT_REVIEW_REASONING_CAPABILITY_VALIDATION,
    EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY,
    EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE,
    expert_review_reviewer_policy_metadata,
)


def selection_metadata(
    *,
    reviewer_capability_policy: str,
    reviewer_capability_policy_source: str,
    reasoning_capability_validation: str,
) -> Dict[str, Any]:
    return {
        **expert_review_reviewer_policy_metadata(),
        "reviewer_capability_policy": reviewer_capability_policy,
        "reviewer_capability_policy_source": reviewer_capability_policy_source,
        "reasoning_capability_validation": reasoning_capability_validation,
    }


def normalized_selector_settings(
    *,
    review_gate: Mapping[str, Any] | None,
    prefer_cross_vendor: bool | None,
    allow_same_vendor_fallback: bool | None,
    reviewer_capability_policy: Any,
    reviewer_capability_policy_source: Any,
    reasoning_capability_validation: Any,
) -> Dict[str, Any]:
    gate_root = dict(review_gate or {})
    nested_gate = gate_root.get("expert_review_gate")
    gate_payload = dict(nested_gate) if isinstance(nested_gate, Mapping) else {}

    normalized_prefer_cross_vendor = expert_review_selector_pure_helpers_runtime.boolish(
        expert_review_selector_pure_helpers_runtime.first_present(
            prefer_cross_vendor,
            gate_root.get("expert_review_prefer_cross_vendor"),
            gate_payload.get("prefer_cross_vendor"),
            default=True,
        ),
        default=True,
    )
    normalized_allow_same_vendor_fallback = expert_review_selector_pure_helpers_runtime.boolish(
        expert_review_selector_pure_helpers_runtime.first_present(
            allow_same_vendor_fallback,
            gate_root.get("expert_review_allow_same_vendor_fallback"),
            gate_payload.get("allow_same_vendor_fallback"),
            default=True,
        ),
        default=True,
    )
    normalized_reviewer_capability_policy = (
        str(
            expert_review_selector_pure_helpers_runtime.first_present(
                reviewer_capability_policy,
                gate_root.get("expert_review_reviewer_capability_policy"),
                gate_payload.get("reviewer_capability_policy"),
                default=EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY,
            )
            or EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY
        ).strip()
        or EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY
    )
    normalized_reviewer_capability_policy_source = (
        str(
            expert_review_selector_pure_helpers_runtime.first_present(
                reviewer_capability_policy_source,
                gate_root.get("expert_review_reviewer_capability_policy_source"),
                gate_payload.get("reviewer_capability_policy_source"),
                default=EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE,
            )
            or EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE
        ).strip()
        or EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE
    )
    normalized_reasoning_capability_validation = (
        str(
            expert_review_selector_pure_helpers_runtime.first_present(
                reasoning_capability_validation,
                gate_root.get("expert_review_reasoning_capability_validation"),
                gate_payload.get("reasoning_capability_validation"),
                default=EXPERT_REVIEW_REASONING_CAPABILITY_VALIDATION,
            )
            or EXPERT_REVIEW_REASONING_CAPABILITY_VALIDATION
        )
        .strip()
        .lower()
        or EXPERT_REVIEW_REASONING_CAPABILITY_VALIDATION
    )

    return {
        "gate_root": gate_root,
        "gate_payload": gate_payload,
        "prefer_cross_vendor": normalized_prefer_cross_vendor,
        "allow_same_vendor_fallback": normalized_allow_same_vendor_fallback,
        "selection_metadata": selection_metadata(
            reviewer_capability_policy=normalized_reviewer_capability_policy,
            reviewer_capability_policy_source=normalized_reviewer_capability_policy_source,
            reasoning_capability_validation=normalized_reasoning_capability_validation,
        ),
    }


def active_provider_context(
    *,
    active_provider_name: Any,
    active_provider_public_name: Any,
    gate_root: Mapping[str, Any],
    gate_payload: Mapping[str, Any],
    vendor_for_name_fn: Callable[[str], Any] | None,
) -> Dict[str, Any]:
    active_config_name = str(active_provider_name or "").strip()
    active_public_name = str(
        active_provider_public_name
        or gate_root.get("primary_provider_name")
        or gate_payload.get("primary_provider_name")
        or active_provider_name
        or ""
    ).strip()
    active_config_key = expert_review_selector_pure_helpers_runtime.normalized_provider_key(
        active_config_name
    )
    active_public_key = expert_review_selector_pure_helpers_runtime.normalized_provider_key(
        active_public_name
    )
    primary_provider_resolved = bool(active_config_key or active_public_key)

    active_vendor_name = expert_review_selector_pure_helpers_runtime.resolved_vendor_name(
        (active_public_name, active_config_name),
        vendor_for_name_fn=vendor_for_name_fn,
    )
    if not active_vendor_name:
        active_vendor_name = str(
            gate_root.get("primary_provider_vendor") or gate_payload.get("primary_vendor_name") or ""
        ).strip().lower()

    return {
        "active_config_name": active_config_name,
        "active_public_name": active_public_name,
        "active_config_key": active_config_key,
        "active_public_key": active_public_key,
        "primary_provider_resolved": primary_provider_resolved,
        "active_vendor_name": active_vendor_name,
    }


def gate_decision(
    *,
    gate_root: Mapping[str, Any],
    gate_payload: Mapping[str, Any],
    primary_provider_resolved: bool,
    reviewer_candidate_count: int,
    cross_vendor_candidate_count: int,
    preferred_candidate_count: int,
    prefer_cross_vendor: bool,
    allow_same_vendor_fallback: bool,
) -> Dict[str, Any]:
    gate_available = True
    gate_unavailable_reason = "-"
    if gate_root:
        gate_available = expert_review_selector_pure_helpers_runtime.boolish(
            expert_review_selector_pure_helpers_runtime.first_present(
                gate_root.get("expert_review_available"),
                gate_payload.get("available"),
                default=True,
            ),
            default=True,
        )
        gate_unavailable_reason = (
            str(
                expert_review_selector_pure_helpers_runtime.first_present(
                    gate_root.get("expert_review_unavailable_reason"),
                    gate_payload.get("unavailable_reason"),
                    default="-",
                )
                or "-"
            ).strip()
            or "-"
        )

    unavailable_reason = ""
    if not gate_available:
        unavailable_reason = (
            gate_unavailable_reason
            if gate_unavailable_reason != "-"
            else "expert_review_unavailable"
        )
    elif not primary_provider_resolved:
        unavailable_reason = "primary_provider_unknown"
    elif reviewer_candidate_count == 0:
        unavailable_reason = "no_reviewer_candidate"
    elif prefer_cross_vendor and not allow_same_vendor_fallback and cross_vendor_candidate_count == 0:
        unavailable_reason = "no_cross_vendor_candidate"
    elif preferred_candidate_count == 0:
        unavailable_reason = "no_preferred_reviewer_candidate"

    return {
        "gate_available": gate_available,
        "gate_unavailable_reason": gate_unavailable_reason,
        "unavailable_reason": unavailable_reason,
    }


def selection_outcome(
    *,
    preferred_candidates: list[Dict[str, Any]],
    unavailable_reason: str,
    prefer_cross_vendor: bool,
) -> Dict[str, Any]:
    selected_candidate = dict(preferred_candidates[0]) if preferred_candidates and not unavailable_reason else None
    same_vendor_fallback_used = bool(
        selected_candidate is not None
        and prefer_cross_vendor
        and str(selected_candidate.get("vendor_match") or "") == "same_vendor"
    )
    if same_vendor_fallback_used:
        selection_reason = "same_vendor_fallback"
    elif selected_candidate is not None:
        selection_reason = str(selected_candidate.get("selection_bucket") or "selected")
    else:
        selection_reason = unavailable_reason or "no_reviewer_candidate"
    return {
        "selected_candidate": selected_candidate,
        "same_vendor_fallback_used": same_vendor_fallback_used,
        "selection_reason": selection_reason,
    }


def build_selection_result(
    *,
    selected_candidate: Dict[str, Any] | None,
    ordered_candidates: list[Dict[str, Any]],
    preferred_candidates: list[Dict[str, Any]],
    selection_reason: str,
    same_vendor_fallback_used: bool,
    prefer_cross_vendor: bool,
    allow_same_vendor_fallback: bool,
    selection_metadata_payload: Mapping[str, Any],
    gate_available: bool,
    gate_unavailable_reason: str,
    active_public_name: str,
    active_config_name: str,
    active_vendor_name: str,
    primary_provider_resolved: bool,
    counts: Mapping[str, Any],
) -> Dict[str, Any]:
    return {
        "selected": selected_candidate is not None,
        "selection_state": "selected" if selected_candidate is not None else "unavailable",
        "selection_reason": selection_reason,
        "selected_candidate": selected_candidate,
        "ordered_candidates": ordered_candidates,
        "preferred_candidates": preferred_candidates,
        "policy": {
            "prefer_cross_vendor": prefer_cross_vendor,
            "allow_same_vendor_fallback": allow_same_vendor_fallback,
            **selection_metadata_payload,
        },
        "gate": {
            "expert_review_available": gate_available,
            "expert_review_unavailable_reason": gate_unavailable_reason,
            "primary_provider_name": active_public_name or active_config_name or "-",
            "primary_provider_config_name": active_config_name or "-",
            "primary_provider_vendor": active_vendor_name or "-",
            "primary_provider_resolved": primary_provider_resolved,
        },
        "counts": {
            "eligible_provider_count": int(counts.get("eligible_provider_count") or 0),
            "reviewer_candidate_count": int(counts.get("reviewer_candidate_count") or 0),
            "reviewer_ineligible_candidate_count": int(
                counts.get("reviewer_ineligible_candidate_count") or 0
            ),
            "ordered_candidate_count": int(counts.get("ordered_candidate_count") or 0),
            "preferred_candidate_count": int(counts.get("preferred_candidate_count") or 0),
            "cross_vendor_candidate_count": int(counts.get("cross_vendor_candidate_count") or 0),
            "same_vendor_candidate_count": int(counts.get("same_vendor_candidate_count") or 0),
            "unknown_vendor_candidate_count": int(counts.get("unknown_vendor_candidate_count") or 0),
            "available_candidate_count": int(counts.get("available_candidate_count") or 0),
            "unknown_status_candidate_count": int(counts.get("unknown_status_candidate_count") or 0),
        },
        "same_vendor_fallback_used": same_vendor_fallback_used,
    }

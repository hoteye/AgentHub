from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Mapping

from cli.agent_cli.providers.registry import vendor_for_name as _default_vendor_for_name
from cli.agent_cli.runtime_services import expert_review_selector_projection_helpers_runtime
from cli.agent_cli.runtime_services import expert_review_selector_ranking_helpers_runtime


def select_expert_review_reviewer(
    provider_items: Iterable[Mapping[str, Any]],
    *,
    review_gate: Mapping[str, Any] | None = None,
    active_provider_name: Any = "",
    active_provider_public_name: Any = "",
    prefer_cross_vendor: bool | None = None,
    allow_same_vendor_fallback: bool | None = None,
    reviewer_capability_policy: Any = None,
    reviewer_capability_policy_source: Any = None,
    reasoning_capability_validation: Any = None,
    vendor_for_name_fn: Callable[[str], Any] | None = _default_vendor_for_name,
) -> Dict[str, Any]:
    selector_settings = expert_review_selector_projection_helpers_runtime.normalized_selector_settings(
        review_gate=review_gate,
        prefer_cross_vendor=prefer_cross_vendor,
        allow_same_vendor_fallback=allow_same_vendor_fallback,
        reviewer_capability_policy=reviewer_capability_policy,
        reviewer_capability_policy_source=reviewer_capability_policy_source,
        reasoning_capability_validation=reasoning_capability_validation,
    )
    gate_root = dict(selector_settings["gate_root"])
    gate_payload = dict(selector_settings["gate_payload"])
    normalized_prefer_cross_vendor = bool(selector_settings["prefer_cross_vendor"])
    normalized_allow_same_vendor_fallback = bool(
        selector_settings["allow_same_vendor_fallback"]
    )
    selection_metadata = dict(selector_settings["selection_metadata"])

    active_provider = expert_review_selector_projection_helpers_runtime.active_provider_context(
        active_provider_name=active_provider_name,
        active_provider_public_name=active_provider_public_name,
        gate_root=gate_root,
        gate_payload=gate_payload,
        vendor_for_name_fn=vendor_for_name_fn,
    )
    candidate_inventory = expert_review_selector_ranking_helpers_runtime.reviewer_candidate_inventory(
        provider_items,
        active_config_key=str(active_provider["active_config_key"]),
        active_public_key=str(active_provider["active_public_key"]),
    )
    ranking_projection = expert_review_selector_ranking_helpers_runtime.rank_reviewer_candidates(
        candidate_inventory["reviewer_candidates"],
        active_vendor_name=str(active_provider["active_vendor_name"]),
        prefer_cross_vendor=normalized_prefer_cross_vendor,
        allow_same_vendor_fallback=normalized_allow_same_vendor_fallback,
        selection_metadata=selection_metadata,
        vendor_for_name_fn=vendor_for_name_fn,
    )
    gate_decision = expert_review_selector_projection_helpers_runtime.gate_decision(
        gate_root=gate_root,
        gate_payload=gate_payload,
        primary_provider_resolved=bool(active_provider["primary_provider_resolved"]),
        reviewer_candidate_count=len(candidate_inventory["reviewer_candidates"]),
        cross_vendor_candidate_count=int(ranking_projection["cross_vendor_candidate_count"]),
        preferred_candidate_count=len(ranking_projection["preferred_candidates"]),
        prefer_cross_vendor=normalized_prefer_cross_vendor,
        allow_same_vendor_fallback=normalized_allow_same_vendor_fallback,
    )
    selection_outcome = expert_review_selector_projection_helpers_runtime.selection_outcome(
        preferred_candidates=ranking_projection["preferred_candidates"],
        unavailable_reason=str(gate_decision["unavailable_reason"]),
        prefer_cross_vendor=normalized_prefer_cross_vendor,
    )
    counts = {
        "eligible_provider_count": len(candidate_inventory["eligible_items"]),
        "reviewer_candidate_count": len(candidate_inventory["reviewer_candidates"]),
        "reviewer_ineligible_candidate_count": int(
            candidate_inventory["reviewer_ineligible_candidate_count"]
        ),
        "ordered_candidate_count": len(ranking_projection["ordered_candidates"]),
        "preferred_candidate_count": len(ranking_projection["preferred_candidates"]),
        "cross_vendor_candidate_count": int(ranking_projection["cross_vendor_candidate_count"]),
        "same_vendor_candidate_count": int(ranking_projection["same_vendor_candidate_count"]),
        "unknown_vendor_candidate_count": int(ranking_projection["unknown_vendor_candidate_count"]),
        "available_candidate_count": int(ranking_projection["available_candidate_count"]),
        "unknown_status_candidate_count": int(ranking_projection["unknown_status_candidate_count"]),
    }
    return expert_review_selector_projection_helpers_runtime.build_selection_result(
        selected_candidate=selection_outcome["selected_candidate"],
        ordered_candidates=ranking_projection["ordered_candidates"],
        preferred_candidates=ranking_projection["preferred_candidates"],
        selection_reason=str(selection_outcome["selection_reason"]),
        same_vendor_fallback_used=bool(selection_outcome["same_vendor_fallback_used"]),
        prefer_cross_vendor=normalized_prefer_cross_vendor,
        allow_same_vendor_fallback=normalized_allow_same_vendor_fallback,
        selection_metadata_payload=selection_metadata,
        gate_available=bool(gate_decision["gate_available"]),
        gate_unavailable_reason=str(gate_decision["gate_unavailable_reason"]),
        active_public_name=str(active_provider["active_public_name"]),
        active_config_name=str(active_provider["active_config_name"]),
        active_vendor_name=str(active_provider["active_vendor_name"]),
        primary_provider_resolved=bool(active_provider["primary_provider_resolved"]),
        counts=counts,
    )


__all__ = ["select_expert_review_reviewer"]

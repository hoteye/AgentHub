from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Mapping

from cli.agent_cli.runtime_services import expert_review_selector_pure_helpers_runtime
from cli.agent_cli.runtime_services.expert_review_reviewer_capability_runtime import (
    resolve_expert_review_reviewer_capability,
)


def availability_bucket(item: Mapping[str, Any]) -> tuple[str, int]:
    availability_status = expert_review_selector_pure_helpers_runtime.normalized_text(
        item.get("availability_status")
    )
    provider_state = expert_review_selector_pure_helpers_runtime.normalized_text(
        item.get("provider_status_state")
    )
    if availability_status == "available" or provider_state == "ready":
        return "available", 0
    return "unknown", 1


def selection_bucket(
    *,
    vendor_match: str,
    availability_bucket: str,
    prefer_cross_vendor: bool,
) -> tuple[str, int]:
    if prefer_cross_vendor:
        if vendor_match == "cross_vendor":
            return (
                f"cross_vendor_{availability_bucket}",
                0 if availability_bucket == "available" else 1,
            )
        if vendor_match == "same_vendor":
            return (
                f"same_vendor_{availability_bucket}",
                2 if availability_bucket == "available" else 3,
            )
        return (
            f"unknown_vendor_{availability_bucket}",
            4 if availability_bucket == "available" else 5,
        )
    if availability_bucket == "available":
        if vendor_match == "cross_vendor":
            return "cross_vendor_available", 0
        if vendor_match == "same_vendor":
            return "same_vendor_available", 1
        return "unknown_vendor_available", 2
    if vendor_match == "cross_vendor":
        return "cross_vendor_unknown", 3
    if vendor_match == "same_vendor":
        return "same_vendor_unknown", 4
    return "unknown_vendor_unknown", 5


def reviewer_candidate_inventory(
    provider_items: Iterable[Mapping[str, Any]],
    *,
    active_config_key: str,
    active_public_key: str,
) -> Dict[str, Any]:
    deduped_items = expert_review_selector_pure_helpers_runtime.deduped_provider_items(provider_items)
    eligible_items = [
        item
        for item in deduped_items
        if expert_review_selector_pure_helpers_runtime.available_reviewer_candidate(item)
    ]
    reviewer_candidates: list[Dict[str, Any]] = []
    reviewer_ineligible_candidate_count = 0
    for item in eligible_items:
        if (
            (active_config_key and active_config_key == str(item.get("_config_provider_key") or ""))
            or (active_public_key and active_public_key == str(item.get("_provider_key") or ""))
        ):
            continue
        capability = resolve_expert_review_reviewer_capability(item)
        if not bool(capability.get("reviewer_eligible")):
            reviewer_ineligible_candidate_count += 1
            continue
        candidate = dict(item)
        candidate.update(capability)
        reviewer_candidates.append(candidate)
    return {
        "eligible_items": eligible_items,
        "reviewer_candidates": reviewer_candidates,
        "reviewer_ineligible_candidate_count": reviewer_ineligible_candidate_count,
    }


def rank_reviewer_candidates(
    reviewer_candidates: Iterable[Mapping[str, Any]],
    *,
    active_vendor_name: str,
    prefer_cross_vendor: bool,
    allow_same_vendor_fallback: bool,
    selection_metadata: Mapping[str, Any],
    vendor_for_name_fn: Callable[[str], Any] | None,
) -> Dict[str, Any]:
    ordered_candidates: list[Dict[str, Any]] = []
    cross_vendor_candidate_count = 0
    same_vendor_candidate_count = 0
    unknown_vendor_candidate_count = 0
    available_candidate_count = 0
    unknown_status_candidate_count = 0

    for index, item in enumerate(reviewer_candidates):
        candidate = dict(item)
        vendor_name = expert_review_selector_pure_helpers_runtime.resolved_vendor_name(
            (
                candidate.get("provider_name"),
                candidate.get("config_provider_name"),
            ),
            vendor_for_name_fn=vendor_for_name_fn,
        )
        if active_vendor_name and vendor_name:
            vendor_match = "same_vendor" if vendor_name == active_vendor_name else "cross_vendor"
        else:
            vendor_match = "unknown_vendor"

        if vendor_match == "cross_vendor":
            cross_vendor_candidate_count += 1
        elif vendor_match == "same_vendor":
            same_vendor_candidate_count += 1
        else:
            unknown_vendor_candidate_count += 1

        candidate_availability_bucket, _ = availability_bucket(candidate)
        if candidate_availability_bucket == "available":
            available_candidate_count += 1
        else:
            unknown_status_candidate_count += 1

        candidate_selection_bucket, selection_rank = selection_bucket(
            vendor_match=vendor_match,
            availability_bucket=candidate_availability_bucket,
            prefer_cross_vendor=prefer_cross_vendor,
        )
        candidate.update(
            {
                "vendor_name": vendor_name or "-",
                "vendor_match": vendor_match,
                "cross_vendor": vendor_match == "cross_vendor",
                "availability_bucket": candidate_availability_bucket,
                "selection_bucket": candidate_selection_bucket,
                "selection_rank": selection_rank,
                "_stable_input_order": index,
                **selection_metadata,
            }
        )
        ordered_candidates.append(candidate)

    ordered_candidates.sort(
        key=lambda item: (
            int(item["selection_rank"]),
            int(item.get("reviewer_selection_priority") or 999),
            int(item["_stable_input_order"]),
        )
    )
    for rank, item in enumerate(ordered_candidates, start=1):
        item["priority"] = rank
        item.pop("_stable_input_order", None)

    cross_vendor_candidates = [
        item for item in ordered_candidates if str(item.get("vendor_match") or "") == "cross_vendor"
    ]
    preferred_candidates = list(ordered_candidates)
    if prefer_cross_vendor and cross_vendor_candidates:
        preferred_candidates = list(cross_vendor_candidates)
    elif prefer_cross_vendor and not allow_same_vendor_fallback:
        preferred_candidates = []

    return {
        "ordered_candidates": ordered_candidates,
        "preferred_candidates": preferred_candidates,
        "cross_vendor_candidate_count": cross_vendor_candidate_count,
        "same_vendor_candidate_count": same_vendor_candidate_count,
        "unknown_vendor_candidate_count": unknown_vendor_candidate_count,
        "available_candidate_count": available_candidate_count,
        "unknown_status_candidate_count": unknown_status_candidate_count,
    }

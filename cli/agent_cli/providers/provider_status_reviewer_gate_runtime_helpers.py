from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Mapping

from cli.agent_cli.runtime_services.expert_review_reviewer_capability_runtime import (
    EXPERT_REVIEW_REASONING_CAPABILITY_VALIDATION,
    EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY,
    EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE,
    resolve_expert_review_reviewer_capability,
)


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _boolish(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    normalized = _normalized_text(value)
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def _normalized_provider_key(value: Any) -> str:
    return str(value or "").strip().lower()


def _provider_identity_fields(item: Mapping[str, Any]) -> Dict[str, str]:
    config_name = str(item.get("config_provider_name") or item.get("provider_name") or "").strip()
    public_name = str(item.get("provider_name") or item.get("display_name") or config_name).strip()
    return {
        "config_provider_name": config_name,
        "provider_name": public_name,
        "_config_provider_key": _normalized_provider_key(config_name),
        "_provider_key": _normalized_provider_key(public_name),
    }


def _deduped_provider_items(items: Iterable[Mapping[str, Any]]) -> list[Dict[str, Any]]:
    deduped: dict[tuple[str, str], Dict[str, Any]] = {}
    for raw_item in items:
        item = dict(raw_item or {})
        identity = _provider_identity_fields(item)
        item.update(identity)
        dedupe_key = (
            identity["_config_provider_key"] or identity["_provider_key"],
            identity["_provider_key"] or identity["_config_provider_key"],
        )
        if dedupe_key not in deduped:
            deduped[dedupe_key] = item
    return list(deduped.values())


def _vendor_name_for_item(
    item: Mapping[str, Any],
    *,
    vendor_for_name_fn: Callable[[str], Any] | None,
) -> str:
    if vendor_for_name_fn is None:
        return ""
    for candidate in (
        str(item.get("provider_name") or "").strip(),
        str(item.get("config_provider_name") or "").strip(),
    ):
        if not candidate:
            continue
        try:
            vendor = vendor_for_name_fn(candidate)
        except Exception:
            vendor = None
        vendor_name = str(getattr(vendor, "name", "") or "").strip().lower()
        if vendor_name:
            return vendor_name
    return ""


def _available_reviewer_candidate(item: Mapping[str, Any]) -> bool:
    return _boolish(item.get("provider_base_eligible"))


def provider_reviewer_gate_fields(
    provider_items: Iterable[Mapping[str, Any]],
    *,
    active_provider_name: Any = "",
    active_provider_public_name: Any = "",
    min_eligible_providers: int = 2,
    prefer_cross_vendor: bool = True,
    allow_same_vendor_fallback: bool = True,
    feature_enabled: Any = True,
    feature_source: Any = "default",
    required_reasoning_effort: Any = "",
    reasoning_effort_source: Any = EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE,
    reviewer_capability_policy: Any = EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY,
    reviewer_capability_policy_source: Any = EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE,
    reasoning_capability_validation: Any = EXPERT_REVIEW_REASONING_CAPABILITY_VALIDATION,
    vendor_for_name_fn: Callable[[str], Any] | None = None,
) -> Dict[str, Any]:
    try:
        normalized_min = max(1, int(min_eligible_providers or 1))
    except (TypeError, ValueError):
        normalized_min = 2
    normalized_feature_enabled = _boolish(feature_enabled, default=True)
    normalized_feature_source = str(feature_source or "").strip() or "default"
    normalized_required_reasoning_effort = str(required_reasoning_effort or "").strip().lower()
    normalized_reasoning_effort_source = (
        str(reasoning_effort_source or "").strip() or EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE
    )
    normalized_reviewer_capability_policy = (
        str(reviewer_capability_policy or "").strip() or EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY
    )
    normalized_reviewer_capability_policy_source = (
        str(reviewer_capability_policy_source or "").strip()
        or EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE
    )
    normalized_reasoning_capability_validation = (
        str(reasoning_capability_validation or "").strip()
        or EXPERT_REVIEW_REASONING_CAPABILITY_VALIDATION
    )
    active_config_key = _normalized_provider_key(active_provider_name)
    active_public_key = _normalized_provider_key(active_provider_public_name)
    primary_provider_resolved = bool(active_config_key or active_public_key)

    deduped_items = _deduped_provider_items(provider_items)
    eligible_items = [item for item in deduped_items if _available_reviewer_candidate(item)]
    eligible_names = [
        str(item.get("provider_name") or "").strip()
        for item in eligible_items
        if str(item.get("provider_name") or "").strip()
    ]
    eligible_config_names = [
        str(item.get("config_provider_name") or "").strip()
        for item in eligible_items
        if str(item.get("config_provider_name") or "").strip()
    ]

    reviewer_candidates: list[Dict[str, Any]] = []
    reviewer_ineligible_names: list[str] = []
    reviewer_ineligible_reasons: dict[str, str] = {}
    for item in eligible_items:
        if (
            (active_config_key and active_config_key == str(item.get("_config_provider_key") or ""))
            or (active_public_key and active_public_key == str(item.get("_provider_key") or ""))
        ):
            continue
        capability = resolve_expert_review_reviewer_capability(item)
        if not bool(capability.get("reviewer_eligible")):
            provider_label = str(item.get("provider_name") or item.get("config_provider_name") or "").strip()
            if provider_label:
                reviewer_ineligible_names.append(provider_label)
                reviewer_ineligible_reasons[provider_label] = str(
                    capability.get("reviewer_eligibility_reason") or "unsupported_provider_or_model"
                )
            continue
        candidate = dict(item)
        candidate.update(capability)
        reviewer_candidates.append(candidate)
    reviewer_candidate_names = [
        str(item.get("provider_name") or "").strip()
        for item in reviewer_candidates
        if str(item.get("provider_name") or "").strip()
    ]
    reviewer_candidate_config_names = [
        str(item.get("config_provider_name") or "").strip()
        for item in reviewer_candidates
        if str(item.get("config_provider_name") or "").strip()
    ]

    active_vendor_name = ""
    if vendor_for_name_fn is not None:
        for candidate in (
            str(active_provider_public_name or "").strip(),
            str(active_provider_name or "").strip(),
        ):
            if not candidate:
                continue
            try:
                vendor = vendor_for_name_fn(candidate)
            except Exception:
                vendor = None
            active_vendor_name = str(getattr(vendor, "name", "") or "").strip().lower()
            if active_vendor_name:
                break

    cross_vendor_candidates: list[Dict[str, Any]] = []
    same_vendor_candidates: list[Dict[str, Any]] = []
    unknown_vendor_candidates: list[Dict[str, Any]] = []
    for item in reviewer_candidates:
        item_vendor_name = _vendor_name_for_item(item, vendor_for_name_fn=vendor_for_name_fn)
        if active_vendor_name and item_vendor_name:
            if item_vendor_name == active_vendor_name:
                same_vendor_candidates.append(item)
            else:
                cross_vendor_candidates.append(item)
            continue
        unknown_vendor_candidates.append(item)

    if prefer_cross_vendor and cross_vendor_candidates:
        preferred_candidates = list(cross_vendor_candidates)
    elif prefer_cross_vendor and not allow_same_vendor_fallback:
        preferred_candidates = []
    else:
        preferred_candidates = list(reviewer_candidates)

    available = True
    unavailable_reason = ""
    if not normalized_feature_enabled:
        available = False
        unavailable_reason = "feature_disabled"
    elif len(eligible_items) < normalized_min:
        available = False
        unavailable_reason = "insufficient_eligible_providers"
    elif not primary_provider_resolved:
        available = False
        unavailable_reason = "primary_provider_unknown"
    elif not reviewer_candidates:
        available = False
        unavailable_reason = "no_reviewer_candidate"
    elif prefer_cross_vendor and not allow_same_vendor_fallback and not cross_vendor_candidates:
        available = False
        unavailable_reason = "no_cross_vendor_candidate"
    elif not preferred_candidates:
        available = False
        unavailable_reason = "no_preferred_reviewer_candidate"

    gate_payload = {
        "available": available,
        "unavailable_reason": unavailable_reason,
        "feature_enabled": normalized_feature_enabled,
        "feature_source": normalized_feature_source,
        "required_reasoning_effort": normalized_required_reasoning_effort,
        "reasoning_effort_source": normalized_reasoning_effort_source,
        "reviewer_capability_policy": normalized_reviewer_capability_policy,
        "reviewer_capability_policy_source": normalized_reviewer_capability_policy_source,
        "reasoning_capability_validation": normalized_reasoning_capability_validation,
        "min_eligible_providers": normalized_min,
        "prefer_cross_vendor": bool(prefer_cross_vendor),
        "allow_same_vendor_fallback": bool(allow_same_vendor_fallback),
        "primary_provider_resolved": primary_provider_resolved,
        "primary_provider_name": str(active_provider_public_name or active_provider_name or "").strip(),
        "primary_vendor_name": active_vendor_name,
        "eligible_provider_count": len(eligible_items),
        "eligible_provider_names": eligible_names,
        "eligible_provider_config_names": eligible_config_names,
        "reviewer_candidate_count": len(reviewer_candidates),
        "reviewer_candidate_names": reviewer_candidate_names,
        "reviewer_candidate_config_names": reviewer_candidate_config_names,
        "reviewer_ineligible_candidate_count": len(reviewer_ineligible_names),
        "reviewer_ineligible_candidate_names": reviewer_ineligible_names,
        "reviewer_ineligible_candidate_reasons": reviewer_ineligible_reasons,
        "reviewer_cross_vendor_candidate_count": len(cross_vendor_candidates),
        "reviewer_cross_vendor_candidate_names": [
            str(item.get("provider_name") or "").strip()
            for item in cross_vendor_candidates
            if str(item.get("provider_name") or "").strip()
        ],
        "reviewer_same_vendor_candidate_count": len(same_vendor_candidates),
        "reviewer_same_vendor_candidate_names": [
            str(item.get("provider_name") or "").strip()
            for item in same_vendor_candidates
            if str(item.get("provider_name") or "").strip()
        ],
        "reviewer_unknown_vendor_candidate_count": len(unknown_vendor_candidates),
        "reviewer_unknown_vendor_candidate_names": [
            str(item.get("provider_name") or "").strip()
            for item in unknown_vendor_candidates
            if str(item.get("provider_name") or "").strip()
        ],
        "preferred_reviewer_candidate_count": len(preferred_candidates),
        "preferred_reviewer_candidate_names": [
            str(item.get("provider_name") or "").strip()
            for item in preferred_candidates
            if str(item.get("provider_name") or "").strip()
        ],
    }
    return {
        "expert_review_available": available,
        "expert_review_unavailable_reason": unavailable_reason or "-",
        "expert_review_feature_enabled": normalized_feature_enabled,
        "expert_review_feature_source": normalized_feature_source,
        "expert_review_required_reasoning_effort": normalized_required_reasoning_effort or "-",
        "expert_review_reasoning_effort_source": normalized_reasoning_effort_source,
        "expert_review_reviewer_capability_policy": normalized_reviewer_capability_policy,
        "expert_review_reviewer_capability_policy_source": normalized_reviewer_capability_policy_source,
        "expert_review_reasoning_capability_validation": normalized_reasoning_capability_validation,
        "expert_review_min_eligible_providers": normalized_min,
        "expert_review_prefer_cross_vendor": bool(prefer_cross_vendor),
        "expert_review_allow_same_vendor_fallback": bool(allow_same_vendor_fallback),
        "primary_provider_resolved": primary_provider_resolved,
        "primary_provider_name": str(active_provider_public_name or active_provider_name or "").strip() or "-",
        "primary_provider_vendor": active_vendor_name or "-",
        "eligible_provider_count": len(eligible_items),
        "eligible_provider_names": eligible_names,
        "eligible_provider_config_names": eligible_config_names,
        "reviewer_candidate_count": len(reviewer_candidates),
        "reviewer_candidate_names": reviewer_candidate_names,
        "reviewer_candidate_config_names": reviewer_candidate_config_names,
        "reviewer_ineligible_candidate_count": len(reviewer_ineligible_names),
        "reviewer_ineligible_candidate_names": reviewer_ineligible_names,
        "reviewer_cross_vendor_candidate_count": len(cross_vendor_candidates),
        "reviewer_cross_vendor_candidate_names": gate_payload["reviewer_cross_vendor_candidate_names"],
        "reviewer_same_vendor_candidate_count": len(same_vendor_candidates),
        "reviewer_same_vendor_candidate_names": gate_payload["reviewer_same_vendor_candidate_names"],
        "reviewer_unknown_vendor_candidate_count": len(unknown_vendor_candidates),
        "reviewer_unknown_vendor_candidate_names": gate_payload["reviewer_unknown_vendor_candidate_names"],
        "preferred_reviewer_candidate_count": len(preferred_candidates),
        "preferred_reviewer_candidate_names": gate_payload["preferred_reviewer_candidate_names"],
        "expert_review_gate": gate_payload,
    }

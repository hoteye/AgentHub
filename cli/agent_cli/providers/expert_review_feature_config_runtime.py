from __future__ import annotations

from typing import Any, Dict, Mapping

from cli.agent_cli.runtime_services.expert_review_reviewer_capability_runtime import (
    EXPERT_REVIEW_REASONING_CAPABILITY_VALIDATION,
    EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY,
    EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE,
)


_DEFAULT_MIN_ELIGIBLE_PROVIDERS = 2
_DEFAULT_PREFER_CROSS_VENDOR = True
_DEFAULT_ALLOW_SAME_VENDOR_FALLBACK = True
_DEFAULT_ENABLED = True


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _boolish(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = _normalized_text(value)
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def _intish(value: Any, *, default: int, minimum: int) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, normalized)


def expert_review_feature_settings_from_config(config: Mapping[str, Any] | None) -> Dict[str, Any]:
    feature_block: Mapping[str, Any] | None = None
    enabled_value: Any = None
    config_source = "default"

    if isinstance(config, Mapping):
        features = config.get("features")
        if isinstance(features, Mapping) and "expert_review" in features:
            raw_feature_block = features.get("expert_review")
            config_source = "workspace_config"
            if isinstance(raw_feature_block, Mapping):
                feature_block = raw_feature_block
                enabled_value = raw_feature_block.get("enabled")
            else:
                enabled_value = raw_feature_block

    block = dict(feature_block or {})
    enabled = _boolish(enabled_value, default=_DEFAULT_ENABLED)
    min_eligible_providers = _intish(
        block.get("min_eligible_providers"),
        default=_DEFAULT_MIN_ELIGIBLE_PROVIDERS,
        minimum=1,
    )
    prefer_cross_vendor = _boolish(
        block.get("prefer_cross_vendor"),
        default=_DEFAULT_PREFER_CROSS_VENDOR,
    )
    allow_same_vendor_fallback = _boolish(
        block.get("allow_same_vendor_fallback"),
        default=_DEFAULT_ALLOW_SAME_VENDOR_FALLBACK,
    )
    return {
        "enabled": enabled,
        "config_source": config_source,
        "min_eligible_providers": min_eligible_providers,
        "prefer_cross_vendor": prefer_cross_vendor,
        "allow_same_vendor_fallback": allow_same_vendor_fallback,
        "required_reasoning_effort": "",
        "reasoning_effort_source": EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE,
        "reviewer_capability_policy": EXPERT_REVIEW_REVIEWER_CAPABILITY_POLICY,
        "reviewer_capability_policy_source": EXPERT_REVIEW_REVIEWER_CAPABILITY_SOURCE,
        "reasoning_capability_validation": EXPERT_REVIEW_REASONING_CAPABILITY_VALIDATION,
    }

from __future__ import annotations

from typing import Any

from cli.agent_cli.orchestration.taskbook_state import TaskCardKind

_REWORK_ESCALATION_MIN_ATTEMPTS = 2


def policy_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def policy_bool(policy: dict[str, Any], *keys: str) -> bool | None:
    for key in keys:
        if key not in policy:
            continue
        value = policy.get(key)
        if isinstance(value, bool):
            return value
        text = str(value or "").strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
    return None


def policy_int(policy: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        if key not in policy:
            continue
        value = policy.get(key)
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed >= 1:
            return parsed
    return None


def policy_str_list(policy: dict[str, Any], *keys: str) -> list[str]:
    for key in keys:
        if key not in policy:
            continue
        value = policy.get(key)
        if isinstance(value, (list, tuple, set)):
            items = [str(item or "").strip().lower() for item in value]
            return [item for item in items if item]
        if isinstance(value, str):
            parts = [part.strip().lower() for part in value.split(",")]
            return [part for part in parts if part]
    return []


def contains_policy_keyword(value: str, keywords: list[str]) -> str:
    lowered = str(value or "").strip().lower()
    if not lowered:
        return ""
    for keyword in keywords:
        token = str(keyword or "").strip().lower()
        if token and token in lowered:
            return token
    return ""


def card_kind_label(card_kind: TaskCardKind | None) -> str:
    if isinstance(card_kind, TaskCardKind):
        return card_kind.value
    return ""


def coerce_kind_token(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if text in {"readonly", "read"}:
        return TaskCardKind.READ_ONLY.value
    if text in {"workspace", "workspace_mutation", "workspace_mutating"}:
        return TaskCardKind.WORKSPACE_MUTATING.value
    if text in {"long", "longrun", "long_running"}:
        return TaskCardKind.LONG_RUNNING.value
    return text


def kind_rule_bool(policy: dict[str, Any], key: str, *, card_kind: TaskCardKind | None) -> bool | None:
    value = policy.get(key)
    if not isinstance(value, dict):
        return None
    kind_token = card_kind_label(card_kind)
    if not kind_token:
        return None
    fallback: bool | None = None
    for raw_key, raw_value in value.items():
        token = coerce_kind_token(raw_key)
        nested = policy_bool({key: raw_value}, key)
        if nested is None:
            continue
        if token in {"default", "*", "all"}:
            fallback = nested
            continue
        if token == kind_token:
            return nested
    return fallback


def kind_rule_int(policy: dict[str, Any], key: str, *, card_kind: TaskCardKind | None) -> int | None:
    value = policy.get(key)
    if not isinstance(value, dict):
        return None
    kind_token = card_kind_label(card_kind)
    if not kind_token:
        return None
    fallback: int | None = None
    for raw_key, raw_value in value.items():
        token = coerce_kind_token(raw_key)
        parsed = policy_int({key: raw_value}, key)
        if parsed is None:
            continue
        if token in {"default", "*", "all"}:
            fallback = parsed
            continue
        if token == kind_token:
            return parsed
    return fallback


def kind_rule_str_list(policy: dict[str, Any], key: str, *, card_kind: TaskCardKind | None) -> list[str]:
    value = policy.get(key)
    if not isinstance(value, dict):
        return []
    kind_token = card_kind_label(card_kind)
    if not kind_token:
        return []
    fallback: list[str] = []
    for raw_key, raw_value in value.items():
        token = coerce_kind_token(raw_key)
        nested = policy_str_list({key: raw_value}, key)
        if not nested:
            continue
        if token in {"default", "*", "all"}:
            fallback = nested
            continue
        if token == kind_token:
            return nested
    return fallback


def workspace_change_requires_review(policy: dict[str, Any]) -> bool:
    value = policy_bool(
        policy,
        "workspace_change_requires_review",
        "require_review_for_workspace_changes",
    )
    return bool(value)


def rework_escalation_min_attempts(policy: dict[str, Any]) -> int:
    parsed = policy_int(
        policy,
        "rework_escalation_min_attempts",
        "rework_escalation_attempts",
    )
    if parsed is None:
        return _REWORK_ESCALATION_MIN_ATTEMPTS
    return max(1, parsed)


def rework_escalation_threshold(
    policy: dict[str, Any],
    *,
    card_kind: TaskCardKind | None,
) -> int:
    by_kind = kind_rule_int(
        policy,
        "rework_escalation_min_attempts_by_kind",
        card_kind=card_kind,
    )
    if by_kind is not None:
        return max(1, by_kind)
    return rework_escalation_min_attempts(policy)


def risk_requires_review(
    policy: dict[str, Any],
    *,
    card_kind: TaskCardKind | None,
) -> bool:
    by_kind = kind_rule_bool(
        policy,
        "risk_requires_review_by_kind",
        card_kind=card_kind,
    )
    if by_kind is not None:
        return by_kind
    if card_kind is TaskCardKind.READ_ONLY:
        read_only = policy_bool(
            policy,
            "read_only_risk_requires_review",
            "read_only_risk_auto_block",
        )
        if read_only is not None:
            return read_only
    return True


def risk_block_reason(
    risks: list[str],
    *,
    policy: dict[str, Any],
) -> str:
    keywords = policy_str_list(
        policy,
        "risk_block_keywords",
        "review_risk_keywords",
    )
    normalized = [str(item or "").strip() for item in risks if str(item or "").strip()]
    if keywords:
        for item in normalized:
            lowered = item.lower()
            for keyword in keywords:
                if keyword and keyword in lowered:
                    return f"reviewer_policy_risk_keyword:{keyword}"
    return _review_risk_reason(risks)


def risk_reject_reason(
    risks: list[str],
    *,
    policy: dict[str, Any],
    card_kind: TaskCardKind | None,
) -> str:
    keywords = kind_rule_str_list(
        policy,
        "risk_reject_keywords_by_kind",
        card_kind=card_kind,
    )
    if not keywords:
        keywords = policy_str_list(
        policy,
        "risk_reject_keywords",
        "review_risk_reject_keywords",
    )
    normalized = [str(item or "").strip() for item in risks if str(item or "").strip()]
    for item in normalized:
        matched = contains_policy_keyword(item, keywords)
        if matched:
            return f"reviewer_policy_risk_reject_keyword:{matched}"
    return ""


def workspace_change_requires_tests(
    policy: dict[str, Any],
    *,
    card_kind: TaskCardKind | None,
) -> bool:
    global_override = policy_bool(
        policy,
        "workspace_change_requires_test_evidence",
        "require_tests_for_workspace_changes",
    )
    if global_override is not None:
        return global_override
    by_kind = kind_rule_bool(
        policy,
        "workspace_change_requires_test_evidence_by_kind",
        card_kind=card_kind,
    )
    if by_kind is not None:
        return by_kind
    configured_kinds = policy_str_list(
        policy,
        "require_tests_for_card_kinds",
        "require_test_evidence_card_kinds",
    )
    if configured_kinds:
        kind_token = card_kind_label(card_kind)
        return kind_token in {coerce_kind_token(item) for item in configured_kinds}
    return card_kind is not TaskCardKind.READ_ONLY


def _review_risk_reason(risks: list[str]) -> str:
    normalized = [str(item or "").strip() for item in risks if str(item or "").strip()]
    for item in normalized:
        if "background_task_apply" in item or "background_task_reject" in item:
            return "staged_workspace_review_required"
    return "completed_result_risk_review_required"

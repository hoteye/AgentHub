from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List


MEMORY_TYPES: tuple[str, ...] = ("user", "project", "reference", "feedback")
MEMORY_SCOPES: tuple[str, ...] = ("project", "user")
MEMORY_STATUSES: tuple[str, ...] = ("active", "archived", "deleted")
MEMORY_TYPE_RECALL_WEIGHTS: dict[str, float] = {
    "project": 1.2,
    "reference": 1.0,
    "user": 0.8,
    "feedback": 0.6,
}
DEFAULT_RANKING_COMPONENT_WEIGHTS: dict[str, float] = {
    "tag": 3.0,
    "path": 4.0,
    "text": 2.0,
    "type": 1.0,
    "salience": 1.5,
}
MEMORY_CANDIDATE_REASONS: tuple[str, ...] = (
    "user_preference_signal",
    "project_constraint_signal",
    "reference_signal",
    "path_hint_detected",
    "blocked_sensitive_content",
)
MEMORY_CANDIDATE_DECISIONS: tuple[str, ...] = ("safe", "review", "block")
MEMORY_CANDIDATE_DECISION_REASONS: tuple[str, ...] = (
    "eligible_auto_writeback",
    "low_signal_short_content",
    "contains_sensitive_content",
)
MEMORY_USER_SCOPE_OPT_IN_ENV = "AGENTHUB_MEMORY_USER_SCOPE_ENABLED"


def normalize_memory_type(value: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in MEMORY_TYPES else "project"


def normalize_memory_scope(value: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in MEMORY_SCOPES else "project"


def user_scope_opt_in_enabled(value: bool | str | None = None) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        value = os.environ.get(MEMORY_USER_SCOPE_OPT_IN_ENV)
    normalized = str(value or "").strip().lower()
    return normalized in {"1", "true", "yes", "on", "enabled"}


def normalize_memory_status(value: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in MEMORY_STATUSES else "active"


def normalized_recall_weight_map(weights: dict[str, float] | None = None) -> dict[str, float]:
    payload = dict(MEMORY_TYPE_RECALL_WEIGHTS)
    for raw_key, raw_value in dict(weights or {}).items():
        raw_text = str(raw_key or "").strip().lower()
        if raw_text not in MEMORY_TYPES:
            continue
        key = raw_text
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        payload[key] = value
    return payload


def normalized_ranking_weight_contract(
    ranking_weights: Dict[str, Any] | None = None,
    *,
    type_weights: dict[str, float] | None = None,
) -> Dict[str, Any]:
    payload = dict(ranking_weights or {})
    normalized_components = dict(DEFAULT_RANKING_COMPONENT_WEIGHTS)
    component_payload = payload.get("components")
    if isinstance(component_payload, dict):
        for key in list(DEFAULT_RANKING_COMPONENT_WEIGHTS.keys()):
            try:
                if key in component_payload:
                    normalized_components[key] = float(component_payload[key])
            except (TypeError, ValueError):
                continue
    for key in list(DEFAULT_RANKING_COMPONENT_WEIGHTS.keys()):
        flat_key = f"{key}_weight"
        try:
            if flat_key in payload:
                normalized_components[key] = float(payload[flat_key])
        except (TypeError, ValueError):
            continue
    normalized_type_weights = normalized_recall_weight_map(type_weights)
    contract_type_payload = payload.get("type_weights")
    if isinstance(contract_type_payload, dict):
        normalized_type_weights = normalized_recall_weight_map(contract_type_payload)
    return {
        "components": normalized_components,
        "type_weights": normalized_type_weights,
    }


def normalize_string_list(values: Iterable[str] | None) -> List[str]:
    items: List[str] = []
    seen: set[str] = set()
    for raw_value in list(values or []):
        item = str(raw_value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        items.append(item)
    return items


def normalize_candidate_decision(value: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in MEMORY_CANDIDATE_DECISIONS else "review"


def normalize_candidate_decision_reason(value: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in MEMORY_CANDIDATE_DECISION_REASONS else "low_signal_short_content"


def memory_auto_writeback_enabled(
    *,
    scope: str,
    memory_type: str,
    policy: Dict[str, Any] | None = None,
) -> bool:
    normalized_scope = normalize_memory_scope(scope)
    normalized_type = normalize_memory_type(memory_type)
    payload = dict(policy or {})

    # Match order: exact scope/type pair > scope-wide > type-wide > default.
    pairs = payload.get("scope_types")
    if isinstance(pairs, dict):
        exact_key = f"{normalized_scope}:{normalized_type}"
        if exact_key in pairs:
            return bool(pairs.get(exact_key))

    scopes = payload.get("scopes")
    if isinstance(scopes, dict) and normalized_scope in scopes:
        return bool(scopes.get(normalized_scope))

    types = payload.get("types")
    if isinstance(types, dict) and normalized_type in types:
        return bool(types.get(normalized_type))

    return bool(payload.get("enabled", False))

from __future__ import annotations

import re
from typing import Any


APPROVAL_DECISION_ACCEPT = "accept"
APPROVAL_DECISION_ACCEPT_FOR_SESSION = "accept_for_session"
APPROVAL_DECISION_ACCEPT_WITH_EXECPOLICY_AMENDMENT = "accept_with_execpolicy_amendment"
APPROVAL_DECISION_DECLINE = "decline"
APPROVAL_DECISION_CANCEL = "cancel"

APPROVAL_DECISION_TYPES = (
    APPROVAL_DECISION_ACCEPT,
    APPROVAL_DECISION_ACCEPT_FOR_SESSION,
    APPROVAL_DECISION_ACCEPT_WITH_EXECPOLICY_AMENDMENT,
    APPROVAL_DECISION_DECLINE,
    APPROVAL_DECISION_CANCEL,
)
_ACCEPTING_DECISIONS = {
    APPROVAL_DECISION_ACCEPT,
    APPROVAL_DECISION_ACCEPT_FOR_SESSION,
    APPROVAL_DECISION_ACCEPT_WITH_EXECPOLICY_AMENDMENT,
}


def _copy_mapping(value: Any) -> dict[str, Any] | None:
    return dict(value) if isinstance(value, dict) else None


def _copy_mapping_list(values: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in list(values or []):
        if isinstance(item, dict):
            result.append(dict(item))
    return result


def _normalized_token(value: Any) -> str:
    return str(value or "").strip()


def _decision_spec(decision_type: str, **payload: Any) -> dict[str, Any]:
    result = {"type": decision_type}
    for key, value in payload.items():
        if value in ("", None, [], {}):
            continue
        result[key] = value
    return result


def generic_available_decisions() -> list[dict[str, Any]]:
    return [
        _decision_spec(APPROVAL_DECISION_ACCEPT),
        _decision_spec(APPROVAL_DECISION_DECLINE),
        _decision_spec(APPROVAL_DECISION_CANCEL),
    ]


def browser_available_decisions(*, allow_for_session: bool = False) -> list[dict[str, Any]]:
    decisions = [_decision_spec(APPROVAL_DECISION_ACCEPT)]
    if allow_for_session:
        decisions.append(_decision_spec(APPROVAL_DECISION_ACCEPT_FOR_SESSION))
    decisions.extend(
        (
            _decision_spec(APPROVAL_DECISION_DECLINE),
            _decision_spec(APPROVAL_DECISION_CANCEL),
        )
    )
    return decisions


def approval_execpolicy_amendment_rule(proposed_rule: dict[str, Any] | None) -> dict[str, Any] | None:
    normalized = _copy_mapping(proposed_rule)
    if not normalized:
        return None
    pattern = normalized.get("pattern")
    normalized_command = _normalized_token(normalized.get("normalized_command"))
    command_tokens = list(normalized.get("command_tokens") or [])
    if not pattern and not normalized_command and not command_tokens:
        return None
    normalized["decision"] = "allow"
    return normalized


def shell_available_decisions(proposed_rule: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    decisions = [
        _decision_spec(APPROVAL_DECISION_ACCEPT),
        _decision_spec(APPROVAL_DECISION_ACCEPT_FOR_SESSION),
    ]
    amendment = approval_execpolicy_amendment_rule(proposed_rule)
    if amendment is not None:
        decisions.append(
            _decision_spec(
                APPROVAL_DECISION_ACCEPT_WITH_EXECPOLICY_AMENDMENT,
                proposed_rule=amendment,
            )
        )
    decisions.extend(
        (
            _decision_spec(APPROVAL_DECISION_DECLINE),
            _decision_spec(APPROVAL_DECISION_CANCEL),
        )
    )
    return decisions


def patch_available_decisions(*, grant_root: str | None = None) -> list[dict[str, Any]]:
    return [
        _decision_spec(APPROVAL_DECISION_ACCEPT),
        _decision_spec(APPROVAL_DECISION_ACCEPT_FOR_SESSION, grant_root=_normalized_token(grant_root) or None),
        _decision_spec(APPROVAL_DECISION_DECLINE),
        _decision_spec(APPROVAL_DECISION_CANCEL),
    ]


def normalize_available_decisions(values: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in list(values or []):
        try:
            result.append(normalize_approval_decision(item))
        except ValueError:
            continue
    return result


def available_decision_types(values: Any) -> list[str]:
    return [str(item.get("type") or "").strip() for item in normalize_available_decisions(values)]


def is_approval_accepting(decision: Any) -> bool:
    return str(normalize_approval_decision(decision).get("type") or "") in _ACCEPTING_DECISIONS


def normalize_approval_decision(
    value: Any,
    *,
    fallback_proposed_rule: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(value, dict):
        if "type" in value:
            spec = normalize_approval_decision(
                value.get("type"),
                fallback_proposed_rule=_copy_mapping(
                    value.get("proposed_rule")
                    or value.get("execpolicy_amendment")
                    or value.get("execpolicyAmendment")
                    or fallback_proposed_rule
                ),
            )
            merged = dict(spec)
            for key, item in value.items():
                if key == "type":
                    continue
                if item in ("", None, [], {}):
                    continue
                merged[key] = dict(item) if isinstance(item, dict) else item
            return merged
        if "acceptWithExecpolicyAmendment" in value or "accept_with_execpolicy_amendment" in value:
            payload = value.get("acceptWithExecpolicyAmendment") or value.get("accept_with_execpolicy_amendment")
            payload_map = dict(payload) if isinstance(payload, dict) else {}
            proposed_rule = approval_execpolicy_amendment_rule(
                _copy_mapping(
                    payload_map.get("execpolicy_amendment")
                    or payload_map.get("execpolicyAmendment")
                    or payload_map.get("proposed_rule")
                    or fallback_proposed_rule
                )
            )
            return _decision_spec(
                APPROVAL_DECISION_ACCEPT_WITH_EXECPOLICY_AMENDMENT,
                proposed_rule=proposed_rule,
            )
        if "decision" in value:
            return normalize_approval_decision(
                value.get("decision"),
                fallback_proposed_rule=_copy_mapping(
                    value.get("proposed_rule")
                    or value.get("execpolicy_amendment")
                    or value.get("execpolicyAmendment")
                    or fallback_proposed_rule
                ),
            )

    text = _normalized_token(value)
    compact = re.sub(r"[^a-z]", "", text.lower())
    if compact in {"approve", "approved", "accept", "acceptonce", "once", "yes", "proceed"}:
        return _decision_spec(APPROVAL_DECISION_ACCEPT)
    if compact in {"acceptforsession", "session", "allowforsession"}:
        return _decision_spec(APPROVAL_DECISION_ACCEPT_FOR_SESSION)
    if compact in {
        "acceptwithexecpolicyamendment",
        "acceptwithrule",
        "rule",
        "prefix",
        "amendment",
    }:
        return _decision_spec(
            APPROVAL_DECISION_ACCEPT_WITH_EXECPOLICY_AMENDMENT,
            proposed_rule=approval_execpolicy_amendment_rule(fallback_proposed_rule),
        )
    if compact in {"reject", "rejected", "decline", "deny", "denied", "no"}:
        return _decision_spec(APPROVAL_DECISION_DECLINE)
    if compact in {"cancel", "abort"}:
        return _decision_spec(APPROVAL_DECISION_CANCEL)
    raise ValueError(f"unsupported approval decision: {value!r}")


def merge_available_decision(
    *,
    available_decisions: Any,
    decision: Any,
    fallback_proposed_rule: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = normalize_approval_decision(decision, fallback_proposed_rule=fallback_proposed_rule)
    decision_type = str(resolved.get("type") or "").strip()
    choices = normalize_available_decisions(available_decisions)
    if not choices:
        return resolved
    for candidate in choices:
        if str(candidate.get("type") or "").strip() != decision_type:
            continue
        merged = dict(candidate)
        merged.update({key: value for key, value in resolved.items() if key != "type"})
        return merged
    raise ValueError(f"approval decision {decision_type!r} is not allowed for this request")


def approval_option_commands(approval_id: str, available_decisions: Any) -> list[str]:
    normalized_id = _normalized_token(approval_id)
    if not normalized_id:
        return []
    commands: list[str] = []
    seen: set[str] = set()
    for item in normalize_available_decisions(available_decisions):
        decision_type = str(item.get("type") or "").strip()
        if decision_type == APPROVAL_DECISION_ACCEPT:
            command = f"/approve {normalized_id}"
        elif decision_type == APPROVAL_DECISION_ACCEPT_FOR_SESSION:
            command = f"/approve {normalized_id} mode session"
        elif decision_type == APPROVAL_DECISION_ACCEPT_WITH_EXECPOLICY_AMENDMENT:
            command = f"/approve {normalized_id} mode rule"
        elif decision_type == APPROVAL_DECISION_DECLINE:
            command = f"/reject {normalized_id}"
        elif decision_type == APPROVAL_DECISION_CANCEL:
            command = f"/reject {normalized_id} mode cancel"
        else:
            continue
        if command not in seen:
            seen.add(command)
            commands.append(command)
    return commands


__all__ = [
    "APPROVAL_DECISION_ACCEPT",
    "APPROVAL_DECISION_ACCEPT_FOR_SESSION",
    "APPROVAL_DECISION_ACCEPT_WITH_EXECPOLICY_AMENDMENT",
    "APPROVAL_DECISION_CANCEL",
    "APPROVAL_DECISION_DECLINE",
    "APPROVAL_DECISION_TYPES",
    "approval_execpolicy_amendment_rule",
    "approval_option_commands",
    "available_decision_types",
    "browser_available_decisions",
    "generic_available_decisions",
    "is_approval_accepting",
    "merge_available_decision",
    "normalize_approval_decision",
    "normalize_available_decisions",
    "patch_available_decisions",
    "shell_available_decisions",
]

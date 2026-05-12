from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, TypeVar

from cli.agent_cli.runtime_exec_policy_models import (
    ExecApprovalRequirementKind,
    parse_exec_approval_requirement_kind,
)


class ActionPolicyDecisionValue(str, Enum):
    ALLOWED = "allowed"
    REQUIRES_APPROVAL = "requires_approval"
    BLOCKED = "blocked"


_EnumT = TypeVar("_EnumT", bound=Enum)


def _parse_enum(enum_cls: type[_EnumT], value: Any, *, field_name: str) -> _EnumT:
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls(str(value or "").strip())
    except ValueError as exc:
        choices = ", ".join(item.value for item in enum_cls)
        raise ValueError(f"invalid {field_name}: {value!r}; expected one of: {choices}") from exc


def _copied_mapping(value: Any) -> Dict[str, Any] | None:
    return dict(value) if isinstance(value, dict) else None


def _copied_mapping_items(values: Iterable[Any] | None) -> tuple[Dict[str, Any], ...]:
    if values is None:
        return ()
    if isinstance(values, dict):
        return (dict(values),)
    copied: list[Dict[str, Any]] = []
    for item in values:
        if isinstance(item, dict):
            copied.append(dict(item))
    return tuple(copied)


def _copied_string_items(values: Iterable[Any] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        text = values.strip()
        return (text,) if text else ()
    copied: list[str] = []
    for item in values:
        text = str(item or "").strip()
        if text:
            copied.append(text)
    return tuple(copied)


def parse_action_policy_decision(
    value: Any,
    *,
    field_name: str = "action_policy.decision",
) -> ActionPolicyDecisionValue:
    return _parse_enum(ActionPolicyDecisionValue, value, field_name=field_name)


@dataclass(frozen=True, slots=True)
class ActionPolicyDecision:
    action_kind: str
    decision: ActionPolicyDecisionValue
    requirement: ExecApprovalRequirementKind
    reason_code: str = ""
    reason_text: str = ""
    approval_policy: str = ""
    sandbox_mode: str = ""
    matched_rules: tuple[Dict[str, Any], ...] = field(default_factory=tuple)
    proposed_rule: Dict[str, Any] | None = None
    normalized_targets: tuple[str, ...] = field(default_factory=tuple)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "action_kind", str(self.action_kind or "").strip())
        object.__setattr__(
            self,
            "decision",
            parse_action_policy_decision(self.decision),
        )
        object.__setattr__(
            self,
            "requirement",
            parse_exec_approval_requirement_kind(
                self.requirement,
                field_name="action_policy.requirement",
            ),
        )
        object.__setattr__(self, "reason_code", str(self.reason_code or "").strip())
        object.__setattr__(self, "reason_text", str(self.reason_text or "").strip())
        object.__setattr__(self, "approval_policy", str(self.approval_policy or "").strip())
        object.__setattr__(self, "sandbox_mode", str(self.sandbox_mode or "").strip())
        object.__setattr__(self, "matched_rules", _copied_mapping_items(self.matched_rules))
        object.__setattr__(self, "proposed_rule", _copied_mapping(self.proposed_rule))
        object.__setattr__(self, "normalized_targets", _copied_string_items(self.normalized_targets))
        object.__setattr__(self, "metadata", _copied_mapping(self.metadata) or {})

    @property
    def approval_required(self) -> bool:
        return self.requirement is ExecApprovalRequirementKind.NEEDS_APPROVAL

    @property
    def blocked(self) -> bool:
        return self.requirement is ExecApprovalRequirementKind.FORBIDDEN

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_kind": self.action_kind,
            "decision": self.decision.value,
            "requirement": self.requirement.value,
            "reason_code": self.reason_code,
            "reason_text": self.reason_text,
            "approval_policy": self.approval_policy,
            "sandbox_mode": self.sandbox_mode,
            "approval_required": self.approval_required,
            "blocked": self.blocked,
            "matched_rules": [dict(item) for item in self.matched_rules],
            "proposed_rule": None if self.proposed_rule is None else dict(self.proposed_rule),
            "normalized_targets": list(self.normalized_targets),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "ActionPolicyDecision":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            action_kind=str(data.get("action_kind") or "").strip(),
            decision=parse_action_policy_decision(data.get("decision")),
            requirement=parse_exec_approval_requirement_kind(
                data.get("requirement"),
                field_name="action_policy.requirement",
            ),
            reason_code=str(data.get("reason_code") or "").strip(),
            reason_text=str(data.get("reason_text") or "").strip(),
            approval_policy=str(data.get("approval_policy") or "").strip(),
            sandbox_mode=str(data.get("sandbox_mode") or "").strip(),
            matched_rules=_copied_mapping_items(data.get("matched_rules")),
            proposed_rule=_copied_mapping(data.get("proposed_rule")),
            normalized_targets=_copied_string_items(data.get("normalized_targets")),
            metadata=_copied_mapping(data.get("metadata")) or {},
        )


__all__ = [
    "ActionPolicyDecision",
    "ActionPolicyDecisionValue",
    "parse_action_policy_decision",
]

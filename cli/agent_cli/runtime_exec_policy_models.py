from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, TypeAlias, TypeVar


class CommandApprovalDecisionValue(str, Enum):
    ALLOW = "allow"
    PROMPT = "prompt"
    FORBIDDEN = "forbidden"


class ExecApprovalRequirementKind(str, Enum):
    SKIP = "skip"
    NEEDS_APPROVAL = "needs_approval"
    FORBIDDEN = "forbidden"


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


def parse_command_approval_decision(
    value: Any,
    *,
    field_name: str = "command_approval_decision.decision",
) -> CommandApprovalDecisionValue:
    return _parse_enum(CommandApprovalDecisionValue, value, field_name=field_name)


def parse_exec_approval_requirement_kind(
    value: Any,
    *,
    field_name: str = "exec_approval_requirement.requirement",
) -> ExecApprovalRequirementKind:
    return _parse_enum(ExecApprovalRequirementKind, value, field_name=field_name)


@dataclass(frozen=True, slots=True)
class CommandApprovalDecision:
    decision: CommandApprovalDecisionValue
    reason_code: str = ""
    reason_text: str = ""
    matched_rules: tuple[Dict[str, Any], ...] = field(default_factory=tuple)
    proposed_rule: Dict[str, Any] | None = None
    normalized_segments: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "decision",
            parse_command_approval_decision(self.decision),
        )
        object.__setattr__(self, "reason_code", str(self.reason_code or "").strip())
        object.__setattr__(self, "reason_text", str(self.reason_text or "").strip())
        object.__setattr__(self, "matched_rules", _copied_mapping_items(self.matched_rules))
        object.__setattr__(self, "proposed_rule", _copied_mapping(self.proposed_rule))
        object.__setattr__(self, "normalized_segments", _copied_string_items(self.normalized_segments))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reason_code": self.reason_code,
            "reason_text": self.reason_text,
            "matched_rules": [dict(item) for item in self.matched_rules],
            "proposed_rule": None if self.proposed_rule is None else dict(self.proposed_rule),
            "normalized_segments": list(self.normalized_segments),
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any] | None) -> "CommandApprovalDecision":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            decision=parse_command_approval_decision(data.get("decision")),
            reason_code=str(data.get("reason_code") or "").strip(),
            reason_text=str(data.get("reason_text") or "").strip(),
            matched_rules=_copied_mapping_items(data.get("matched_rules")),
            proposed_rule=_copied_mapping(data.get("proposed_rule")),
            normalized_segments=_copied_string_items(data.get("normalized_segments")),
        )


@dataclass(frozen=True, slots=True)
class Skip:
    requirement: ExecApprovalRequirementKind = field(default=ExecApprovalRequirementKind.SKIP, init=False)

    def to_dict(self) -> Dict[str, str]:
        return {"requirement": self.requirement.value}


@dataclass(frozen=True, slots=True)
class NeedsApproval:
    requirement: ExecApprovalRequirementKind = field(default=ExecApprovalRequirementKind.NEEDS_APPROVAL, init=False)

    def to_dict(self) -> Dict[str, str]:
        return {"requirement": self.requirement.value}


@dataclass(frozen=True, slots=True)
class Forbidden:
    requirement: ExecApprovalRequirementKind = field(default=ExecApprovalRequirementKind.FORBIDDEN, init=False)

    def to_dict(self) -> Dict[str, str]:
        return {"requirement": self.requirement.value}


ExecApprovalRequirement: TypeAlias = Skip | NeedsApproval | Forbidden


__all__ = [
    "CommandApprovalDecision",
    "CommandApprovalDecisionValue",
    "ExecApprovalRequirement",
    "ExecApprovalRequirementKind",
    "Forbidden",
    "NeedsApproval",
    "Skip",
    "parse_command_approval_decision",
    "parse_exec_approval_requirement_kind",
]

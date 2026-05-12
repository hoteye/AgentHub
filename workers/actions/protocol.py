from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional


class ActionError(RuntimeError):
    """Raised when a controlled action request is invalid or denied."""


@dataclass(frozen=True)
class ActionRequest:
    action: str
    parameters: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None
    correlation_id: str | None = None
    actor_id: str | None = None
    run_id: str | None = None
    agent_id: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ActionRequest":
        return cls(
            action=str(value.get("action") or "").strip(),
            parameters=dict(value.get("parameters") or {}),
            request_id=str(value.get("request_id") or "").strip() or None,
            correlation_id=str(value.get("correlation_id") or "").strip() or None,
            actor_id=str(value.get("actor_id") or "").strip() or None,
            run_id=str(value.get("run_id") or "").strip() or None,
            agent_id=str(value.get("agent_id") or "").strip() or None,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    action: str
    summary: str
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    request_id: str | None = None
    correlation_id: str | None = None
    run_id: str | None = None
    agent_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

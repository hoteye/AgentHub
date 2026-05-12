from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict


@dataclass(frozen=True, slots=True)
class ResolvedInteractionContract:
    profile: str
    source: str
    base_prompt_profile: str
    tool_surface_profile: str
    context_prelude_policy: str
    tool_result_projection_policy: str
    continuation_policy: str
    turn_protocol_policy: str
    fallback_profile: str
    conflict_reason: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


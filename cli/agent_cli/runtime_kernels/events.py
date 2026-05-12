from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class KernelEvent:
    event_type: str
    session_id: str = ""
    turn_id: str = ""
    item_id: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    raw_event: dict[str, Any] = field(default_factory=dict)

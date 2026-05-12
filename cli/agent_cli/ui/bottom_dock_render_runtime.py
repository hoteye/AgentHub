from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BottomDockRenderState:
    primary_line: str
    secondary_line: str


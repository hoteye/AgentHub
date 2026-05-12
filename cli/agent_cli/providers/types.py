from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderVendorSpec:
    name: str
    aliases: tuple[str, ...]
    default_protocol_family: str
    description: str = ""
    line_model_selectors: tuple[tuple[str, str], ...] = ()

    def model_selector_for_line(self, line: str) -> str | None:
        normalized = str(line or "").strip().lower()
        for candidate_line, selector in self.line_model_selectors:
            if normalized == str(candidate_line or "").strip().lower():
                return str(selector or "").strip() or None
        return None


@dataclass(frozen=True)
class PlannerRuntimeFamily:
    name: str
    planner_kinds: tuple[str, ...]
    description: str = ""

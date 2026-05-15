from __future__ import annotations

from typing import Any


def _command_detail_line_is_structured(line: str) -> bool:
    key, separator, _value = str(line or "").strip().partition("=")
    if separator != "=" or not key:
        return False
    return all(char.isalnum() or char in {"_", "-", "."} for char in key)


def command_display_text_from_assistant_text(assistant_text: str) -> str:
    lines = [
        raw_line.strip() for raw_line in str(assistant_text or "").splitlines() if raw_line.strip()
    ]
    if not lines:
        return ""
    if len(lines) == 1:
        return lines[0]
    if all(_command_detail_line_is_structured(line) for line in lines[1:]):
        return lines[0]
    return ""


def command_display_text_from_tool_events(tool_events: list[Any]) -> str:
    if (
        tool_events
        and str(getattr(tool_events[0], "name", "") or "").strip() == "approval_decision"
    ):
        return ""
    for event in list(tool_events or []):
        summary = str(getattr(event, "summary", "") or "").strip()
        if summary:
            return summary
    return ""


def default_command_display_text(
    *,
    assistant_text: str,
    tool_events: list[Any] | None = None,
) -> str:
    return command_display_text_from_assistant_text(
        assistant_text
    ) or command_display_text_from_tool_events(list(tool_events or []))

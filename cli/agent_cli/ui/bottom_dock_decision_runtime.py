from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BottomDockDecision:
    status_line: str
    footer_left: str
    footer_right: str


def decide_bottom_dock_content(
    *,
    screen_mode: str,
    status_line: str,
    passive_summary_active: bool,
    prompt_has_text: bool,
    busy: bool,
    queue_dominant_active: bool,
    footer_context_text: str,
    footer_shortcuts_text: str,
    footer_queue_text: str,
    transcript_prompt_view_text: str,
    transcript_exit_text: str,
) -> BottomDockDecision:
    normalized_mode = str(screen_mode or "prompt").strip().lower()
    if normalized_mode == "transcript":
        return BottomDockDecision(
            status_line="",
            footer_left=transcript_prompt_view_text,
            footer_right=transcript_exit_text,
        )

    if queue_dominant_active:
        return BottomDockDecision(
            status_line=status_line,
            footer_left=footer_queue_text,
            footer_right=footer_context_text,
        )

    if prompt_has_text:
        return BottomDockDecision(
            status_line=status_line,
            footer_left="",
            footer_right=footer_context_text,
        )

    if passive_summary_active:
        return BottomDockDecision(
            status_line=status_line,
            footer_left="",
            footer_right=footer_context_text,
        )

    return BottomDockDecision(
        status_line=status_line,
        footer_left="",
        footer_right=footer_context_text,
    )

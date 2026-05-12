from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.style import Style as RichStyle

from cli.agent_cli.ui import transcript_visual_rendering_runtime
from cli.agent_cli.ui.theme import (
    CliTheme,
    ThemeStyles,
    build_theme_styles,
    default_theme,
)

if TYPE_CHECKING:
    from cli.agent_cli.ui.transcript_history import TranscriptEntry


LAYERED_TRANSCRIPT_GROUPS = {"system", "user", "commentary", "reasoning", "tool", "web", "separator", "final"}


def _styles_for_theme(theme: CliTheme | None) -> ThemeStyles:
    return build_theme_styles(theme or default_theme())


def render_transcript_entries(entries: list["TranscriptEntry"]) -> list[str]:
    lines: list[str] = []
    pending_blank = False
    previous_visible: "TranscriptEntry" | None = None
    for entry in entries:
        if entry.kind == "blank":
            pending_blank = previous_visible is not None
            continue
        if previous_visible is not None and (pending_blank or should_insert_layer_gap(previous_visible, entry)):
            if lines and lines[-1] != "":
                lines.append("")
        visible_lines = entry.expanded_lines if entry.expanded and entry.expanded_lines else entry.lines
        lines.extend(str(line) for line in visible_lines)
        previous_visible = entry
        pending_blank = False
    return lines


def render_transcript_visual_entries(
    entries: list["TranscriptEntry"],
    *,
    width: int,
    theme: CliTheme | None = None,
    console: Console | None = None,
) -> "RenderedTranscript":
    styles = _styles_for_theme(theme)
    lines: list[str] = []
    line_styles: list[list[tuple[int, int, RichStyle]]] = []
    pending_blank = False
    previous_visible: "TranscriptEntry" | None = None
    render_width = max(20, int(width or 0))
    for entry in entries:
        if entry.kind == "blank":
            pending_blank = previous_visible is not None
            continue
        if previous_visible is not None and (pending_blank or should_insert_layer_gap(previous_visible, entry)):
            if lines and lines[-1] != "":
                lines.append("")
                line_styles.append([])
        visual_lines = transcript_visual_rendering_runtime.visual_lines_for_entry(
            entry,
            width=render_width,
            console=console,
            styles=styles,
        )
        for line_text, spans in visual_lines:
            lines.append(line_text)
            line_styles.append(spans)
        previous_visible = entry
        pending_blank = False
    return RenderedTranscript(lines=lines, line_styles=line_styles)


def should_insert_layer_gap(previous: "TranscriptEntry", current: "TranscriptEntry") -> bool:
    if previous.layer not in LAYERED_TRANSCRIPT_GROUPS or current.layer not in LAYERED_TRANSCRIPT_GROUPS:
        return False
    return previous.layer != current.layer


def _separator_line(width: int, *, label: str = "") -> str:
    return transcript_visual_rendering_runtime.separator_line(width, label=label)


class RenderedTranscript:
    def __init__(self, *, lines: list[str], line_styles: list[list[tuple[int, int, RichStyle]]]) -> None:
        self.lines = lines
        self.line_styles = line_styles

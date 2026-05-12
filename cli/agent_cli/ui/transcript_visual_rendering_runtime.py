from __future__ import annotations

from typing import TYPE_CHECKING

from rich.cells import cell_len
from rich.console import Console
from rich.style import Style as RichStyle

from cli.agent_cli.ui.markdown_render import render_markdown_visual_lines
from cli.agent_cli.ui.theme import (
    TRANSCRIPT_MESSAGE_PREFIX,
    ThemeStyles,
)
from cli.agent_cli.ui.transcript_visual_rendering_helpers import (
    markdown_base_style,
    markdown_line_styles,
    markdown_prefix_style,
    normalized_completion_stamp_line,
    plain_line_styles,
    prefix_rendered_lines,
    wrap_prefixed_text,
)

if TYPE_CHECKING:
    from cli.agent_cli.ui.transcript_history import TranscriptEntry


def visual_lines_for_entry(
    entry: TranscriptEntry,
    *,
    width: int,
    console: Console | None,
    styles: ThemeStyles,
) -> list[tuple[str, list[tuple[int, int, RichStyle]]]]:
    if entry.render_mode in {"markdown", "reasoning_markdown"} and entry.raw_content is not None:
        return render_markdown_entry_lines(entry, width=width, console=console, styles=styles)
    if entry.render_mode == "separator":
        return render_separator_entry_lines(entry, width=width, styles=styles)
    if entry.render_mode == "tool_command":
        return render_tool_command_entry_lines(entry, width=width, styles=styles)
    if entry.render_mode == "tool_mcp":
        return render_tool_mcp_entry_lines(entry, width=width, styles=styles)
    if entry.render_mode == "web_search":
        return render_web_search_entry_lines(entry, width=width, styles=styles)
    if entry.render_mode == "todo_list":
        return render_todo_list_entry_lines(entry, width=width, styles=styles)
    visible_lines = entry.expanded_lines if entry.expanded and entry.expanded_lines else entry.lines
    rendered_lines: list[tuple[str, list[tuple[int, int, RichStyle]]]] = []
    for line_index, line in enumerate(visible_lines):
        line_text = str(line)
        normalized_completion_line = normalized_completion_stamp_line(line_text)
        if normalized_completion_line is not None:
            line_text = normalized_completion_line
        rendered_lines.append(
            (line_text, plain_line_styles(entry, line_index, line_text, styles=styles))
        )
    return rendered_lines


def render_markdown_entry_lines(
    entry: TranscriptEntry,
    *,
    width: int,
    console: Console | None,
    styles: ThemeStyles,
) -> list[tuple[str, list[tuple[int, int, RichStyle]]]]:
    del width, console
    content = str(entry.raw_content or "")
    base_style = markdown_base_style(entry, styles=styles)
    visible_lines = [
        (
            line.text,
            markdown_line_styles(
                line.text,
                line.spans,
                base_style,
                styles=styles,
                merge_base_semantics=entry.kind == "reasoning",
            ),
        )
        for line in render_markdown_visual_lines(content)
    ]
    prefixed_lines = prefix_rendered_lines(
        visible_lines,
        first_prefix=TRANSCRIPT_MESSAGE_PREFIX,
        continuation_prefix="",
        prefix_style=markdown_prefix_style(entry, styles=styles),
    )
    rendered: list[tuple[str, list[tuple[int, int, RichStyle]]]] = []
    for line_text, spans in prefixed_lines:
        normalized_completion_line = normalized_completion_stamp_line(line_text)
        if normalized_completion_line is not None:
            rendered.append(
                (
                    normalized_completion_line,
                    [(0, len(normalized_completion_line), styles.completion_time_style)],
                )
            )
            continue
        rendered.append((line_text, spans))
    return rendered


def render_tool_command_entry_lines(
    entry: TranscriptEntry,
    *,
    width: int,
    styles: ThemeStyles,
) -> list[tuple[str, list[tuple[int, int, RichStyle]]]]:
    visible_lines = entry.expanded_lines if entry.expanded and entry.expanded_lines else entry.lines
    if not visible_lines:
        return []
    header_line = str(visible_lines[0] or "")
    prefix = "• Running " if header_line.startswith("• Running ") else "• Ran "
    command_lines = (
        [header_line[len(prefix) :]] if header_line.startswith(prefix) else [header_line]
    )
    output_lines: list[str] = []
    for raw_line in visible_lines[1:]:
        line = str(raw_line or "")
        if line.startswith("  │ "):
            command_lines.append(line[4:])
        elif line.startswith("  └ "):
            output_lines.append(line[4:])
        elif line.startswith("    "):
            output_lines.append(line[4:])
        else:
            output_lines.append(line)

    rendered_lines: list[str] = []
    for index, command_text in enumerate(command_lines):
        rendered_lines.extend(
            wrap_prefixed_text(
                command_text,
                first_prefix=prefix if index == 0 else "  │ ",
                continuation_prefix="  │ ",
                width=width,
            )
        )
    if output_lines:
        for index, output_text in enumerate(output_lines):
            rendered_lines.extend(
                wrap_prefixed_text(
                    output_text,
                    first_prefix="  └ " if index == 0 else "    ",
                    continuation_prefix="    ",
                    width=width,
                )
            )
    return [
        (line_text, plain_line_styles(entry, line_index, line_text, styles=styles))
        for line_index, line_text in enumerate(rendered_lines)
    ]


def render_tool_mcp_entry_lines(
    entry: TranscriptEntry,
    *,
    width: int,
    styles: ThemeStyles,
) -> list[tuple[str, list[tuple[int, int, RichStyle]]]]:
    visible_lines = entry.expanded_lines if entry.expanded and entry.expanded_lines else entry.lines
    if not visible_lines:
        return []
    header_line = str(visible_lines[0] or "")
    if header_line.startswith("• Calling "):
        header_word = "Calling"
        invocation = header_line[len("• Calling ") :]
    elif header_line.startswith("• Called "):
        header_word = "Called"
        invocation = header_line[len("• Called ") :]
    else:
        return [
            (str(line), plain_line_styles(entry, line_index, str(line), styles=styles))
            for line_index, line in enumerate(visible_lines)
        ]
    detail_lines = [
        str(line[4:] if str(line).startswith(("  └ ", "    ")) else line)
        for line in visible_lines[1:]
    ]
    compact_header = f"• {header_word} {invocation}".rstrip()
    rendered_lines: list[str] = []
    inline_invocation = cell_len(compact_header) <= max(1, width)
    if inline_invocation:
        rendered_lines.append(compact_header)
    else:
        rendered_lines.append(f"• {header_word}")
        rendered_lines.extend(
            wrap_prefixed_text(
                invocation,
                first_prefix="  └ ",
                continuation_prefix="    ",
                width=width,
            )
        )
    for index, detail_text in enumerate(detail_lines):
        rendered_lines.extend(
            wrap_prefixed_text(
                detail_text,
                first_prefix="  └ " if inline_invocation and index == 0 else "    ",
                continuation_prefix="    ",
                width=width,
            )
        )
    return [
        (line_text, plain_line_styles(entry, line_index, line_text, styles=styles))
        for line_index, line_text in enumerate(rendered_lines)
    ]


def render_web_search_entry_lines(
    entry: TranscriptEntry,
    *,
    width: int,
    styles: ThemeStyles,
) -> list[tuple[str, list[tuple[int, int, RichStyle]]]]:
    visible_lines = entry.expanded_lines if entry.expanded and entry.expanded_lines else entry.lines
    if not visible_lines:
        return []

    rendered_lines: list[str] = []
    for index, raw_line in enumerate(visible_lines):
        line_text = str(raw_line or "")
        if index == 0 and line_text.startswith("• "):
            rendered_lines.extend(
                wrap_prefixed_text(
                    line_text[2:],
                    first_prefix="• ",
                    continuation_prefix="  ",
                    width=width,
                )
            )
            continue
        if line_text.startswith("  └ "):
            rendered_lines.extend(
                wrap_prefixed_text(
                    line_text[4:],
                    first_prefix="  └ ",
                    continuation_prefix="    ",
                    width=width,
                )
            )
            continue
        if line_text.startswith("    "):
            rendered_lines.extend(
                wrap_prefixed_text(
                    line_text[4:],
                    first_prefix="    ",
                    continuation_prefix="    ",
                    width=width,
                )
            )
            continue
        rendered_lines.extend(
            wrap_prefixed_text(
                line_text,
                first_prefix="" if index else "• ",
                continuation_prefix="    " if index else "  ",
                width=width,
            )
        )

    return [
        (line_text, plain_line_styles(entry, line_index, line_text, styles=styles))
        for line_index, line_text in enumerate(rendered_lines)
    ]


def render_todo_list_entry_lines(
    entry: TranscriptEntry,
    *,
    width: int,
    styles: ThemeStyles,
) -> list[tuple[str, list[tuple[int, int, RichStyle]]]]:
    visible_lines = entry.expanded_lines if entry.expanded and entry.expanded_lines else entry.lines
    if not visible_lines:
        return []

    rendered_lines: list[str] = []
    for index, raw_line in enumerate(visible_lines):
        line_text = str(raw_line or "")
        if index == 0 and line_text.startswith("• "):
            rendered_lines.extend(
                wrap_prefixed_text(
                    line_text[2:],
                    first_prefix="• ",
                    continuation_prefix="  ",
                    width=width,
                )
            )
            continue
        if line_text.startswith("  └ "):
            rendered_lines.extend(
                _wrap_todo_body_line(line_text[4:], width=width, branch_prefix="  └ ")
            )
            continue
        if line_text.startswith("    "):
            rendered_lines.extend(
                _wrap_todo_body_line(line_text[4:], width=width, branch_prefix="    ")
            )
            continue
        rendered_lines.extend(
            wrap_prefixed_text(
                line_text,
                first_prefix="" if index else "• ",
                continuation_prefix="    " if index else "  ",
                width=width,
            )
        )

    return [
        (line_text, plain_line_styles(entry, line_index, line_text, styles=styles))
        for line_index, line_text in enumerate(rendered_lines)
    ]


def _wrap_todo_body_line(text: str, *, width: int, branch_prefix: str) -> list[str]:
    body_text = str(text or "")
    for marker in ("✔ ", "□ "):
        if body_text.startswith(marker):
            return wrap_prefixed_text(
                body_text[len(marker) :],
                first_prefix=f"{branch_prefix}{marker}",
                continuation_prefix=" " * (len(branch_prefix) + len(marker)),
                width=width,
            )
    continuation_prefix = " " * len(branch_prefix)
    return wrap_prefixed_text(
        body_text,
        first_prefix=branch_prefix,
        continuation_prefix=continuation_prefix,
        width=width,
    )


def render_separator_entry_lines(
    entry: TranscriptEntry,
    *,
    width: int,
    styles: ThemeStyles,
) -> list[tuple[str, list[tuple[int, int, RichStyle]]]]:
    label = str(entry.raw_content or "").strip()
    line = separator_line(width, label=label)
    return [(line, [(0, len(line), styles.separator_text_style)])]


def separator_line(width: int, *, label: str = "") -> str:
    target_width = max(16, int(width or 0))
    text = str(label or "").strip()
    if not text:
        return "─" * target_width
    prefix = "──"
    prefix_width = cell_len(prefix)
    text_width = cell_len(text)
    consumed = prefix_width + text_width
    if consumed >= target_width:
        return prefix + text
    return prefix + text + ("─" * (target_width - consumed))

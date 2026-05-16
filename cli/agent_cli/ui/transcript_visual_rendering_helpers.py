from __future__ import annotations

import re
import textwrap
from typing import TYPE_CHECKING

from rich.cells import cell_len
from rich.style import Style as RichStyle

from cli.agent_cli.ui.theme import (
    TRANSCRIPT_MESSAGE_PREFIX,
    TRANSCRIPT_USER_PREFIX,
    ThemeStyles,
)

if TYPE_CHECKING:
    from cli.agent_cli.ui.transcript_history import TranscriptEntry

_COMPLETION_STAMP_LINE_RE = re.compile(
    r"^\s*(?P<stamp>(?:🏁|[tT])\s+\d{2}:\d{2}\s+(?:(?:⌛|⌛️|⏱|⏱️)\s+)?\d+[sm]|Done\s+\d{2}:\d{2},\s+took\s+\d+[sm]|完成\d{2}:\d{2}，用时\d+[sm]|完成时间\s+\d{2}:\d{2})\s*$"
)
_VISUAL_HEADER_PREFIXES = frozenset({"$ ", "⌕ ", "◆ ", "▸ ", "□ ", "◦ ", "✗ "})
_ALL_HEADER_PREFIXES = (TRANSCRIPT_MESSAGE_PREFIX, *_VISUAL_HEADER_PREFIXES)


def normalized_completion_stamp_line(line_text: str) -> str | None:
    matched = _COMPLETION_STAMP_LINE_RE.match(str(line_text or ""))
    if not matched:
        return None
    return str(matched.group("stamp") or "").strip()


def is_completion_stamp_line(line_text: str) -> bool:
    return normalized_completion_stamp_line(line_text) is not None


def wrap_prefixed_text(
    text: str,
    *,
    first_prefix: str,
    continuation_prefix: str,
    width: int,
) -> list[str]:
    source = str(text or "")
    first_width = max(1, int(width) - cell_len(first_prefix))
    continuation_width = max(1, int(width) - cell_len(continuation_prefix))
    wrapper = textwrap.TextWrapper(
        width=first_width,
        break_long_words=True,
        break_on_hyphens=False,
        replace_whitespace=False,
        drop_whitespace=True,
    )
    wrapped = wrapper.wrap(source) or [""]
    lines = [f"{first_prefix}{wrapped[0]}"]
    if len(wrapped) == 1:
        return lines
    continuation_wrapper = textwrap.TextWrapper(
        width=continuation_width,
        break_long_words=True,
        break_on_hyphens=False,
        replace_whitespace=False,
        drop_whitespace=True,
    )
    for chunk in wrapped[1:]:
        continuation_lines = continuation_wrapper.wrap(chunk) or [""]
        lines.extend(f"{continuation_prefix}{line}" for line in continuation_lines)
    return lines


def prefix_rendered_lines(
    lines: list[tuple[str, list[tuple[int, int, RichStyle]]]],
    *,
    first_prefix: str,
    continuation_prefix: str,
    prefix_style: RichStyle,
) -> list[tuple[str, list[tuple[int, int, RichStyle]]]]:
    prefixed: list[tuple[str, list[tuple[int, int, RichStyle]]]] = []
    for index, (line_text, spans) in enumerate(lines):
        prefix = first_prefix if index == 0 else continuation_prefix
        joined = f"{prefix}{line_text}"
        joined_spans: list[tuple[int, int, RichStyle]] = []
        if prefix:
            joined_spans.append((0, len(prefix), prefix_style))
        shift = len(prefix)
        joined_spans.extend((start + shift, end + shift, style) for start, end, style in spans)
        prefixed.append((joined, joined_spans))
    return prefixed


def visual_header_prefix(entry: TranscriptEntry) -> str:
    if entry.kind == "activity":
        if str(entry.status or "").strip().lower() in {"error", "failed"}:
            return "✗ "
        activity_key = str(entry.activity_key or "").strip()
        if (
            entry.render_mode == "tool_command"
            or activity_key.startswith("command:")
            or ":command:" in activity_key
        ):
            return "$ "
        if entry.render_mode == "web_search" or entry.layer == "web":
            return "⌕ "
        if entry.render_mode == "todo_list":
            return "□ "
        if entry.render_mode == "prompt_tool_group":
            return "▸ "
        if entry.layer == "tool":
            return "◆ "
        if entry.layer == "commentary":
            return "◦ "
        return TRANSCRIPT_MESSAGE_PREFIX
    if entry.kind == "reasoning" or entry.layer in {"commentary", "reasoning"}:
        return "◦ "
    return TRANSCRIPT_MESSAGE_PREFIX


def apply_visual_header_prefix(
    entry: TranscriptEntry,
    line_text: str,
    *,
    line_index: int,
) -> str:
    if line_index != 0 or not line_text or is_completion_stamp_line(line_text):
        return line_text
    prefix = visual_header_prefix(entry)
    if not prefix or line_text.startswith(prefix):
        return line_text
    if line_text.startswith(TRANSCRIPT_MESSAGE_PREFIX):
        return f"{prefix}{line_text[len(TRANSCRIPT_MESSAGE_PREFIX):]}"
    if entry.kind == "activity" and not any(
        line_text.startswith(item) for item in _VISUAL_HEADER_PREFIXES
    ):
        return f"{prefix}{line_text}"
    return line_text


def prefixed_visual_lines(entry: TranscriptEntry, lines: list[str]) -> list[str]:
    return [
        apply_visual_header_prefix(entry, line_text, line_index=line_index)
        for line_index, line_text in enumerate(lines)
    ]


def _header_prefix_for_line(line_text: str) -> str:
    for prefix in _ALL_HEADER_PREFIXES:
        if line_text.startswith(prefix):
            return prefix
    return ""


def markdown_base_style(entry: TranscriptEntry, *, styles: ThemeStyles) -> RichStyle:
    if entry.status == "error":
        return styles.error_text_style
    if entry.kind == "reasoning":
        return styles.reasoning_text_style
    if entry.layer == "commentary":
        return styles.commentary_text_style
    return styles.final_text_style


def markdown_prefix_style(entry: TranscriptEntry, *, styles: ThemeStyles) -> RichStyle:
    if entry.status == "error":
        return styles.error_text_style
    if entry.kind == "reasoning":
        return styles.reasoning_prefix_style
    if entry.layer == "commentary":
        return styles.commentary_prefix_style
    return styles.final_prefix_style


def plain_line_styles(
    entry: TranscriptEntry,
    line_index: int,
    line_text: str,
    *,
    styles: ThemeStyles,
) -> list[tuple[int, int, RichStyle]]:
    if not line_text:
        return []
    if entry.kind == "system":
        return [(0, len(line_text), styles.system_text_style)]
    if entry.kind == "user":
        spans = [(0, len(line_text), styles.user_text_style)]
        if line_text.startswith(TRANSCRIPT_USER_PREFIX):
            spans.append((0, len(TRANSCRIPT_USER_PREFIX), styles.user_prefix_style))
        elif line_text.startswith("  [Image #"):
            spans.append((2, len(line_text), styles.user_image_style))
        return spans
    if entry.kind == "assistant":
        if is_completion_stamp_line(line_text):
            return [(0, len(line_text), styles.completion_time_style)]
        if entry.status == "error":
            base_style = styles.error_text_style
            prefix_style = styles.error_text_style
        else:
            base_style = (
                styles.commentary_text_style
                if entry.layer == "commentary"
                else styles.final_text_style
            )
            prefix_style = (
                styles.commentary_prefix_style
                if entry.layer == "commentary"
                else styles.final_prefix_style
            )
        spans = [(0, len(line_text), base_style)]
        header_prefix = _header_prefix_for_line(line_text)
        if header_prefix:
            spans.append((0, len(header_prefix), prefix_style))
        return spans
    if entry.kind == "separator":
        return [(0, len(line_text), styles.separator_text_style)]
    if entry.kind != "activity":
        return [(0, len(line_text), styles.activity_text_style)]
    if line_text.startswith("✗ "):
        return [(0, len(line_text), styles.error_text_style), (0, 2, styles.error_text_style)]
    if line_text.startswith("  └ "):
        return [
            (
                0,
                len(line_text),
                (
                    styles.error_detail_style
                    if entry.status == "error"
                    else styles.activity_detail_style
                ),
            ),
            (2, 5, styles.tree_prefix_style),
        ]
    if line_text.startswith("  │ "):
        return [
            (
                0,
                len(line_text),
                (
                    styles.error_detail_style
                    if entry.status == "error"
                    else styles.activity_detail_style
                ),
            ),
            (2, 5, styles.tree_prefix_style),
        ]
    if line_text.startswith("    "):
        return [
            (
                0,
                len(line_text),
                (
                    styles.error_detail_style
                    if entry.status == "error"
                    else styles.activity_detail_style
                ),
            )
        ]
    base_style = activity_header_style(entry, line_index, styles=styles)
    spans = [(0, len(line_text), base_style)]
    header_prefix = _header_prefix_for_line(line_text)
    if header_prefix:
        spans.append((0, len(header_prefix), styles.activity_prefix_style))
    return spans


def activity_header_style(
    entry: TranscriptEntry, line_index: int, *, styles: ThemeStyles
) -> RichStyle:
    if entry.status == "error":
        return styles.error_text_style
    if entry.layer == "web":
        return styles.web_text_style
    if entry.layer == "commentary":
        return styles.commentary_text_style
    if entry.layer == "tool":
        return styles.activity_text_style
    if line_index > 0:
        return styles.activity_detail_style
    return styles.activity_text_style


def markdown_line_styles(
    line_text: str,
    spans,
    base_style: RichStyle,
    *,
    styles: ThemeStyles,
    merge_base_semantics: bool = False,
) -> list[tuple[int, int, RichStyle]]:
    if not line_text:
        return []
    styled_spans: list[tuple[int, int, RichStyle]] = [(0, len(line_text), base_style)]
    for span in spans:
        style = markdown_semantic_style(span.kind, styles=styles)
        if style is None:
            continue
        start = max(0, min(span.start, len(line_text)))
        end = max(0, min(span.end, len(line_text)))
        if end > start:
            styled_spans.append(
                (start, end, (base_style + style) if merge_base_semantics else style)
            )
    return styled_spans


def markdown_semantic_style(kind: str, *, styles: ThemeStyles) -> RichStyle | None:
    if kind == "heading1":
        return styles.markdown_h1_style
    if kind == "heading2":
        return styles.markdown_h2_style
    if kind == "heading3":
        return styles.markdown_h3_style
    if kind == "heading4":
        return styles.markdown_h4_style
    if kind == "heading5":
        return styles.markdown_h5_style
    if kind == "heading6":
        return styles.markdown_h6_style
    if kind == "emphasis":
        return styles.markdown_emphasis_style
    if kind == "strong":
        return styles.markdown_strong_style
    if kind == "code":
        return styles.markdown_code_style
    if kind == "link":
        return styles.markdown_link_style
    if kind == "blockquote":
        return styles.markdown_blockquote_style
    if kind == "ordered_list_marker":
        return styles.markdown_ordered_list_marker_style
    if kind == "syntax_comment":
        return styles.markdown_syntax_comment_style
    if kind == "syntax_keyword":
        return styles.markdown_syntax_keyword_style
    if kind == "syntax_string":
        return styles.markdown_syntax_string_style
    if kind == "syntax_number":
        return styles.markdown_syntax_number_style
    if kind == "syntax_operator":
        return styles.markdown_syntax_operator_style
    if kind == "syntax_name":
        return styles.markdown_syntax_name_style
    if kind == "syntax_builtin":
        return styles.markdown_syntax_builtin_style
    return None

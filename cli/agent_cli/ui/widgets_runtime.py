from __future__ import annotations

from rich.segment import Segment
from rich.style import Style as RichStyle


def serialize_rich_style(style: RichStyle | None) -> dict[str, object] | None:
    if style is None:
        return None
    if not isinstance(style, RichStyle):
        return {
            "repr": str(style),
            "type": type(style).__name__,
        }
    return {
        "repr": str(style),
        "color": str(style.color) if style.color is not None else None,
        "bgcolor": str(style.bgcolor) if style.bgcolor is not None else None,
        "bold": bool(style.bold) if style.bold is not None else None,
        "dim": bool(style.dim) if style.dim is not None else None,
        "italic": bool(style.italic) if style.italic is not None else None,
        "underline": bool(style.underline) if style.underline is not None else None,
    }


def quote_line_debug_entries(
    *,
    lines: list[str],
    line_styles: list[list[tuple[int, int, RichStyle]]],
    serialize_style_fn,
) -> list[dict[str, object]]:
    quote_lines: list[dict[str, object]] = []
    for index, line in enumerate(lines):
        line_text = str(line)
        if ">" not in line_text:
            continue
        spans = line_styles[index] if index < len(line_styles) else []
        quote_lines.append(
            {
                "line_index": int(index),
                "text": line_text,
                "spans": [
                    {
                        "start": int(start),
                        "end": int(end),
                        "style": serialize_style_fn(style),
                    }
                    for start, end, style in spans
                ],
            }
        )
    return quote_lines


def render_line_debug_payload(
    *,
    y: int,
    absolute_y: int,
    line_index: int,
    section_offset: int,
    document_line: str,
    strip_text: str,
    strip_segments: list[Segment],
    probe_line_style: RichStyle | None,
    probe_line_spans,
    probe_render_segments: list[Segment],
    show_cursor: bool,
    highlight_cursor_line: bool,
    selection_start: tuple[int, int],
    selection_end: tuple[int, int],
    has_cursor: bool,
    draw_cursor: bool,
    language: object,
    theme: object,
    highlight_query: bool,
    highlight_ranges: list[object],
    rich_style: RichStyle | None,
    visual_style: RichStyle | None,
    serialize_style_fn,
) -> dict[str, object]:
    return {
        "y": int(y),
        "absolute_y": absolute_y,
        "line_index": int(line_index),
        "section_offset": int(section_offset),
        "document_line": document_line,
        "strip_text": strip_text,
        "strip_segments": [
            {
                "text": segment.text,
                "style": serialize_style_fn(segment.style),
            }
            for segment in strip_segments
        ],
        "probe_line_style": serialize_style_fn(probe_line_style),
        "probe_line_spans": [
            {
                "start": int(span.start),
                "end": int(span.end),
                "style": serialize_style_fn(span.style),
            }
            for span in probe_line_spans
        ],
        "probe_render_segments": [
            {
                "text": segment.text,
                "style": serialize_style_fn(segment.style),
            }
            for segment in probe_render_segments
        ],
        "show_cursor": bool(show_cursor),
        "highlight_cursor_line": bool(highlight_cursor_line),
        "selection_start": list(selection_start),
        "selection_end": list(selection_end),
        "has_cursor": bool(has_cursor),
        "draw_cursor": bool(draw_cursor),
        "language": str(language),
        "theme": str(theme),
        "highlight_query": bool(highlight_query),
        "highlight_ranges": list(highlight_ranges),
        "rich_style": serialize_style_fn(rich_style),
        "visual_style": serialize_style_fn(visual_style),
    }


def popup_visible_line_count(*, item_count: int, max_visible_items: int) -> int:
    if item_count <= 0:
        return 0
    return min(item_count, max_visible_items)


def popup_state(
    *,
    items: list[dict[str, str]],
    selected_index: int,
    query: str,
    mode: str,
    current_scroll_top: int,
    max_visible_items: int,
    popup_scroll_top_fn,
) -> dict[str, object]:
    normalized_items = list(items)
    normalized_selected_index = max(0, min(selected_index, len(normalized_items) - 1)) if normalized_items else 0
    visible = popup_visible_line_count(item_count=len(normalized_items), max_visible_items=max_visible_items)
    return {
        "items": normalized_items,
        "selected_index": normalized_selected_index,
        "query": str(query or "").strip().lower(),
        "mode": str(mode or "slash").strip().lower() or "slash",
        "scroll_top": popup_scroll_top_fn(
            item_count=len(normalized_items),
            selected_index=normalized_selected_index,
            visible=visible,
            current_scroll_top=current_scroll_top,
        ),
        "visible": visible,
    }


def normalized_segments(*, styled_strip, base_style: RichStyle | None) -> list[Segment]:
    return [
        Segment(text, style if style is not None else base_style, control)
        for text, style, control in styled_strip._segments
    ]

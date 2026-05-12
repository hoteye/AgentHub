from __future__ import annotations

from typing import Any

from rich.style import Style as RichStyle
from rich.text import Text
from textual.strip import Strip
from textual.widgets._text_area import (
    _utf8_encode,
    build_byte_to_codepoint_dict,
    expand_text_tabs_from_widths,
)

from cli.agent_cli.ui import widgets_runtime


def render_transcript_line(area: Any, y: int) -> Strip:
    theme = area._theme
    if theme:
        theme.apply_css(area)

    wrapped_document = area.wrapped_document
    scroll_x, scroll_y = area.scroll_offset
    y_offset = y + scroll_y
    if y_offset >= wrapped_document.height:
        return area._blank_transcript_strip(theme)

    try:
        line_info = wrapped_document._offset_to_line_info[y_offset]
    except IndexError:
        line_info = None
    if line_info is None:
        return area._blank_transcript_strip(theme)

    line_index, section_offset = line_info
    line = area.get_line(line_index)
    line_character_count = len(line)
    line.tab_size = area.indent_width
    line.set_length(line_character_count + (1 if area.show_cursor else 0))
    virtual_width, _virtual_height = area.virtual_size

    selection = area.selection
    start, end = selection
    cursor_row, cursor_column = end

    selection_top, selection_bottom = sorted(selection)
    selection_top_row, selection_top_column = selection_top
    selection_bottom_row, selection_bottom_column = selection_bottom

    cursor_line_style = theme.cursor_line_style if (theme and area.highlight_cursor_line) else None
    if cursor_line_style and cursor_row == line_index:
        line.stylize(cursor_line_style)

    if start != end and selection_top_row <= line_index <= selection_bottom_row:
        line = _apply_selection_style(
            line=line,
            theme=theme,
            start=start,
            end=end,
            line_index=line_index,
            line_character_count=line_character_count,
            selection_top_row=selection_top_row,
            selection_top_column=selection_top_column,
            selection_bottom_row=selection_bottom_row,
            selection_bottom_column=selection_bottom_column,
        )

    _apply_syntax_highlights(area=area, line=line, line_index=line_index, theme=theme)

    matching_bracket = area._matching_bracket_location
    match_cursor_bracket = area.match_cursor_bracket
    draw_matched_brackets = match_cursor_bracket and matching_bracket is not None and start == end

    if cursor_row == line_index:
        draw_cursor = (area.has_focus and not area.cursor_blink) or (area.cursor_blink and area._cursor_visible)
        if draw_matched_brackets:
            matching_bracket_style = theme.bracket_matching_style if theme else None
            if matching_bracket_style:
                line.stylize(matching_bracket_style, cursor_column, cursor_column + 1)
        if draw_cursor and area.show_cursor:
            cursor_style = theme.cursor_style if theme else None
            if cursor_style:
                line.stylize(cursor_style, cursor_column, cursor_column + 1)

    if draw_matched_brackets:
        assert matching_bracket is not None
        bracket_match_row, bracket_match_column = matching_bracket
        if theme and bracket_match_row == line_index:
            matching_bracket_style = theme.bracket_matching_style
            if matching_bracket_style:
                line.stylize(matching_bracket_style, bracket_match_column, bracket_match_column + 1)

    gutter_width = area.gutter_width
    gutter = _build_gutter(
        area=area,
        theme=theme,
        line_index=line_index,
        section_offset=section_offset,
        cursor_row=cursor_row,
        cursor_line_style=cursor_line_style,
        gutter_width=gutter_width,
    )

    line = _line_section_with_expanded_tabs(
        line=line,
        wrapped_document=wrapped_document,
        line_index=line_index,
        section_offset=section_offset,
        indent_width=area.indent_width,
    )

    target_width = _target_width(
        area=area,
        wrapped_document=wrapped_document,
        virtual_width=virtual_width,
    )
    console = area.app.console
    gutter_segments = console.render(gutter)
    text_segments = list(console.render(line, console.options.update_width(target_width)))

    gutter_strip = Strip(gutter_segments, cell_length=gutter_width)
    text_strip = Strip(text_segments)
    if not area.soft_wrap:
        text_strip = text_strip.crop(scroll_x, scroll_x + virtual_width)

    line_style = cursor_line_style if (cursor_row == line_index and cursor_line_style) else (theme.base_style if theme else None)
    text_strip = text_strip.extend_cell_length(target_width, line_style)
    strip = Strip.join([gutter_strip, text_strip]).simplify()

    base_style = theme.base_style if theme and theme.base_style is not None else area.rich_style
    styled_strip = strip.apply_style(base_style)
    normalized_segments = widgets_runtime.normalized_segments(
        styled_strip=styled_strip,
        base_style=base_style,
    )
    return Strip(normalized_segments, styled_strip.cell_length).simplify()


def _apply_selection_style(
    *,
    line: Text,
    theme: Any,
    start: tuple[int, int],
    end: tuple[int, int],
    line_index: int,
    line_character_count: int,
    selection_top_row: int,
    selection_top_column: int,
    selection_bottom_row: int,
    selection_bottom_column: int,
) -> Text:
    selection_style = theme.selection_style if theme else None
    cursor_row, _ = end
    if not selection_style:
        return line
    if line_character_count == 0 and line_index != cursor_row:
        return Text("▌", end="", style=RichStyle(color=selection_style.bgcolor))
    if line_index == selection_top_row == selection_bottom_row:
        line.stylize(selection_style, start=selection_top_column, end=selection_bottom_column)
        return line
    if line_index == selection_top_row:
        line.stylize(selection_style, start=selection_top_column, end=line_character_count)
        return line
    if line_index == selection_bottom_row:
        line.stylize(selection_style, end=selection_bottom_column)
        return line
    line.stylize(selection_style, end=line_character_count)
    return line


def _apply_syntax_highlights(*, area: Any, line: Text, line_index: int, theme: Any) -> None:
    highlights = area._highlights
    if not (highlights and theme):
        return
    line_bytes = _utf8_encode(line.plain)
    byte_to_codepoint = build_byte_to_codepoint_dict(line_bytes)
    get_highlight_from_theme = theme.syntax_styles.get
    line_highlights = highlights[line_index]
    for highlight_start, highlight_end, highlight_name in line_highlights:
        node_style = get_highlight_from_theme(highlight_name)
        if node_style is not None:
            line.stylize(
                node_style,
                byte_to_codepoint.get(highlight_start, 0),
                byte_to_codepoint.get(highlight_end) if highlight_end else None,
            )


def _build_gutter(
    *,
    area: Any,
    theme: Any,
    line_index: int,
    section_offset: int,
    cursor_row: int,
    cursor_line_style: RichStyle | None,
    gutter_width: int,
) -> Text:
    gutter = Text("", end="")
    if not area.show_line_numbers:
        return gutter
    gutter_style = theme.cursor_line_gutter_style if (cursor_row == line_index and cursor_line_style) else theme.gutter_style
    gutter_width_no_margin = gutter_width - 2
    gutter_content = str(line_index + area.line_number_start) if section_offset == 0 else ""
    return Text(f"{gutter_content:>{gutter_width_no_margin}}  ", style=gutter_style or "", end="")


def _line_section_with_expanded_tabs(
    *,
    line: Text,
    wrapped_document: Any,
    line_index: int,
    section_offset: int,
    indent_width: int,
) -> Text:
    wrap_offsets = wrapped_document.get_offsets(line_index)
    if wrap_offsets:
        sections = line.divide(wrap_offsets)
        line = sections[section_offset]
        line_tab_widths = wrapped_document.get_tab_widths(line_index)
        line.end = ""
        tabs_before = 0
        for section_index in range(section_offset):
            tabs_before += sections[section_index].plain.count("\t")
        tabs_within = line.plain.count("\t")
        section_tab_widths = line_tab_widths[tabs_before : tabs_before + tabs_within]
        return expand_text_tabs_from_widths(line, section_tab_widths)
    line.expand_tabs(indent_width)
    return line


def _target_width(*, area: Any, wrapped_document: Any, virtual_width: int) -> int:
    base_width = area.scrollable_content_region.size.width if area.soft_wrap else max(virtual_width, area.region.size.width)
    if area.soft_wrap:
        wrapped_width = 0
        try:
            wrapped_width = int(getattr(wrapped_document, "_width", 0) or 0)
        except Exception:
            wrapped_width = 0
        return wrapped_width if wrapped_width > 0 else (base_width - area.gutter_width)
    return base_width - area.gutter_width

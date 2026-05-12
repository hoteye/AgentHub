from __future__ import annotations

from typing import Pattern

from rich.cells import cell_len

from cli.agent_cli.ui import unicode_word_break_runtime


def line_start(text: str, pos: int) -> int:
    return text.rfind("\n", 0, pos) + 1


def line_end(text: str, pos: int) -> int:
    newline_at = text.find("\n", pos)
    return len(text) if newline_at == -1 else newline_at


def column(text: str, pos: int) -> int:
    return pos - line_start(text, pos)


def visual_row_ranges(text: str, content_width: int) -> list[tuple[int, int]]:
    rows: list[tuple[int, int]] = []
    line_start_pos = 0
    while True:
        line_end_pos = text.find("\n", line_start_pos)
        if line_end_pos == -1:
            line_end_pos = len(text)
        if line_end_pos == line_start_pos:
            rows.append((line_start_pos, line_start_pos))
        else:
            row_start = line_start_pos
            row_width = 0
            pos = line_start_pos
            while pos < line_end_pos:
                char_width = max(0, cell_len(text[pos]))
                if pos > row_start and row_width + char_width > content_width:
                    rows.append((row_start, pos))
                    row_start = pos
                    row_width = 0
                row_width += char_width
                pos += 1
            rows.append((row_start, line_end_pos))
        if line_end_pos >= len(text):
            break
        line_start_pos = line_end_pos + 1
    return rows or [(0, 0)]


def row_state(rows: list[tuple[int, int]], cursor_pos: int) -> tuple[list[tuple[int, int]], int]:
    for index, row in enumerate(rows):
        start, end = row
        if cursor_pos == start:
            return rows, index
    for index, row in enumerate(rows):
        start, end = row
        if start < cursor_pos < end:
            return rows, index
    for index, row in enumerate(rows):
        _, end = row
        if cursor_pos == end:
            return rows, index
    if cursor_pos == rows[-1][1]:
        return rows, len(rows) - 1
    return rows, max(0, len(rows) - 1)


def row_display_column(text: str, row: tuple[int, int], pos: int) -> int:
    start, end = row
    clamped = max(start, min(pos, end))
    return cell_len(text[start:clamped])


def position_in_row_for_column(text: str, row: tuple[int, int], target_column: int) -> int:
    start, end = row
    target = max(0, target_column)
    best_pos = start
    best_distance = abs(target)
    current_column = 0
    pos = start
    while pos < end:
        char_width = max(0, cell_len(text[pos]))
        next_pos = pos + 1
        next_column = current_column + char_width
        next_distance = abs(next_column - target)
        if next_distance <= best_distance:
            best_pos = next_pos
            best_distance = next_distance
        pos = next_pos
        current_column = next_column
    return best_pos


def word_like_range_at(text: str, pos: int, *, is_word_separator_fn) -> tuple[int, int]:
    if not text:
        return (0, 0)
    index = max(0, min(pos, len(text) - 1))
    char = text[index]
    if char.isspace():
        start = index
        end = index + 1
        while start > 0 and text[start - 1].isspace():
            start -= 1
        while end < len(text) and text[end].isspace():
            end += 1
        return (start, end)
    unicode_range = unicode_word_break_runtime.word_range_at(text, index)
    if unicode_range is not None:
        return unicode_range
    is_separator = is_word_separator_fn(char)
    start = index
    end = index + 1
    while start > 0:
        previous = text[start - 1]
        if previous.isspace() or is_word_separator_fn(previous) != is_separator:
            break
        start -= 1
    while end < len(text):
        current = text[end]
        if current.isspace() or is_word_separator_fn(current) != is_separator:
            break
        end += 1
    return (start, end)


def atomic_ranges(text: str, patterns: tuple[Pattern[str], ...]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            start, end = match.span()
            if start != end:
                ranges.append((start, end))
    ranges.sort()
    return ranges


def atomic_range_at(ranges: list[tuple[int, int]], pos: int, *, text_length: int) -> tuple[int, int] | None:
    probe = max(0, min(pos, text_length))
    for start, end in ranges:
        if start <= probe < end:
            return (start, end)
        if probe == end and probe > start:
            return (start, end)
    return None


def expand_bounds_to_atomic_tokens(
    ranges: list[tuple[int, int]],
    start: int,
    end: int,
) -> tuple[int, int]:
    expanded_start = start
    expanded_end = end
    changed = True
    while changed:
        changed = False
        for token_start, token_end in ranges:
            overlaps = token_start < expanded_end and token_end > expanded_start
            touches_inside = expanded_start == expanded_end and token_start <= expanded_start < token_end
            if overlaps or touches_inside:
                next_start = min(expanded_start, token_start)
                next_end = max(expanded_end, token_end)
                if next_start != expanded_start or next_end != expanded_end:
                    expanded_start = next_start
                    expanded_end = next_end
                    changed = True
    return (expanded_start, expanded_end)


def beginning_of_previous_word(text: str, cursor_pos: int, *, is_word_separator_fn) -> int:
    prefix = text[:cursor_pos]
    first_non_ws_index: int | None = None
    first_non_ws_char = ""
    for index in range(len(prefix) - 1, -1, -1):
        char = prefix[index]
        if not char.isspace():
            first_non_ws_index = index
            first_non_ws_char = char
            break
    if first_non_ws_index is None:
        return 0
    unicode_range = unicode_word_break_runtime.word_range_at(text, first_non_ws_index)
    if unicode_range is not None:
        return unicode_range[0]
    is_separator_value = is_word_separator_fn(first_non_ws_char)
    start = first_non_ws_index
    for index in range(first_non_ws_index - 1, -1, -1):
        char = prefix[index]
        if char.isspace() or is_word_separator_fn(char) != is_separator_value:
            return index + 1
        start = index
    return start


def end_of_next_word(text: str, cursor_pos: int, *, is_word_separator_fn) -> int:
    suffix = text[cursor_pos:]
    first_non_ws_offset: int | None = None
    for index, char in enumerate(suffix):
        if not char.isspace():
            first_non_ws_offset = index
            break
    if first_non_ws_offset is None:
        return len(text)
    word_start = cursor_pos + first_non_ws_offset
    unicode_range = unicode_word_break_runtime.word_range_at(text, word_start)
    if unicode_range is not None:
        return unicode_range[1]
    first_char = text[word_start]
    is_separator_value = is_word_separator_fn(first_char)
    for index in range(word_start + 1, len(text)):
        char = text[index]
        if char.isspace() or is_word_separator_fn(char) != is_separator_value:
            return index
    return len(text)

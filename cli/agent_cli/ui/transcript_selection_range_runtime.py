from __future__ import annotations

from time import monotonic
from typing import Any

from cli.agent_cli.ui import unicode_word_break_runtime


def register_click_streak(area: Any, x: int, y: int) -> int:
    now = monotonic()
    cell = (int(x), int(y))
    if area._last_click_cell == cell and (now - area._last_click_at) <= area.MULTI_CLICK_TIMEOUT_SECONDS:
        area._click_streak += 1
    else:
        area._click_streak = 1
    area._last_click_at = now
    area._last_click_cell = cell
    return area._click_streak


def register_right_click_streak(area: Any, x: int, y: int) -> int:
    now = monotonic()
    cell = (int(x), int(y))
    if (
        area._last_right_click_cell == cell
        and (now - area._last_right_click_at) <= area.MULTI_CLICK_TIMEOUT_SECONDS
    ):
        area._right_click_streak += 1
    else:
        area._right_click_streak = 1
    area._last_right_click_at = now
    area._last_right_click_cell = cell
    return area._right_click_streak


def select_word_at(area: Any, row: int, column: int) -> None:
    try:
        line = area.document[row]
    except IndexError:
        return
    if not line:
        area.selection = area.selection.cursor((row, 0))
        return
    probe = max(0, min(column, len(line) - 1))
    if column == len(line) and column > 0:
        probe = column - 1
    char = line[probe]
    if char.isspace():
        start = probe
        end = probe + 1
        while start > 0 and line[start - 1].isspace():
            start -= 1
        while end < len(line) and line[end].isspace():
            end += 1
        area.selection = area.selection.__class__((row, start), (row, end))
        return
    unicode_range = unicode_word_break_runtime.word_range_at(line, probe)
    if unicode_range is not None:
        start, end = unicode_range
        area.selection = area.selection.__class__((row, start), (row, end))
        return
    is_separator = area._is_word_separator(char)
    start = probe
    end = probe + 1
    while start > 0:
        previous = line[start - 1]
        if previous.isspace() or area._is_word_separator(previous) != is_separator:
            break
        start -= 1
    while end < len(line):
        current = line[end]
        if current.isspace() or area._is_word_separator(current) != is_separator:
            break
        end += 1
    area.selection = area.selection.__class__((row, start), (row, end))

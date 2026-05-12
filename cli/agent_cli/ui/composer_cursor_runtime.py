from __future__ import annotations

from time import monotonic
from typing import Any

from rich.cells import cell_len


def on_mouse_down(composer: Any, event: Any) -> None:
    if event.button == 1:
        if hasattr(event, "stop"):
            event.stop()
        if hasattr(event, "prevent_default"):
            event.prevent_default()
        composer.focus()
        x, y = event_visual_point(composer, event)
        pos = move_cursor_to_visual_point(composer, x, y, sync=False, extend=False)
        click_streak = register_click_streak(composer, x, y)
        if click_streak == 2:
            select_word_at(composer, pos)
            composer._drag_anchor_pos = composer._selection_anchor
            composer._is_drag_selecting = True
            composer._preferred_column = None
            composer._sync()
            return
        if click_streak >= 3:
            select_line_at(composer, pos)
            composer._drag_anchor_pos = composer._selection_anchor
            composer._is_drag_selecting = True
            composer._preferred_column = None
            composer._sync()
            return
        composer._drag_anchor_pos = pos
        composer._is_drag_selecting = True
        composer._selection_anchor = pos
        composer._cursor_pos = pos
        composer._preferred_column = None
        composer._sync()
        return
    if event.button != 3:
        return
    composer.focus()
    if composer.has_selection:
        if hasattr(event, "stop"):
            event.stop()
        if hasattr(event, "prevent_default"):
            event.prevent_default()
        composer._arm_paste_suppression()
        composer.copy_selection_to_clipboard()
        composer.clear_selection()
        composer._preferred_column = None
        composer._sync()
        return


def on_mouse_move(composer: Any, event: Any) -> None:
    if not composer._is_drag_selecting:
        return
    if hasattr(event, "stop"):
        event.stop()
    if hasattr(event, "prevent_default"):
        event.prevent_default()
    move_cursor_to_mouse_event(composer, event, extend=True)
    composer._preferred_column = None
    composer._sync()


def on_mouse_up(composer: Any, event: Any) -> None:
    if event.button == 3:
        return
    if event.button != 1:
        return
    if hasattr(event, "stop"):
        event.stop()
    if hasattr(event, "prevent_default"):
        event.prevent_default()
    composer._is_drag_selecting = False
    composer._drag_anchor_pos = None
    composer.copy_selection_to_clipboard()


def event_visual_point(composer: Any, event: Any) -> tuple[int, int]:
    try:
        offset = event.get_content_offset_capture(composer)
        x = int(getattr(offset, "x", 0))
        y = int(getattr(offset, "y", 0))
    except Exception:
        x = int(getattr(event, "x", 0))
        y = int(getattr(event, "y", 0))
    return x, y


def move_cursor_to_mouse_event(composer: Any, event: Any, *, extend: bool = False) -> int:
    x, y = event_visual_point(composer, event)
    return move_cursor_to_visual_point(composer, x, y, sync=False, extend=extend)


def move_cursor_to_visual_point(
    composer: Any,
    x: int,
    y: int,
    *,
    sync: bool = True,
    extend: bool = False,
) -> int:
    total_width = composer._navigation_total_width()
    rows = composer._visual_row_ranges(total_width)
    row_index = max(0, min(int(y), len(rows) - 1))
    prefix_width = cell_len(composer._prompt_prefix(total_width))
    target_column = max(0, int(x) - prefix_width)
    new_pos = composer._position_in_row_for_column(rows[row_index], target_column)
    composer._set_cursor_position(new_pos, extend=extend)
    if sync:
        composer._sync()
    return new_pos


def register_click_streak(composer: Any, x: int, y: int) -> int:
    now = monotonic()
    cell = (int(x), int(y))
    if (
        composer._last_click_cell == cell
        and (now - composer._last_click_at) <= composer.MULTI_CLICK_TIMEOUT_SECONDS
    ):
        composer._click_streak += 1
    else:
        composer._click_streak = 1
    composer._last_click_at = now
    composer._last_click_cell = cell
    return composer._click_streak


def select_range(composer: Any, start: int, end: int) -> None:
    normalized_start = max(0, min(start, len(composer._text)))
    normalized_end = max(0, min(end, len(composer._text)))
    composer._selection_anchor = normalized_start
    composer._cursor_pos = normalized_end


def select_word_at(composer: Any, pos: int) -> None:
    atomic = composer._atomic_range_at(pos)
    if atomic is not None:
        select_range(composer, *atomic)
        return
    if not composer._text:
        select_range(composer, 0, 0)
        return
    probe = max(0, min(pos, len(composer._text) - 1))
    if pos == len(composer._text) and pos > 0:
        probe = pos - 1
    start, end = composer._word_like_range_at(probe)
    select_range(composer, start, end)


def select_line_at(composer: Any, pos: int) -> None:
    start = composer._line_start(pos)
    end = composer._line_end(pos)
    select_range(composer, start, end)

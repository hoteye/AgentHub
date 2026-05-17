from __future__ import annotations

from rich.cells import cell_len

from . import composer_edit_history_runtime, composer_editing_model_runtime

ComposerSnapshot = composer_edit_history_runtime.ComposerSnapshot
apply_snapshot = composer_edit_history_runtime.apply_snapshot
push_undo_snapshot = composer_edit_history_runtime.push_undo_snapshot
redo = composer_edit_history_runtime.redo
snapshot = composer_edit_history_runtime.snapshot
undo = composer_edit_history_runtime.undo


def clear_text(composer) -> None:
    composer._clear_paste_burst_state()
    composer._push_undo_snapshot()
    composer._text = ""
    composer._cursor_pos = 0
    composer._selection_anchor = None
    composer._preferred_column = None
    composer._sync()


def set_text(composer, text: str) -> None:
    composer._clear_paste_burst_state()
    composer._text = text
    composer._cursor_pos = len(text)
    composer._selection_anchor = None
    composer._preferred_column = None
    composer._sync()


def insert_text(composer, text: str) -> None:
    composer._replace_selection_or_insert(text)


def backspace(composer) -> None:
    if composer.has_selection:
        composer.delete_selection()
        return
    if composer._cursor_pos <= 0:
        return
    atomic = composer._atomic_range_at(composer._cursor_pos - 1)
    if atomic is not None:
        composer._replace_range(atomic[0], atomic[1], "")
        return
    composer._push_undo_snapshot()
    composer._text = (
        composer._text[: composer._cursor_pos - 1] + composer._text[composer._cursor_pos :]
    )
    composer._cursor_pos -= 1
    composer._selection_anchor = None
    composer._preferred_column = None
    composer._sync()


def delete_forward(composer) -> None:
    if composer.has_selection:
        composer.delete_selection()
        return
    if composer._cursor_pos >= len(composer._text):
        return
    atomic = composer._atomic_range_at(composer._cursor_pos)
    if atomic is not None:
        composer._replace_range(atomic[0], atomic[1], "")
        return
    composer._push_undo_snapshot()
    composer._text = (
        composer._text[: composer._cursor_pos] + composer._text[composer._cursor_pos + 1 :]
    )
    composer._selection_anchor = None
    composer._preferred_column = None
    composer._sync()


def move_cursor_left(composer, *, extend: bool = False) -> None:
    if composer._cursor_pos <= 0:
        return
    composer._set_cursor_position(composer._cursor_pos - 1, extend=extend)
    composer._preferred_column = None
    composer._sync()


def move_cursor_right(composer, *, extend: bool = False) -> None:
    if composer._cursor_pos >= len(composer._text):
        return
    composer._set_cursor_position(composer._cursor_pos + 1, extend=extend)
    composer._preferred_column = None
    composer._sync()


def move_cursor_word_left(composer, *, extend: bool = False) -> None:
    composer._set_cursor_position(composer._beginning_of_previous_word(), extend=extend)
    composer._preferred_column = None
    composer._sync()


def move_cursor_word_right(composer, *, extend: bool = False) -> None:
    composer._set_cursor_position(composer._end_of_next_word(), extend=extend)
    composer._preferred_column = None
    composer._sync()


def move_cursor_logical_line_end(
    composer,
    *,
    extend: bool = False,
    move_to_next_line_when_at_end: bool = False,
) -> None:
    target_pos = composer._line_end(composer._cursor_pos)
    if (
        move_to_next_line_when_at_end
        and composer._cursor_pos == target_pos
        and target_pos < len(composer._text)
    ):
        target_pos = composer._line_end(target_pos + 1)
    composer._set_cursor_position(target_pos, extend=extend)
    composer._preferred_column = None
    composer._sync()


def move_cursor_home(composer, *, extend: bool = False) -> None:
    rows, row_index = composer._visual_row_state()
    composer._set_cursor_position(rows[row_index][0], extend=extend)
    composer._preferred_column = None
    composer._sync()


def move_cursor_end(composer, *, extend: bool = False) -> None:
    rows, row_index = composer._visual_row_state()
    composer._set_cursor_position(rows[row_index][1], extend=extend)
    composer._preferred_column = None
    composer._sync()


def move_cursor_up(composer, *, extend: bool = False) -> None:
    rows, row_index = composer._visual_row_state()
    if row_index == 0:
        composer._set_cursor_position(0, extend=extend)
        composer._preferred_column = composer._row_display_column(rows[0], composer._cursor_pos)
        composer._sync()
        return
    column = composer._current_or_preferred_column()
    target_row = rows[row_index - 1]
    composer._set_cursor_position(
        composer._position_in_row_for_column(target_row, column), extend=extend
    )
    composer._preferred_column = column
    composer._sync()


def move_cursor_down(composer, *, extend: bool = False) -> None:
    rows, row_index = composer._visual_row_state()
    if row_index >= len(rows) - 1:
        composer._set_cursor_position(len(composer._text), extend=extend)
        composer._preferred_column = composer._row_display_column(rows[-1], composer._cursor_pos)
        composer._sync()
        return
    column = composer._current_or_preferred_column()
    target_row = rows[row_index + 1]
    composer._set_cursor_position(
        composer._position_in_row_for_column(target_row, column), extend=extend
    )
    composer._preferred_column = column
    composer._sync()


def select_all(composer) -> None:
    composer._selection_anchor = 0
    composer._cursor_pos = len(composer._text)
    composer._preferred_column = None
    composer._sync()


def clear_selection(composer) -> None:
    if composer._selection_anchor is None:
        return
    composer._selection_anchor = None
    composer._sync()


def copy_selection_to_clipboard(composer) -> bool:
    selected = composer.selected_text
    if not selected:
        return False
    try:
        composer.app.copy_to_clipboard(selected)
    except Exception:
        return False
    return True


def cut_selection_to_clipboard(composer) -> bool:
    if not composer.copy_selection_to_clipboard():
        return False
    composer.delete_selection()
    return True


def delete_selection(composer) -> bool:
    bounds = composer.selection_bounds
    if bounds is None:
        return False
    start, end = bounds
    composer._replace_range(start, end, "")
    return True


def kill_range(composer, start: int, end: int) -> bool:
    expanded_start, expanded_end = composer._expand_bounds_to_atomic_tokens(start, end)
    if expanded_end <= expanded_start:
        return False
    removed_text = composer._text[expanded_start:expanded_end]
    if not removed_text:
        return False
    composer._kill_buffer = removed_text
    composer._replace_range(expanded_start, expanded_end, "")
    return True


def delete_backward_word(composer) -> None:
    bounds = composer.selection_bounds
    if bounds is not None:
        composer._kill_range(bounds[0], bounds[1])
        return
    if composer._cursor_pos <= 0:
        return
    composer._kill_range(composer._beginning_of_previous_word(), composer._cursor_pos)


def delete_forward_word(composer) -> None:
    bounds = composer.selection_bounds
    if bounds is not None:
        composer._kill_range(bounds[0], bounds[1])
        return
    if composer._cursor_pos >= len(composer._text):
        return
    composer._kill_range(composer._cursor_pos, composer._end_of_next_word())


def kill_line_start(composer) -> None:
    bounds = composer.selection_bounds
    if bounds is not None:
        composer._kill_range(bounds[0], bounds[1])
        return
    line_start_pos = composer._line_start(composer._cursor_pos)
    if composer._cursor_pos == line_start_pos:
        return
    composer._kill_range(line_start_pos, composer._cursor_pos)


def kill_line_end(composer) -> None:
    bounds = composer.selection_bounds
    if bounds is not None:
        composer._kill_range(bounds[0], bounds[1])
        return
    line_end_pos = composer._line_end(composer._cursor_pos)
    if composer._cursor_pos == line_end_pos:
        if line_end_pos < len(composer._text):
            composer._kill_range(composer._cursor_pos, line_end_pos + 1)
        return
    composer._kill_range(composer._cursor_pos, line_end_pos)


def yank_kill_buffer(composer) -> None:
    if not composer._kill_buffer:
        return
    composer.insert_text(composer._kill_buffer)


def current_or_preferred_column(composer) -> int:
    if composer._preferred_column is not None:
        return composer._preferred_column
    rows, row_index = composer._visual_row_state()
    return composer._row_display_column(rows[row_index], composer._cursor_pos)


def line_start(composer, pos: int) -> int:
    return composer_editing_model_runtime.line_start(composer._text, pos)


def line_end(composer, pos: int) -> int:
    return composer_editing_model_runtime.line_end(composer._text, pos)


def column(composer, pos: int) -> int:
    return composer_editing_model_runtime.column(composer._text, pos)


def navigation_total_width(composer) -> int:
    live_width = (
        getattr(getattr(composer, "content_region", None), "width", 0)
        or getattr(getattr(composer, "region", None), "width", 0)
        or composer.size.width
        or composer._last_render_width
    )
    if live_width:
        return max(1, live_width)
    longest_line = max((cell_len(line) for line in composer._text.split("\n")), default=0)
    return max(1, longest_line + cell_len(composer.PROMPT_PREFIX))


def content_width(composer_cls, total_width: int) -> int:
    return max(1, total_width - cell_len(composer_cls._prompt_prefix(total_width)))


def visual_row_ranges(composer, total_width: int) -> list[tuple[int, int]]:
    content_width_value = composer._content_width(total_width)
    return composer_editing_model_runtime.visual_row_ranges(composer._text, content_width_value)


def visual_row_state(composer) -> tuple[list[tuple[int, int]], int]:
    rows = composer._visual_row_ranges(composer._navigation_total_width())
    return composer_editing_model_runtime.row_state(rows, composer._cursor_pos)


def row_display_column(composer, row: tuple[int, int], pos: int) -> int:
    return composer_editing_model_runtime.row_display_column(composer._text, row, pos)


def position_in_row_for_column(composer, row: tuple[int, int], target_column: int) -> int:
    return composer_editing_model_runtime.position_in_row_for_column(
        composer._text, row, target_column
    )


def set_cursor_position(composer, pos: int, *, extend: bool) -> None:
    next_pos = max(0, min(pos, len(composer._text)))
    if extend:
        if composer._selection_anchor is None:
            composer._selection_anchor = composer._cursor_pos
    else:
        composer._selection_anchor = None
    composer._cursor_pos = next_pos
    if composer._selection_anchor == composer._cursor_pos:
        composer._selection_anchor = None


def word_like_range_at(composer, pos: int) -> tuple[int, int]:
    return composer_editing_model_runtime.word_like_range_at(
        composer._text,
        pos,
        is_word_separator_fn=composer._is_word_separator,
    )


def atomic_ranges(composer) -> list[tuple[int, int]]:
    return composer_editing_model_runtime.atomic_ranges(
        composer._text,
        (composer.PASTED_PLACEHOLDER_RE, composer.ATTACHMENT_REFERENCE_RE),
    )


def atomic_range_at(composer, pos: int) -> tuple[int, int] | None:
    return composer_editing_model_runtime.atomic_range_at(
        composer._atomic_ranges(),
        pos,
        text_length=len(composer._text),
    )


def expand_bounds_to_atomic_tokens(composer, start: int, end: int) -> tuple[int, int]:
    return composer_editing_model_runtime.expand_bounds_to_atomic_tokens(
        composer._atomic_ranges(), start, end
    )


def replace_selection_or_insert(composer, text: str) -> None:
    bounds = composer.selection_bounds
    if bounds is None:
        composer._replace_range(composer._cursor_pos, composer._cursor_pos, text)
        return
    composer._replace_range(bounds[0], bounds[1], text)


def replace_range(composer, start: int, end: int, replacement: str) -> None:
    composer._push_undo_snapshot()
    composer._text = composer._text[:start] + replacement + composer._text[end:]
    composer._cursor_pos = start + len(replacement)
    composer._selection_anchor = None
    composer._preferred_column = None
    composer._sync()


def is_word_separator(composer_cls, char: str) -> bool:
    return char in composer_cls.WORD_SEPARATORS


def beginning_of_previous_word(composer) -> int:
    return composer_editing_model_runtime.beginning_of_previous_word(
        composer._text,
        composer._cursor_pos,
        is_word_separator_fn=composer._is_word_separator,
    )


def end_of_next_word(composer) -> int:
    return composer_editing_model_runtime.end_of_next_word(
        composer._text,
        composer._cursor_pos,
        is_word_separator_fn=composer._is_word_separator,
    )

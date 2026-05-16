from __future__ import annotations

from textual.events import MouseDown, MouseMove, MouseUp, Paste

from cli.agent_cli.ui import (
    composer_actions,
    composer_cursor_runtime,
    composer_edit_runtime,
    composer_helpers_runtime,
    composer_runtime,
    composer_submission,
    composer_widget_runtime,
)

ComposerSnapshot = composer_edit_runtime.ComposerSnapshot


class ComposerSelectionMixin:
    @property
    def text(self) -> str:
        return self._text

    @property
    def cursor_pos(self) -> int:
        return self._cursor_pos

    @property
    def selection_anchor(self) -> int | None:
        return self._selection_anchor

    @property
    def has_selection(self) -> bool:
        return self._selection_anchor is not None and self._selection_anchor != self._cursor_pos

    @property
    def selection_bounds(self) -> tuple[int, int] | None:
        if not self.has_selection:
            return None
        assert self._selection_anchor is not None
        bounds = (
            min(self._selection_anchor, self._cursor_pos),
            max(self._selection_anchor, self._cursor_pos),
        )
        return self._expand_bounds_to_atomic_tokens(*bounds)

    @property
    def selected_text(self) -> str:
        bounds = self.selection_bounds
        if bounds is None:
            return ""
        start, end = bounds
        return self._text[start:end]


class ComposerCursorMixin:
    def on_mouse_down(self, event: MouseDown) -> None:
        composer_cursor_runtime.on_mouse_down(self, event)

    def on_mouse_move(self, event: MouseMove) -> None:
        composer_cursor_runtime.on_mouse_move(self, event)

    def on_mouse_up(self, event: MouseUp) -> None:
        composer_cursor_runtime.on_mouse_up(self, event)

    def _event_visual_point(self, event) -> tuple[int, int]:
        return composer_cursor_runtime.event_visual_point(self, event)

    def _move_cursor_to_mouse_event(self, event, *, extend: bool = False) -> int:
        return composer_cursor_runtime.move_cursor_to_mouse_event(self, event, extend=extend)

    def move_cursor_to_visual_point(
        self, x: int, y: int, *, sync: bool = True, extend: bool = False
    ) -> int:
        return composer_cursor_runtime.move_cursor_to_visual_point(
            self,
            x,
            y,
            sync=sync,
            extend=extend,
        )

    def _register_click_streak(self, x: int, y: int) -> int:
        return composer_cursor_runtime.register_click_streak(self, x, y)

    def _select_range(self, start: int, end: int) -> None:
        composer_cursor_runtime.select_range(self, start, end)

    def _select_word_at(self, pos: int) -> None:
        composer_cursor_runtime.select_word_at(self, pos)

    def _select_line_at(self, pos: int) -> None:
        composer_cursor_runtime.select_line_at(self, pos)


class ComposerEditMixin:
    def clear_text(self) -> None:
        composer_edit_runtime.clear_text(self)

    def set_text(self, text: str) -> None:
        composer_edit_runtime.set_text(self, text)

    def insert_text(self, text: str) -> None:
        composer_edit_runtime.insert_text(self, text)

    def backspace(self) -> None:
        composer_edit_runtime.backspace(self)

    def delete_forward(self) -> None:
        composer_edit_runtime.delete_forward(self)

    def move_cursor_left(self, *, extend: bool = False) -> None:
        composer_edit_runtime.move_cursor_left(self, extend=extend)

    def move_cursor_right(self, *, extend: bool = False) -> None:
        composer_edit_runtime.move_cursor_right(self, extend=extend)

    def move_cursor_word_left(self, *, extend: bool = False) -> None:
        composer_edit_runtime.move_cursor_word_left(self, extend=extend)

    def move_cursor_word_right(self, *, extend: bool = False) -> None:
        composer_edit_runtime.move_cursor_word_right(self, extend=extend)

    def move_cursor_logical_line_end(
        self,
        *,
        extend: bool = False,
        move_to_next_line_when_at_end: bool = False,
    ) -> None:
        composer_edit_runtime.move_cursor_logical_line_end(
            self,
            extend=extend,
            move_to_next_line_when_at_end=move_to_next_line_when_at_end,
        )

    def move_cursor_home(self, *, extend: bool = False) -> None:
        composer_edit_runtime.move_cursor_home(self, extend=extend)

    def move_cursor_end(self, *, extend: bool = False) -> None:
        composer_edit_runtime.move_cursor_end(self, extend=extend)

    def move_cursor_up(self, *, extend: bool = False) -> None:
        composer_edit_runtime.move_cursor_up(self, extend=extend)

    def move_cursor_down(self, *, extend: bool = False) -> None:
        composer_edit_runtime.move_cursor_down(self, extend=extend)

    def select_all(self) -> None:
        composer_edit_runtime.select_all(self)

    def clear_selection(self) -> None:
        composer_edit_runtime.clear_selection(self)

    def copy_selection_to_clipboard(self) -> bool:
        return composer_edit_runtime.copy_selection_to_clipboard(self)

    def cut_selection_to_clipboard(self) -> bool:
        return composer_edit_runtime.cut_selection_to_clipboard(self)

    def delete_selection(self) -> bool:
        return composer_edit_runtime.delete_selection(self)

    def delete_backward_word(self) -> None:
        composer_edit_runtime.delete_backward_word(self)

    def delete_forward_word(self) -> None:
        composer_edit_runtime.delete_forward_word(self)

    def kill_line_start(self) -> None:
        composer_edit_runtime.kill_line_start(self)

    def kill_line_end(self) -> None:
        composer_edit_runtime.kill_line_end(self)

    def yank_kill_buffer(self) -> None:
        composer_edit_runtime.yank_kill_buffer(self)

    def undo(self) -> None:
        composer_edit_runtime.undo(self)

    def redo(self) -> None:
        composer_edit_runtime.redo(self)

    def _current_or_preferred_column(self) -> int:
        return composer_edit_runtime.current_or_preferred_column(self)

    def _line_start(self, pos: int) -> int:
        return composer_edit_runtime.line_start(self, pos)

    def _line_end(self, pos: int) -> int:
        return composer_edit_runtime.line_end(self, pos)

    def _column(self, pos: int) -> int:
        return composer_edit_runtime.column(self, pos)

    def _navigation_total_width(self) -> int:
        return composer_edit_runtime.navigation_total_width(self)

    @classmethod
    def _content_width(cls, total_width: int) -> int:
        return composer_edit_runtime.content_width(cls, total_width)

    def _visual_row_ranges(self, total_width: int) -> list[tuple[int, int]]:
        return composer_edit_runtime.visual_row_ranges(self, total_width)

    def _visual_row_state(self) -> tuple[list[tuple[int, int]], int]:
        return composer_edit_runtime.visual_row_state(self)

    def _row_display_column(self, row: tuple[int, int], pos: int) -> int:
        return composer_edit_runtime.row_display_column(self, row, pos)

    def _position_in_row_for_column(self, row: tuple[int, int], target_column: int) -> int:
        return composer_edit_runtime.position_in_row_for_column(self, row, target_column)

    def _set_cursor_position(self, pos: int, *, extend: bool) -> None:
        composer_edit_runtime.set_cursor_position(self, pos, extend=extend)

    def _word_like_range_at(self, pos: int) -> tuple[int, int]:
        return composer_edit_runtime.word_like_range_at(self, pos)

    def _atomic_ranges(self) -> list[tuple[int, int]]:
        return composer_edit_runtime.atomic_ranges(self)

    def _atomic_range_at(self, pos: int) -> tuple[int, int] | None:
        return composer_edit_runtime.atomic_range_at(self, pos)

    def _expand_bounds_to_atomic_tokens(self, start: int, end: int) -> tuple[int, int]:
        return composer_edit_runtime.expand_bounds_to_atomic_tokens(self, start, end)

    def _kill_range(self, start: int, end: int) -> bool:
        return composer_edit_runtime.kill_range(self, start, end)

    def _snapshot(self) -> ComposerSnapshot:
        return composer_edit_runtime.snapshot(self)

    def _push_undo_snapshot(self) -> None:
        composer_edit_runtime.push_undo_snapshot(self)

    def _apply_snapshot(self, snapshot: ComposerSnapshot) -> None:
        composer_edit_runtime.apply_snapshot(self, snapshot)

    def _replace_selection_or_insert(self, text: str) -> None:
        composer_edit_runtime.replace_selection_or_insert(self, text)

    def _replace_range(self, start: int, end: int, replacement: str) -> None:
        composer_edit_runtime.replace_range(self, start, end, replacement)

    @classmethod
    def _is_word_separator(cls, char: str) -> bool:
        return composer_edit_runtime.is_word_separator(cls, char)

    def _beginning_of_previous_word(self) -> int:
        return composer_edit_runtime.beginning_of_previous_word(self)

    def _end_of_next_word(self) -> int:
        return composer_edit_runtime.end_of_next_word(self)


class ComposerWidgetMixin:
    def _sync(self) -> None:
        composer_widget_runtime.sync_composer(self)

    def visible_line_count(self, width: int) -> int:
        return composer_widget_runtime.visible_line_count(
            self,
            width,
            display_text_and_cursor_fn=self._display_text_and_cursor,
            visual_lines_fn=lambda text, cursor_pos, computed_width: self._visual_lines(
                text,
                cursor_pos,
                computed_width,
                include_cursor=True,
            ),
        )


class ComposerRenderMixin(composer_helpers_runtime.ComposerRenderMixinRuntime):
    pass


class ComposerActionMixin:
    @staticmethod
    def _should_buffer_printable_char(character: str) -> bool:
        return composer_actions.should_buffer_printable_char(character)

    def _handle_submission_action_key(self, event) -> bool:
        return composer_submission.handle_submission_action_key(self, event)

    def _handle_ascii_input(self, character: str) -> None:
        composer_actions.handle_ascii_input(self, character)

    def _flush_paste_burst_if_due(self) -> None:
        composer_actions.flush_paste_burst_if_due(self)

    def flush_paste_burst(self) -> bool:
        return composer_actions.flush_paste_burst(self)

    def _flush_burst_buffer_as_paste(self) -> None:
        composer_actions.flush_burst_buffer_as_paste(self)

    def _flush_pending_ascii_as_typed(self) -> None:
        composer_actions.flush_pending_ascii_as_typed(self)

    def _clear_paste_burst_state(self) -> None:
        composer_actions.clear_paste_burst_state(self)

    def _is_paste_suppression_active(self) -> bool:
        return composer_actions.is_paste_suppression_active(self)

    def _arm_paste_suppression(self, text: str | None = None) -> None:
        composer_actions.arm_paste_suppression(self, text)

    def _should_suppress_paste(self, text: str) -> bool:
        return composer_actions.should_suppress_paste(self, text)


class ComposerRuntimeMixin:
    def on_key(self, event) -> None:
        if str(getattr(self.app, "_screen_mode", "prompt") or "prompt") != "prompt":
            return
        if composer_runtime.handle_alt_enter_escape_fallback(composer=self, event=event):
            return
        prehandled = composer_widget_runtime.handle_key_event(
            self,
            event,
            is_paste_suppression_active_fn=self._is_paste_suppression_active,
            should_buffer_printable_char_fn=self._should_buffer_printable_char,
            flush_paste_burst_fn=self.flush_paste_burst,
            handle_ascii_input_fn=self._handle_ascii_input,
            handle_submission_action_key_fn=self._handle_submission_action_key,
        )
        if composer_runtime.handle_key_event(
            composer=self,
            event=event,
            prehandled=prehandled,
            app_ctrl_c_fn=self.app.action_ctrl_c,
        ):
            return

    def on_paste(self, event: Paste) -> None:
        composer_widget_runtime.handle_paste_event(
            self,
            event,
            clear_paste_burst_state_fn=self._clear_paste_burst_state,
            should_suppress_paste_fn=self._should_suppress_paste,
            insert_text_fn=self.insert_text,
        )

    def on_focus(self) -> None:
        self.refresh(repaint=True, layout=False)

    def on_blur(self) -> None:
        self.refresh(repaint=True, layout=False)

from __future__ import annotations

import unittest
from unittest.mock import patch

from cli.agent_cli.app import PromptComposer
from cli.agent_cli.ui import unicode_word_break_runtime

class PromptComposerSpecTest(unittest.TestCase):
    def assert_cursor_render(
        self,
        composer: PromptComposer,
        width: int,
        expected_plain: str,
        cursor_start: int,
    ) -> None:
        rendered = composer.build_render_text(width, focused=True)
        self.assertEqual(rendered.plain, expected_plain)
        reverse_spans = [(span.start, span.end) for span in rendered.spans if "reverse" in str(span.style)]
        self.assertEqual(reverse_spans, [(cursor_start, cursor_start + 1)])

    def test_empty_prompt_shows_reference_like_prefix_and_block_cursor(self) -> None:
        composer = PromptComposer("")

        self.assertEqual(composer.text, "")
        self.assertEqual(composer.cursor_pos, 0)
        self.assert_cursor_render(composer, 12, "› Ask AgentHub to do anything", 2)

    def test_set_text_moves_cursor_to_end(self) -> None:
        composer = PromptComposer("")

        composer.set_text("hello")

        self.assertEqual(composer.text, "hello")
        self.assertEqual(composer.cursor_pos, 5)
        self.assert_cursor_render(composer, 12, "› hello ", 7)

    def test_insert_text_respects_current_cursor_position(self) -> None:
        composer = PromptComposer("helo")

        composer.move_cursor_left()
        composer.insert_text("l")

        self.assertEqual(composer.text, "hello")
        self.assertEqual(composer.cursor_pos, 4)
        self.assert_cursor_render(composer, 12, "› hello", 6)

    def test_shift_left_creates_selection_and_insert_replaces_it(self) -> None:
        composer = PromptComposer("hello")

        composer.move_cursor_left(extend=True)
        composer.move_cursor_left(extend=True)

        self.assertTrue(composer.has_selection)
        self.assertEqual(composer.selected_text, "lo")

        composer.insert_text("p")

        self.assertEqual(composer.text, "help")
        self.assertEqual(composer.cursor_pos, 4)
        self.assertFalse(composer.has_selection)

    def test_left_and_right_stop_at_buffer_edges(self) -> None:
        composer = PromptComposer("ab")

        composer.move_cursor_left()
        composer.move_cursor_left()
        composer.move_cursor_left()
        self.assertEqual(composer.cursor_pos, 0)
        self.assert_cursor_render(composer, 12, "› ab", 2)

        composer.move_cursor_right()
        composer.move_cursor_right()
        composer.move_cursor_right()
        self.assertEqual(composer.cursor_pos, 2)
        self.assert_cursor_render(composer, 12, "› ab ", 4)

    def test_ctrl_left_moves_to_beginning_of_previous_word(self) -> None:
        composer = PromptComposer("alpha  beta")

        composer.move_cursor_word_left()
        self.assertEqual(composer.cursor_pos, 7)
        self.assert_cursor_render(composer, 16, "› alpha  beta", 9)

        composer.move_cursor_word_left()
        self.assertEqual(composer.cursor_pos, 0)
        self.assert_cursor_render(composer, 16, "› alpha  beta", 2)

    def test_ctrl_right_moves_to_end_of_next_word(self) -> None:
        composer = PromptComposer("alpha  beta")
        composer.move_cursor_home()

        composer.move_cursor_word_right()
        self.assertEqual(composer.cursor_pos, 5)
        self.assert_cursor_render(composer, 16, "› alpha  beta", 7)

        composer.move_cursor_word_right()
        self.assertEqual(composer.cursor_pos, 11)
        self.assert_cursor_render(composer, 16, "› alpha  beta ", 13)

    def test_word_motion_treats_separator_runs_as_distinct_words(self) -> None:
        composer = PromptComposer("send-draft_now")

        composer.move_cursor_word_left()
        self.assertEqual(composer.cursor_pos, 5)
        self.assert_cursor_render(composer, 20, "› send-draft_now", 7)

        composer.move_cursor_word_left()
        self.assertEqual(composer.cursor_pos, 4)
        self.assert_cursor_render(composer, 20, "› send-draft_now", 6)

        composer.move_cursor_word_left()
        self.assertEqual(composer.cursor_pos, 0)

    def test_word_motion_skips_whitespace_before_next_word(self) -> None:
        composer = PromptComposer("one   two")
        composer.move_cursor_home()
        composer.move_cursor_word_right()
        self.assertEqual(composer.cursor_pos, 3)

        composer.move_cursor_word_right()
        self.assertEqual(composer.cursor_pos, 9)

    def test_backspace_deletes_left_of_cursor_and_noops_at_bol(self) -> None:
        composer = PromptComposer("abc")

        composer.move_cursor_left()
        composer.backspace()
        self.assertEqual(composer.text, "ac")
        self.assertEqual(composer.cursor_pos, 1)
        self.assert_cursor_render(composer, 12, "› ac", 3)

        composer.move_cursor_home()
        composer.backspace()
        self.assertEqual(composer.text, "ac")
        self.assertEqual(composer.cursor_pos, 0)

    def test_delete_removes_character_under_cursor_and_noops_at_eol(self) -> None:
        composer = PromptComposer("abcd")

        composer.move_cursor_left()
        composer.move_cursor_left()
        composer.delete_forward()
        self.assertEqual(composer.text, "abd")
        self.assertEqual(composer.cursor_pos, 2)
        self.assert_cursor_render(composer, 12, "› abd", 4)

        composer.move_cursor_end()
        composer.delete_forward()
        self.assertEqual(composer.text, "abd")
        self.assertEqual(composer.cursor_pos, 3)

    def test_backspace_and_delete_remove_active_selection(self) -> None:
        composer = PromptComposer("abcdef")
        composer.move_cursor_left(extend=True)
        composer.move_cursor_left(extend=True)

        composer.backspace()
        self.assertEqual(composer.text, "abcd")
        self.assertEqual(composer.cursor_pos, 4)

        composer.set_text("abcdef")
        composer.move_cursor_home()
        composer.move_cursor_right(extend=True)
        composer.move_cursor_right(extend=True)
        composer.delete_forward()
        self.assertEqual(composer.text, "cdef")
        self.assertEqual(composer.cursor_pos, 0)

    def test_home_and_end_are_relative_to_current_logical_line(self) -> None:
        composer = PromptComposer("abc\ndef")

        composer.move_cursor_home()
        self.assertEqual(composer.cursor_pos, 4)
        self.assert_cursor_render(composer, 12, "› abc\n  def", 8)

        composer.move_cursor_end()
        self.assertEqual(composer.cursor_pos, 7)
        self.assert_cursor_render(composer, 12, "› abc\n  def ", 11)

    def test_vertical_motion_keeps_preferred_column_on_ragged_lines(self) -> None:
        composer = PromptComposer("abcd\nx\nwxyz")

        composer.move_cursor_left()
        self.assertEqual(composer.cursor_pos, 10)

        composer.move_cursor_up()
        self.assertEqual(composer.cursor_pos, 6)

        composer.move_cursor_up()
        self.assertEqual(composer.cursor_pos, 3)

        composer.move_cursor_down()
        self.assertEqual(composer.cursor_pos, 6)

        composer.move_cursor_down()
        self.assertEqual(composer.cursor_pos, 10)

    def test_home_and_end_follow_current_visual_row_when_wrapped(self) -> None:
        composer = PromptComposer("abcdef")
        composer.build_render_text(5, focused=True)

        composer.move_cursor_home()
        self.assertEqual(composer.cursor_pos, 3)

        composer.move_cursor_end()
        self.assertEqual(composer.cursor_pos, 6)

    def test_shift_home_and_shift_end_extend_selection_on_visual_row(self) -> None:
        composer = PromptComposer("abcdef")
        composer.build_render_text(5, focused=True)

        composer.move_cursor_home(extend=True)
        self.assertEqual(composer.selected_text, "def")

        composer.move_cursor_end(extend=True)
        self.assertFalse(composer.has_selection)
        self.assertEqual(composer.cursor_pos, 6)

    def test_vertical_motion_uses_display_columns_across_wrapped_mixed_width_rows(self) -> None:
        composer = PromptComposer("你好ab世界")
        composer.build_render_text(6, focused=True)

        composer.move_cursor_up()
        self.assertEqual(composer.cursor_pos, 4)

        composer.move_cursor_up()
        self.assertEqual(composer.cursor_pos, 1)

        composer.move_cursor_down()
        self.assertEqual(composer.cursor_pos, 4)

        composer.move_cursor_down()
        self.assertEqual(composer.cursor_pos, 6)

    def test_mouse_visual_point_moves_cursor_within_single_row(self) -> None:
        composer = PromptComposer("hello")
        composer.build_render_text(12, focused=True)

        composer.move_cursor_to_visual_point(4, 0)

        self.assertEqual(composer.cursor_pos, 2)

    def test_mouse_visual_point_moves_cursor_across_wrapped_mixed_width_rows(self) -> None:
        composer = PromptComposer("你好ab世界")
        composer.build_render_text(6, focused=True)

        composer.move_cursor_to_visual_point(3, 1)
        self.assertEqual(composer.cursor_pos, 3)

        composer.move_cursor_to_visual_point(4, 2)
        self.assertEqual(composer.cursor_pos, 6)

    def test_atomic_attachment_selection_expands_from_partial_overlap(self) -> None:
        composer = PromptComposer('read @"C:\\docs\\demo file.txt" now')
        composer._selection_anchor = 8
        composer._cursor_pos = 15

        self.assertEqual(composer.selected_text, '@"C:\\docs\\demo file.txt"')

    def test_backspace_inside_attachment_reference_deletes_whole_token(self) -> None:
        composer = PromptComposer('read @"C:\\docs\\demo file.txt" now')
        composer._cursor_pos = 15

        composer.backspace()

        self.assertEqual(composer.text, "read  now")
        self.assertEqual(composer.cursor_pos, 5)

    def test_delete_inside_paste_placeholder_deletes_whole_placeholder(self) -> None:
        composer = PromptComposer("[Pasted Content 12 chars] tail")
        composer._cursor_pos = 4

        composer.delete_forward()

        self.assertEqual(composer.text, " tail")
        self.assertEqual(composer.cursor_pos, 0)

    def test_select_word_at_picks_attachment_token_atomically(self) -> None:
        composer = PromptComposer("use @notes.md please")

        composer._select_word_at(6)

        self.assertEqual(composer.selected_text, "@notes.md")

    def test_select_word_at_prefers_unicode_word_break_for_mixed_text(self) -> None:
        composer = PromptComposer("中文English混排")

        with patch(
            "cli.agent_cli.ui.composer_editing_model_runtime.unicode_word_break_runtime.word_range_at",
            return_value=(2, 9),
        ):
            composer._select_word_at(composer.text.index("g"))

        self.assertEqual(composer.selected_text, "English")

    @unittest.skipIf(
        unicode_word_break_runtime.word_range_at("中文测试", 0) is None,
        "ICU word break runtime not available",
    )
    def test_select_word_at_uses_icu_for_chinese_words(self) -> None:
        composer = PromptComposer("中文English工具")

        composer._select_word_at(composer.text.index("文"))
        self.assertEqual(composer.selected_text, "中文")

        composer._select_word_at(composer.text.index("g"))
        self.assertEqual(composer.selected_text, "English")

        composer._select_word_at(composer.text.index("具"))
        self.assertEqual(composer.selected_text, "工具")

    @unittest.skipIf(
        unicode_word_break_runtime.word_range_at("中文测试", 0) is None,
        "ICU word break runtime not available",
    )
    def test_word_motion_uses_icu_boundaries_for_cjk_mixed_text(self) -> None:
        composer = PromptComposer("中文English工具")
        self.assertEqual(composer.cursor_pos, len("中文English工具"))

        composer.move_cursor_word_left()
        self.assertEqual(composer.cursor_pos, 9)

        composer.move_cursor_word_left()
        self.assertEqual(composer.cursor_pos, 2)

        composer.move_cursor_word_left()
        self.assertEqual(composer.cursor_pos, 0)

        composer.move_cursor_word_right()
        self.assertEqual(composer.cursor_pos, 2)

        composer.move_cursor_word_right()
        self.assertEqual(composer.cursor_pos, 9)

        composer.move_cursor_word_right()
        self.assertEqual(composer.cursor_pos, 11)

    def test_select_line_at_selects_full_logical_line(self) -> None:
        composer = PromptComposer("alpha\nbeta\ngamma")

        composer._select_line_at(7)

        self.assertEqual(composer.selected_text, "beta")

    def test_select_all_copy_cut_undo_redo(self) -> None:
        composer = PromptComposer("hello world")
        copied: list[str] = []
        composer.copy_selection_to_clipboard = lambda: copied.append(composer.selected_text) or True

        composer.select_all()
        self.assertTrue(composer.copy_selection_to_clipboard())
        self.assertEqual(copied, ["hello world"])

        self.assertTrue(composer.cut_selection_to_clipboard())
        self.assertEqual(composer.text, "")

        composer.undo()
        self.assertEqual(composer.text, "hello world")
        self.assertTrue(composer.has_selection)

        composer.redo()
        self.assertEqual(composer.text, "")
        self.assertFalse(composer.has_selection)

    def test_selection_renders_reverse_style(self) -> None:
        composer = PromptComposer("hello")
        composer.move_cursor_left(extend=True)
        composer.move_cursor_left(extend=True)

        rendered = composer.build_render_text(12, focused=True)
        self.assertEqual(rendered.plain, "› hello")
        reverse_spans = [(span.start, span.end) for span in rendered.spans if "reverse" in str(span.style)]
        self.assertEqual(reverse_spans, [(5, 7)])

    def test_wrapped_render_uses_prompt_then_continuation_indent(self) -> None:
        composer = PromptComposer("abcdef")

        self.assert_cursor_render(
            composer,
            5,
            "› abc\n  def\n   ",
            14,
        )

    def test_wrapped_render_uses_display_width_for_cjk_characters(self) -> None:
        composer = PromptComposer("你好ab")

        self.assert_cursor_render(
            composer,
            6,
            "› 你好\n  ab ",
            9,
        )

    def test_narrow_width_falls_back_to_single_character_prompt_prefix(self) -> None:
        composer = PromptComposer("")

        self.assert_cursor_render(composer, 1, "›Ask AgentHub to do anything", 1)

    def test_visible_line_count_includes_cursor_wrap_and_caps_at_maximum(self) -> None:
        composer = PromptComposer("abcdefghijklmno")

        self.assertEqual(composer.visible_line_count(5), 6)
        self.assertEqual(composer.visible_line_count(40), 1)

    def test_clear_text_resets_buffer_and_cursor(self) -> None:
        composer = PromptComposer("hello")

        composer.clear_text()

        self.assertEqual(composer.text, "")
        self.assertEqual(composer.cursor_pos, 0)
        self.assert_cursor_render(composer, 12, "› Ask AgentHub to do anything", 2)

    def test_queue_hint_precondition_treats_whitespace_only_draft_as_empty(self) -> None:
        composer = PromptComposer("")
        composer.set_text("  \n\t  ")

        has_draft = bool(composer.text.strip())

        self.assertFalse(has_draft)

    def test_queue_hint_precondition_treats_non_whitespace_draft_as_present(self) -> None:
        composer = PromptComposer("")
        composer.set_text("   /background_task_status bg123  ")

        has_draft = bool(composer.text.strip())

        self.assertTrue(has_draft)

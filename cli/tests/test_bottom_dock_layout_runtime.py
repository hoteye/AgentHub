from __future__ import annotations

import unittest

from rich.cells import cell_len

from cli.agent_cli.ui.bottom_dock_layout_runtime import (
    compose_bottom_dock_line,
    layout_bottom_dock_line,
)


class BottomDockLayoutRuntimeTest(unittest.TestCase):
    def test_layout_returns_empty_when_both_sides_are_blank(self) -> None:
        layout = layout_bottom_dock_line(left="  ", right="\n", width=8)

        self.assertEqual(layout.line, "")
        self.assertEqual(layout.left_text, "")
        self.assertEqual(layout.right_text, "")
        self.assertFalse(layout.right_visible)

    def test_layout_keeps_right_aligned_when_both_fit(self) -> None:
        layout = layout_bottom_dock_line(left="L", right="R", width=5)

        self.assertEqual(layout.line, "L   R")
        self.assertEqual(layout.left_text, "L")
        self.assertEqual(layout.right_text, "R")
        self.assertTrue(layout.right_visible)

    def test_layout_truncates_left_first_when_space_is_tight(self) -> None:
        layout = layout_bottom_dock_line(left="left-left", right="R", width=10)

        self.assertEqual(layout.line, "left-... R")
        self.assertEqual(layout.left_text, "left-...")
        self.assertEqual(layout.right_text, "R")
        self.assertTrue(layout.right_visible)

    def test_layout_can_hide_right_when_requested(self) -> None:
        layout = layout_bottom_dock_line(
            left="left-left",
            right="R",
            width=8,
            hide_right_when_needed=True,
        )

        self.assertEqual(layout.line, "left-...")
        self.assertEqual(layout.left_text, "left-...")
        self.assertEqual(layout.right_text, "")
        self.assertFalse(layout.right_visible)

    def test_layout_can_prefer_hiding_right_to_keep_left_stable(self) -> None:
        layout = layout_bottom_dock_line(
            left="queue message",
            right="82% left",
            width=16,
            prefer_hiding_right_when_left_present=True,
        )

        self.assertEqual(layout.line, "queue message")
        self.assertEqual(layout.left_text, "queue message")
        self.assertEqual(layout.right_text, "")
        self.assertFalse(layout.right_visible)

    def test_layout_falls_back_to_right_when_right_is_too_wide(self) -> None:
        layout = layout_bottom_dock_line(left="A", right="1234567", width=5)

        self.assertEqual(layout.line, "12...")
        self.assertEqual(layout.left_text, "")
        self.assertEqual(layout.right_text, "12...")
        self.assertTrue(layout.right_visible)

    def test_layout_normalizes_newlines(self) -> None:
        layout = layout_bottom_dock_line(left="a\nb", right="c\nd", width=12)

        self.assertNotIn("\n", layout.line)
        self.assertEqual(layout.left_text, "a b")
        self.assertEqual(layout.right_text, "c d")
        self.assertTrue(layout.line.endswith("c d"))

    def test_layout_supports_wide_characters(self) -> None:
        layout = layout_bottom_dock_line(left="你你你", right="R", width=7)

        self.assertEqual(layout.left_text, "你...")
        self.assertEqual(layout.right_text, "R")
        self.assertEqual(cell_len(layout.line), 7)
        self.assertTrue(layout.right_visible)

    def test_layout_drops_meaningless_left_fragment_when_only_right_is_useful(self) -> None:
        layout = layout_bottom_dock_line(left="  ? for shortcuts", right="100% context left", width=20)

        self.assertEqual(layout.left_text, "")
        self.assertEqual(layout.right_text, "100% context left")
        self.assertEqual(layout.line, "100% context left")
        self.assertTrue(layout.right_visible)

    def test_layout_tiny_width_falls_back_to_ellipsis_on_right(self) -> None:
        layout = layout_bottom_dock_line(left="queue", right="context", width=3)

        self.assertEqual(layout.left_text, "")
        self.assertEqual(layout.right_text, "...")
        self.assertEqual(layout.line, "...")
        self.assertTrue(layout.right_visible)

    def test_compose_helper_returns_rendered_line(self) -> None:
        rendered = compose_bottom_dock_line(left="left", right="right", width=14)
        self.assertEqual(rendered, "left     right")

    def test_compose_helper_supports_prefer_hiding_right_mode(self) -> None:
        rendered = compose_bottom_dock_line(
            left="queue message",
            right="82% left",
            width=16,
            prefer_hiding_right_when_left_present=True,
        )

        self.assertEqual(rendered, "queue message")


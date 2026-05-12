from __future__ import annotations

import unittest

from cli.agent_cli.ui.bottom_dock_render_runtime import BottomDockRenderState


class BottomDockRenderRuntimeTest(unittest.TestCase):
    def test_render_state_preserves_primary_and_secondary_lines(self) -> None:
        state = BottomDockRenderState(
            primary_line="• ? for shortcuts",
            secondary_line="100% context left",
        )

        self.assertEqual(state.primary_line, "• ? for shortcuts")
        self.assertEqual(state.secondary_line, "100% context left")


from __future__ import annotations

import unittest

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.ui.transcript_virtual_list import TranscriptVirtualList
from textual.widgets import Static


class TuiTranscriptSearchNavigationTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _static_plain(widget: Static) -> str:
        renderable = getattr(widget, "renderable", None)
        if renderable is not None:
            return getattr(renderable, "plain", str(renderable))
        return str(widget.render())

    async def test_ctrl_f_searches_transcript_and_f3_advances_match(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            for index in range(5):
                app._write_user_prompt(f"question {index}")
                app._write_assistant_reply(f"shared needle reply {index}")
            await pilot.pause()

            await pilot.press("ctrl+o")
            await pilot.pause()

            await pilot.press("ctrl+f")
            for char in "needle":
                await pilot.press(char)
            await pilot.press("enter")
            await pilot.pause()

            state = app._transcript_browsing_state
            transcript_log = app.query_one("#transcript_log", TranscriptVirtualList)
            self.assertEqual(state.query, "needle")
            self.assertGreaterEqual(len(state.match_entry_ids), 1)
            first_active = state.active_match_entry_id
            self.assertEqual(transcript_log._active_highlighted_entry_id, first_active)

            await pilot.press("f3")
            await pilot.pause()

            advanced_state = app._transcript_browsing_state
            self.assertNotEqual(advanced_state.active_match_entry_id, first_active)
            self.assertEqual(transcript_log._active_highlighted_entry_id, advanced_state.active_match_entry_id)

    async def test_search_backspace_updates_matches_and_shift_n_wraps_to_previous_match(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app._write_user_prompt("question 0")
            app._write_assistant_reply("alpha-target-0")
            app._write_user_prompt("question 1")
            app._write_assistant_reply("alpha-target-1")
            app._write_user_prompt("question other")
            app._write_assistant_reply("outside-target-beta")
            await pilot.pause()

            await pilot.press("ctrl+o")
            await pilot.pause()

            app._activate_transcript_search_mode()
            for char in "alpha-target-1":
                self.assertTrue(app._handle_transcript_search_text_input(char))
            self.assertTrue(app._handle_transcript_search_key("backspace"))
            self.assertTrue(app._handle_transcript_search_key("enter"))
            await pilot.pause()

            state = app._transcript_browsing_state
            transcript_log = app.query_one("#transcript_log", TranscriptVirtualList)
            self.assertEqual(state.query, "alpha-target-")
            self.assertEqual(len(state.match_entry_ids), 2)
            self.assertEqual(state.active_match_index, 0)

            first_match = state.match_entry_ids[0]
            last_match = state.match_entry_ids[-1]
            self.assertEqual(transcript_log._active_highlighted_entry_id, first_match)

            self.assertTrue(app._handle_transcript_search_key("shift+n"))
            await pilot.pause()

            wrapped_state = app._transcript_browsing_state
            self.assertEqual(wrapped_state.active_match_entry_id, last_match)
            self.assertNotEqual(wrapped_state.active_match_entry_id, first_match)
            self.assertEqual(transcript_log._active_highlighted_entry_id, last_match)

    async def test_transcript_footer_mentions_search_shortcuts(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+o")
            await pilot.pause()

            footer = self._static_plain(app.query_one("#composer_footer", Static)).lower()
            self.assertIn("ctrl+f", footer)
            self.assertIn("f3", footer)

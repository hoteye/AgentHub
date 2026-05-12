from __future__ import annotations

import unittest

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.ui.transcript_virtual_list import TranscriptVirtualList
from cli.agent_cli.ui.widgets import TranscriptArea


class PromptTranscriptWindowPhase1Tests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _lines(app: AgentCliApp) -> list[str]:
        return str(app.query_one("#main_log", TranscriptArea).text).splitlines()

    async def test_long_prompt_view_shows_hidden_summary_and_hides_oldest_turns(self) -> None:
        app = AgentCliApp(language="en")

        async with app.run_test() as pilot:
            await pilot.pause()
            for index in range(12):
                app._write_user_prompt(f"turn {index}")
                app._write_assistant_reply(f"reply {index}")
            await pilot.pause()

            lines = self._lines(app)
            self.assertIn("• Earlier transcript hidden", lines)
            self.assertNotIn("› turn 0", lines)
            self.assertNotIn("› turn 1", lines)
            self.assertIn("› turn 2", lines)
            self.assertIn("› turn 11", lines)

    async def test_ctrl_l_clears_prompt_window_but_transcript_mode_keeps_full_history(self) -> None:
        app = AgentCliApp(language="en")

        async with app.run_test() as pilot:
            await pilot.pause()
            for index in range(4):
                app._write_user_prompt(f"clear test {index}")
                app._write_assistant_reply(f"clear reply {index}")
            await pilot.pause()

            await pilot.press("ctrl+l")
            await pilot.pause()

            prompt_text = app.query_one("#main_log", TranscriptArea).text
            self.assertIn("log cleared", prompt_text.lower())
            self.assertNotIn("› clear test 0", prompt_text)

            await pilot.press("ctrl+o")
            await pilot.pause()

            transcript_text = app.query_one("#transcript_log", TranscriptVirtualList).text
            self.assertIn("› clear test 0", transcript_text)
            self.assertIn("› clear test 3", transcript_text)

    async def test_hidden_summary_window_does_not_advance_after_one_new_turn(self) -> None:
        app = AgentCliApp(language="en")

        async with app.run_test() as pilot:
            await pilot.pause()
            for index in range(12):
                app._write_user_prompt(f"stable {index}")
                app._write_assistant_reply(f"stable reply {index}")
            await pilot.pause()

            first_lines = self._lines(app)
            self.assertIn("› stable 2", first_lines)
            self.assertNotIn("› stable 1", first_lines)

            app._write_user_prompt("stable 12")
            app._write_assistant_reply("stable reply 12")
            await pilot.pause()

            second_lines = self._lines(app)
            self.assertIn("› stable 2", second_lines)
            self.assertIn("› stable 12", second_lines)
            self.assertNotIn("› stable 1", second_lines)

    async def test_transcript_view_still_shows_full_history_after_prompt_window_collapses(
        self,
    ) -> None:
        app = AgentCliApp(language="en")

        async with app.run_test() as pilot:
            await pilot.pause()
            for index in range(12):
                app._write_user_prompt(f"full history {index}")
                app._write_assistant_reply(f"history reply {index}")
            await pilot.pause()

            await pilot.press("ctrl+o")
            await pilot.pause()

            transcript_text = app.query_one("#transcript_log", TranscriptVirtualList).text
            self.assertIn("› full history 0", transcript_text)
            self.assertIn("› full history 11", transcript_text)

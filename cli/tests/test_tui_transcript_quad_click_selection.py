from __future__ import annotations

import unittest
from types import SimpleNamespace

from cli.agent_cli.app import AgentCliApp, PromptComposer, TranscriptArea


class TuiTranscriptQuadClickSelectionTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _left_click_event(*, x: int, y: int) -> SimpleNamespace:
        return SimpleNamespace(
            button=1,
            x=x,
            y=y,
            stop=lambda: None,
            prevent_default=lambda: None,
        )

    async def test_quadruple_click_selects_entire_current_transcript_document(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            main_log = app.query_one("#main_log", TranscriptArea)
            main_log.load_text("alpha\nbeta\ngamma")

            event = self._left_click_event(x=1, y=1)
            for _ in range(4):
                main_log.on_mouse_down(event)
            await pilot.pause()

            self.assertEqual(main_log.selected_text, "alpha\nbeta\ngamma")

    async def test_quadruple_click_does_not_auto_copy_on_left_mouse_up(self) -> None:
        app = AgentCliApp()
        copied: list[str] = []
        app.copy_to_clipboard = lambda text: copied.append(text)

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            main_log = app.query_one("#main_log", TranscriptArea)
            main_log.load_text("alpha\nbeta\ngamma")

            event = self._left_click_event(x=1, y=1)
            for _ in range(4):
                main_log.on_mouse_down(event)
            main_log.on_mouse_up(SimpleNamespace(button=1, stop=lambda: None, prevent_default=lambda: None))
            await pilot.pause()

            self.assertEqual(copied, [])
            self.assertEqual(main_log.selected_text, "alpha\nbeta\ngamma")
            self.assertIs(app.focused, composer)

    async def test_quadruple_click_selection_stays_within_current_prompt_window(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            for index in range(40):
                app._write_user_prompt(f"prompt {index}")
                app._write_assistant_reply(f"assistant reply {index} " + ("detail " * 10))
            await pilot.pause()

            main_log = app.query_one("#main_log", TranscriptArea)
            visible_text = str(main_log.text)
            self.assertIn("Earlier transcript hidden", visible_text)
            self.assertNotIn("prompt 0", visible_text)

            event = self._left_click_event(x=1, y=1)
            for _ in range(4):
                main_log.on_mouse_down(event)
            await pilot.pause()

            self.assertEqual(main_log.selected_text, visible_text)
            self.assertNotIn("prompt 0", main_log.selected_text)

    async def test_double_click_still_selects_word(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            main_log = app.query_one("#main_log", TranscriptArea)
            main_log.load_text("alpha beta gamma")

            event = self._left_click_event(x=7, y=0)
            for _ in range(2):
                main_log.on_mouse_down(event)
            await pilot.pause()

            self.assertEqual(main_log.selected_text, "beta")

    async def test_triple_click_still_selects_logical_line(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            main_log = app.query_one("#main_log", TranscriptArea)
            main_log.load_text("alpha\nbeta\ngamma")

            event = self._left_click_event(x=1, y=1)
            for _ in range(3):
                main_log.on_mouse_down(event)
            await pilot.pause()

            self.assertEqual(main_log.selected_text, "beta")

    async def test_non_quadruple_left_mouse_up_still_copies_selection(self) -> None:
        app = AgentCliApp()
        copied: list[str] = []
        app.copy_to_clipboard = lambda text: copied.append(text)

        async with app.run_test() as pilot:
            await pilot.pause()
            main_log = app.query_one("#main_log", TranscriptArea)
            main_log.load_text("alpha beta gamma")

            event = self._left_click_event(x=7, y=0)
            for _ in range(2):
                main_log.on_mouse_down(event)
            main_log.on_mouse_up(SimpleNamespace(button=1, stop=lambda: None, prevent_default=lambda: None))
            await pilot.pause()

            self.assertEqual(copied, ["beta"])

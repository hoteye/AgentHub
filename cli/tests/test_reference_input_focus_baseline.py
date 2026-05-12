from __future__ import annotations

import unittest
from types import SimpleNamespace

from cli.agent_cli.app import AgentCliApp, PromptComposer, TranscriptArea

class ReferenceInputFocusBaselineTest(unittest.IsolatedAsyncioTestCase):
    async def test_prompt_composer_keeps_initial_focus_baseline(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertIs(app.focused, app.query_one("#prompt_composer", PromptComposer))

    async def test_mouse_up_outside_composer_refocuses_input_baseline(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            main_log = app.query_one("#main_log", TranscriptArea)
            app.on_mouse_up(SimpleNamespace(button=1, widget=main_log))
            await pilot.pause()
            self.assertIs(app.focused, app.query_one("#prompt_composer", PromptComposer))

    async def test_transcript_copy_restores_focus_to_input_baseline(self) -> None:
        app = AgentCliApp()
        copied: list[str] = []
        app.copy_to_clipboard = lambda text: copied.append(text)

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            main_log = app.query_one("#main_log", TranscriptArea)
            main_log.load_text("› hello\n• world")
            main_log.selection = ((1, 2), (1, 7))

            main_log.on_mouse_up(SimpleNamespace(button=1))
            await pilot.pause()

            self.assertEqual(copied, ["world"])
            self.assertIs(app.focused, composer)

    async def test_transcript_double_right_click_copies_and_pastes_into_prompt(self) -> None:
        app = AgentCliApp()
        copied: list[str] = []
        app.copy_to_clipboard = lambda text: copied.append(text)

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            main_log = app.query_one("#main_log", TranscriptArea)
            main_log.load_text("› hello\n• world")
            main_log.selection = ((1, 2), (1, 7))
            event = SimpleNamespace(button=3, x=4, y=1)

            main_log.on_mouse_down(event)
            main_log.on_mouse_up(event)
            self.assertEqual(copied, ["world"])
            self.assertEqual(composer.text, "")

            main_log.on_mouse_down(event)
            main_log.on_mouse_up(event)
            await pilot.pause()

            self.assertEqual(copied, ["world"])
            self.assertEqual(composer.text, "world")
            self.assertIs(app.focused, composer)

    async def test_transcript_widget_renders_markdown_blocks_without_raw_fences(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app._write_assistant_reply("读取结果如下：\n\n```python\nprint('hi')\n```")
            await pilot.pause()

            main_log = app.query_one("#main_log", TranscriptArea)
            rendered_text = main_log.text

            self.assertIn("print('hi')", rendered_text)
            self.assertNotIn("```", rendered_text)
            self.assertFalse(any(ch in rendered_text for ch in "┏┗┃━"))

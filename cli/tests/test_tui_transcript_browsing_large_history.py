from __future__ import annotations

import unittest

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.ui.transcript_virtual_list import TranscriptVirtualList
from cli.agent_cli.ui.transcript_virtual_list_runtime import item_index_for_entry_id


class TuiTranscriptBrowsingLargeHistoryTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _materialize_viewport(transcript: TranscriptVirtualList) -> None:
        height = max(1, int(transcript.size.height or 1))
        transcript.render_line(0)
        transcript.render_line(height - 1)

    @staticmethod
    def _seed_large_history(
        app: AgentCliApp,
        *,
        turns: int,
        query_token: str,
        every: int,
        label: str,
    ) -> None:
        for index in range(turns):
            app._write_user_prompt(f"{label} question {index}")
            reply = f"{label} reply {index} " + ("detail " * 12)
            if index % every == 0:
                reply = f"{reply}{query_token}"
            app._write_assistant_reply(reply)

    @staticmethod
    def _seed_wrapped_history(app: AgentCliApp, *, turns: int) -> None:
        for index in range(turns):
            app._write_user_prompt(f"wrapped question {index}")
            app._write_assistant_reply(
                "\n".join(
                    [
                        f"wrapped assistant {index}:",
                        "- state transition handling remains synchronous in the UI layer",
                        "- transcript rendering keeps both raw text and visual lines around",
                        "- cache growth currently depends on viewed width and item signature",
                        "```python",
                        f"result_{index} = 'ok'",
                        "for item in range(30):",
                        "    print('detail detail detail detail detail detail detail detail detail detail')",
                        "```",
                        "final note: preserve exact output ordering.",
                    ]
                )
            )

    async def test_large_history_search_jump_and_resize_keep_active_match_visible(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.resize_terminal(140, 28)
            await pilot.pause()
            self._seed_large_history(
                app,
                turns=96,
                query_token="lane-d-needle",
                every=8,
                label="lane-d",
            )
            await pilot.pause()

            await pilot.press("ctrl+o")
            await pilot.pause()

            await pilot.press("ctrl+f")
            for char in "lane-d-needle":
                await pilot.press(char)
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("f3")
            await pilot.pause()
            await pilot.press("f3")
            await pilot.pause()

            state = app._transcript_browsing_state
            transcript = app.query_one("#transcript_log", TranscriptVirtualList)
            self._materialize_viewport(transcript)
            self.assertEqual(len(state.match_entry_ids), 12)
            active_entry_id = state.active_match_entry_id
            self.assertIsNotNone(active_entry_id)
            self.assertEqual(transcript._active_highlighted_entry_id, active_entry_id)

            active_item_index = item_index_for_entry_id(transcript._display_items, active_entry_id or "")
            self.assertIsNotNone(active_item_index)
            self.assertGreater(transcript.scroll_y, 0)
            self.assertGreater(transcript.visible_range[1], transcript.visible_range[0])
            self.assertIn(active_item_index, range(*transcript.visible_range))

            await pilot.resize_terminal(84, 18)
            await pilot.pause()
            self._materialize_viewport(transcript)

            resized_state = app._transcript_browsing_state
            resized_item_index = item_index_for_entry_id(transcript._display_items, resized_state.active_match_entry_id or "")
            self.assertEqual(resized_state.query, "lane-d-needle")
            self.assertEqual(resized_state.active_match_entry_id, active_entry_id)
            self.assertEqual(transcript._active_highlighted_entry_id, active_entry_id)
            self.assertIsNotNone(resized_item_index)
            self.assertIn(resized_item_index, range(*transcript.visible_range))

    async def test_large_history_search_ignores_post_freeze_entries_until_reopen(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.resize_terminal(120, 24)
            await pilot.pause()
            self._seed_large_history(
                app,
                turns=72,
                query_token="frozen-needle",
                every=24,
                label="frozen",
            )
            await pilot.pause()

            await pilot.press("ctrl+o")
            await pilot.pause()
            await pilot.press("ctrl+f")
            for char in "frozen-needle":
                await pilot.press(char)
            await pilot.press("enter")
            await pilot.pause()

            transcript = app.query_one("#transcript_log", TranscriptVirtualList)
            initial_match_ids = tuple(app._transcript_browsing_state.match_entry_ids)
            self.assertEqual(len(initial_match_ids), 3)

            for index in range(72, 77):
                app._write_user_prompt(f"late frozen question {index}")
                app._write_assistant_reply(f"late frozen reply {index} frozen-needle")
            await pilot.pause()

            self.assertNotIn("late frozen question 72", transcript.text)
            self.assertNotIn("late frozen reply 72", transcript.text)
            self.assertEqual(tuple(app._transcript_browsing_state.match_entry_ids), initial_match_ids)

            await pilot.press("f3")
            await pilot.pause()
            self.assertIn(app._transcript_browsing_state.active_match_entry_id, initial_match_ids)

            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("ctrl+o")
            await pilot.pause()

            refreshed_state = app._transcript_browsing_state
            refreshed_transcript = app.query_one("#transcript_log", TranscriptVirtualList)
            self.assertEqual(refreshed_state.query, "frozen-needle")
            self.assertGreater(len(refreshed_state.match_entry_ids), len(initial_match_ids))
            self.assertIn("late frozen question 72", refreshed_transcript.text)
            self.assertIn("late frozen reply 72", refreshed_transcript.text)

    async def test_large_history_reenter_transcript_restores_active_search_match(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.resize_terminal(120, 24)
            await pilot.pause()
            self._seed_large_history(
                app,
                turns=80,
                query_token="persistent-needle",
                every=20,
                label="persistent",
            )
            await pilot.pause()

            await pilot.press("ctrl+o")
            await pilot.pause()
            await pilot.press("ctrl+f")
            for char in "persistent-needle":
                await pilot.press(char)
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("f3")
            await pilot.pause()

            transcript = app.query_one("#transcript_log", TranscriptVirtualList)
            self._materialize_viewport(transcript)
            active_entry_id = app._transcript_browsing_state.active_match_entry_id
            active_item_index = item_index_for_entry_id(transcript._display_items, active_entry_id or "")
            self.assertIsNotNone(active_entry_id)
            self.assertIsNotNone(active_item_index)
            self.assertIn(active_item_index, range(*transcript.visible_range))

            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("ctrl+o")
            await pilot.pause()

            reopened_state = app._transcript_browsing_state
            reopened_transcript = app.query_one("#transcript_log", TranscriptVirtualList)
            self._materialize_viewport(reopened_transcript)
            reopened_item_index = item_index_for_entry_id(
                reopened_transcript._display_items,
                reopened_state.active_match_entry_id or "",
            )
            self.assertEqual(reopened_state.query, "persistent-needle")
            self.assertEqual(reopened_state.active_match_entry_id, active_entry_id)
            self.assertEqual(reopened_transcript._active_highlighted_entry_id, active_entry_id)
            self.assertIsNotNone(reopened_item_index)
            self.assertIn(reopened_item_index, range(*reopened_transcript.visible_range))

    async def test_large_history_virtual_list_caches_stay_bounded_to_recent_windows_and_widths(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.resize_terminal(80, 16)
            await pilot.pause()
            self._seed_wrapped_history(app, turns=60)
            await pilot.pause()

            await pilot.press("ctrl+o")
            await pilot.pause()

            transcript = app.query_one("#transcript_log", TranscriptVirtualList)
            for width, height in ((80, 16), (64, 14), (100, 18)):
                await pilot.resize_terminal(width, height)
                await pilot.pause()
                for item_index in range(0, len(transcript._display_items), 4):
                    transcript.scroll_to_item_index(item_index, align="start")
                    await pilot.pause()
                    self._materialize_viewport(transcript)

            self.assertLessEqual(len(transcript._render_cache), 96)
            self.assertLessEqual(len(transcript._measured_heights), 128)

from __future__ import annotations

import unittest

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.models import ActivityEvent
from cli.agent_cli.ui.transcript_history import TranscriptEntry, assistant_message_entry, user_message_entry
from cli.agent_cli.ui.transcript_browsing_runtime import TranscriptBrowsingState
from cli.agent_cli.ui.transcript_virtual_list import TranscriptVirtualList
from cli.agent_cli.ui.transcript_screen_projection_runtime import build_prompt_projection
from cli.agent_cli.ui.widgets import TranscriptArea
from textual.widgets import Static


class PromptTranscriptProjectionTests(unittest.TestCase):
    def test_prompt_projection_keeps_user_and_assistant_history_visible(self) -> None:
        entries = [
            user_message_entry("inspect this flow"),
            TranscriptEntry(
                kind="activity",
                layer="tool",
                lines=["• Running rg foo"],
                status="running",
                render_mode="tool_command",
            ),
            TranscriptEntry(
                kind="activity",
                layer="tool",
                lines=["• Ran rg bar"],
                status="success",
                render_mode="tool_command",
            ),
            assistant_message_entry("I found the issue."),
        ]

        projected = build_prompt_projection(entries)

        self.assertEqual(projected[0].kind, "user")
        self.assertEqual(projected[1].render_mode, "prompt_tool_group")
        self.assertEqual(projected[2].kind, "assistant")
        self.assertIn("searched", projected[1].lines[0].lower())

    def test_prompt_projection_does_not_group_non_tool_history(self) -> None:
        entries = [
            user_message_entry("first"),
            assistant_message_entry("answer one"),
            assistant_message_entry("answer two"),
        ]

        projected = build_prompt_projection(entries)

        self.assertEqual(len(projected), 3)
        self.assertEqual([entry.kind for entry in projected], ["user", "assistant", "assistant"])

    def test_prompt_projection_groups_only_same_tool_noise_kind(self) -> None:
        entries = [
            TranscriptEntry(
                kind="activity",
                layer="tool",
                lines=["• Ran cat app.py"],
                status="success",
                render_mode="tool_command",
                entry_id="entry:1",
            ),
            TranscriptEntry(
                kind="activity",
                layer="tool",
                lines=["• Ran sed -n '1,20p' config.py"],
                status="success",
                render_mode="tool_command",
                entry_id="entry:2",
            ),
            TranscriptEntry(
                kind="activity",
                layer="tool",
                lines=["• Running rg prompt"],
                status="running",
                render_mode="tool_command",
                entry_id="entry:3",
            ),
            TranscriptEntry(
                kind="activity",
                layer="tool",
                lines=["• Running rg transcript"],
                status="running",
                render_mode="tool_command",
                entry_id="entry:4",
            ),
        ]

        projected = build_prompt_projection(entries)

        self.assertEqual(len(projected), 2)
        self.assertEqual([entry.render_mode for entry in projected], ["prompt_tool_group", "prompt_tool_group"])
        self.assertEqual(projected[0].group_key, "read")
        self.assertEqual(projected[1].group_key, "search")
        self.assertEqual(projected[0].child_entry_ids, ("entry:1", "entry:2"))
        self.assertEqual(projected[1].child_entry_ids, ("entry:3", "entry:4"))
        self.assertTrue(projected[0].lines[0].startswith("• Read "))
        self.assertTrue(projected[1].lines[0].startswith("• Searched "))

    def test_prompt_projection_labels_native_web_search_groups_explicitly_and_uses_query_summary(self) -> None:
        entries = [
            TranscriptEntry(
                kind="activity",
                layer="web",
                lines=["• Native web search", "  └ 北京 明天天气"],
                status="success",
                render_mode="web_search",
                entry_id="entry:web:1",
            ),
            TranscriptEntry(
                kind="activity",
                layer="web",
                lines=["• Native web search", "  └ 北京 后天天气"],
                status="success",
                render_mode="web_search",
                entry_id="entry:web:2",
            ),
        ]

        projected = build_prompt_projection(entries)

        self.assertEqual(len(projected), 1)
        self.assertEqual(projected[0].group_key, "native_web_search")
        self.assertEqual(projected[0].lines[0], "• Native web search (2 updates)")
        self.assertEqual(projected[0].lines[1], "  └ 北京 明天天气")

    def test_prompt_projection_keeps_approval_entries_visible(self) -> None:
        entries = [
            TranscriptEntry(
                kind="activity",
                layer="tool",
                lines=["• Running rg approval"],
                status="running",
                render_mode="tool_command",
                entry_id="entry:10",
            ),
            TranscriptEntry(
                kind="activity",
                layer="tool",
                lines=["• Approval required"],
                status="info",
                render_mode="plain",
                entry_id="entry:11",
            ),
            TranscriptEntry(
                kind="activity",
                layer="tool",
                lines=["• Running rg decision"],
                status="running",
                render_mode="tool_command",
                entry_id="entry:12",
            ),
        ]

        projected = build_prompt_projection(entries)

        self.assertEqual(len(projected), 3)
        self.assertEqual(projected[1].entry_id, "entry:11")
        self.assertEqual(projected[1].lines[0], "• Approval required")


class PromptTranscriptScreenTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _static_plain(widget: Static) -> str:
        renderable = widget.renderable
        return renderable.plain if hasattr(renderable, "plain") else str(renderable)

    async def test_ctrl_o_toggles_transcript_screen_and_hides_composer(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app._write_user_prompt("hello")
            app._write_activity_event(
                ActivityEvent(
                    title="Running rg hello",
                    status="running",
                    kind="command",
                    detail="",
                    code="command.run",
                    params={"command": "rg hello"},
                )
            )
            app._write_activity_event(
                ActivityEvent(
                    title="Ran cat app.py",
                    status="success",
                    kind="command",
                    detail="",
                    code="command.run",
                    params={"command": "cat app.py"},
                )
            )
            app._write_assistant_reply("done")
            await pilot.pause()

            self.assertEqual(app._screen_mode, "prompt")
            self.assertEqual(app.query_one("#composer_shell").styles.display, "block")
            self.assertIn("Tool activity", app.query_one("#main_log").text)
            self.assertEqual(app.query_one("#transcript_log", TranscriptVirtualList).styles.display, "none")

            await pilot.press("ctrl+o")
            await pilot.pause()

            self.assertEqual(app._screen_mode, "transcript")
            self.assertEqual(app.query_one("#composer_shell").styles.display, "none")
            self.assertEqual(app.query_one("#main_log").styles.display, "none")
            self.assertEqual(app.query_one("#transcript_log", TranscriptVirtualList).styles.display, "block")
            self.assertIn("ctrl+o", self._static_plain(app.query_one("#composer_footer", Static)).lower())
            self.assertIn("• Running rg hello", app.query_one("#transcript_log", TranscriptVirtualList).text)

            await pilot.press("escape")
            await pilot.pause()

            self.assertEqual(app._screen_mode, "prompt")
            self.assertEqual(app.query_one("#composer_shell").styles.display, "block")
            self.assertEqual(app.query_one("#transcript_log", TranscriptVirtualList).styles.display, "none")

    async def test_transcript_virtual_list_scrolls_independently(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            for index in range(40):
                app._write_user_prompt(f"prompt {index}")
                app._write_assistant_reply(f"assistant reply {index} " + ("detail " * 12))
            await pilot.pause()

            await pilot.press("ctrl+o")
            await pilot.pause()

            transcript = app.query_one("#transcript_log", TranscriptVirtualList)
            self.assertGreater(transcript.virtual_size.height, transcript.size.height)
            self.assertGreater(transcript.visible_range[1], transcript.visible_range[0])

            await pilot.press("home")
            await pilot.pause()
            self.assertEqual(transcript.visible_range[0], 0)

            await pilot.press("pagedown")
            await pilot.pause()
            self.assertGreater(transcript.visible_range[0], 0)

    async def test_transcript_screen_freezes_snapshot_until_exit(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app._write_user_prompt("before freeze")
            app._write_assistant_reply("visible in transcript")
            await pilot.pause()

            await pilot.press("ctrl+o")
            await pilot.pause()

            main_log = app.query_one("#main_log", TranscriptArea)
            transcript = app.query_one("#transcript_log", TranscriptVirtualList)
            frozen_text = transcript.text
            self.assertEqual(main_log.text, "")
            self.assertEqual(getattr(main_log, "_loaded_transcript_lines", None), [])

            app._write_user_prompt("after freeze")
            app._write_assistant_reply("should stay hidden")
            await pilot.pause()

            self.assertEqual(main_log.text, "")
            self.assertEqual(transcript.text, frozen_text)
            self.assertNotIn("after freeze", transcript.text)
            self.assertNotIn("should stay hidden", transcript.text)

            await pilot.press("escape")
            await pilot.pause()

            self.assertIn("after freeze", app.query_one("#main_log").text)
            self.assertIn("should stay hidden", app.query_one("#main_log").text)

            await pilot.press("ctrl+o")
            await pilot.pause()

            self.assertIn("after freeze", app.query_one("#transcript_log", TranscriptVirtualList).text)
            self.assertIn("should stay hidden", app.query_one("#transcript_log", TranscriptVirtualList).text)

    async def test_transcript_browsing_state_searches_snapshot_and_highlights_active_entry(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            for index in range(12):
                app._write_user_prompt(f"prompt {index}")
                app._write_assistant_reply(f"assistant reply {index} searchable-token")
            app._transcript_browsing_state = TranscriptBrowsingState(query="reply 9")
            await pilot.pause()

            await pilot.press("ctrl+o")
            await pilot.pause()

            transcript = app.query_one("#transcript_log", TranscriptVirtualList)
            state = app._transcript_browsing_state
            self.assertEqual(state.query, "reply 9")
            self.assertEqual(len(state.match_entry_ids), 1)
            self.assertEqual(state.active_match_entry_id, state.match_entry_ids[0])
            self.assertIn(state.active_match_entry_id, transcript._highlighted_entry_ids)
            self.assertEqual(transcript._active_highlighted_entry_id, state.active_match_entry_id)

    async def test_transcript_virtual_list_scroll_to_entry_and_item_index(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            for index in range(30):
                app._write_user_prompt(f"prompt {index}")
                app._write_assistant_reply(f"assistant reply {index} " + ("detail " * 10))
            await pilot.pause()

            await pilot.press("ctrl+o")
            await pilot.pause()

            transcript = app.query_one("#transcript_log", TranscriptVirtualList)
            target_entry = app._transcript_screen_snapshot_entries[-1]
            self.assertTrue(transcript.scroll_to_entry(target_entry.entry_id, align="end"))
            await pilot.pause()
            self.assertGreater(transcript.scroll_y, 0)
            self.assertTrue(transcript.scroll_to_item_index(0, align="start"))
            await pilot.pause()
            self.assertEqual(transcript.scroll_y, 0)
            self.assertFalse(transcript.scroll_to_entry("missing-entry-id"))

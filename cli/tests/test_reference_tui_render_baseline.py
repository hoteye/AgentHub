from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic

from rich.color import Color as RichColor
from textual.color import Color
from textual.widgets import Static

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.models import ActivityEvent, PromptAttachment
from cli.agent_cli.ui import live_turn_controller_helpers as live_turn_controller_helpers_service
from cli.agent_cli.ui.composer import PromptComposer
from cli.agent_cli.ui.runtime_bridge import FallbackRuntime
from cli.agent_cli.ui.status_indicator import (
    IdleCatAnimator,
    build_idle_status_text,
    build_status_indicator_text,
    fmt_elapsed_compact,
)
from cli.agent_cli.ui.status_line_summary_runtime import build_provider_summary_text
from cli.agent_cli.ui.transcript_history import (
    COMPLETION_TIME_STYLE,
    MARKDOWN_BLOCKQUOTE_STYLE,
    MARKDOWN_CODE_STYLE,
    MARKDOWN_EMPHASIS_STYLE,
    MARKDOWN_H1_STYLE,
    MARKDOWN_LINK_STYLE,
    MARKDOWN_ORDERED_LIST_MARKER_STYLE,
    MARKDOWN_STRONG_STYLE,
    MARKDOWN_SYNTAX_COMMENT_STYLE,
    MARKDOWN_SYNTAX_KEYWORD_STYLE,
    MARKDOWN_SYNTAX_STRING_STYLE,
    REASONING_TEXT_STYLE,
    USER_IMAGE_STYLE,
    USER_PREFIX_STYLE,
    USER_TEXT_STYLE,
    assistant_message_entry,
    final_separator_entry,
    reasoning_message_entry,
    render_transcript_visual_entries,
    user_message_entry,
)
from cli.agent_cli.ui.widgets import TranscriptArea

_IDLE_CAT_FRAMES = {"~=(^.^)=3", "3=(^.^)=~"}


class ReferenceTuiRenderBaselineTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _static_plain(widget: Static) -> str:
        renderable = getattr(widget, "renderable", None)
        if renderable is not None:
            return getattr(renderable, "plain", str(renderable))
        rendered = widget.render()
        if hasattr(rendered, "renderable"):
            inner = rendered.renderable
            return getattr(inner, "plain", str(inner))
        return getattr(rendered, "plain", str(rendered))

    @staticmethod
    def _assert_enhanced_status_line(
        rendered: str, header: str, interrupt_suffix: str = "to interrupt"
    ) -> None:
        assert rendered
        assert rendered[0] in {"•", "●", "◦"}
        assert f" {header} (" in rendered
        assert f"esc {interrupt_suffix}" in rendered

    @staticmethod
    def _idle_cat_offset(rendered: str) -> int:
        for frame in _IDLE_CAT_FRAMES:
            index = rendered.find(frame)
            if index >= 0:
                return index
        raise AssertionError(f"Idle cat frame not found in {rendered!r}")

    def test_status_indicator_elapsed_format_matches_reference_compact_copy(self) -> None:
        self.assertEqual(fmt_elapsed_compact(0), "0s")
        self.assertEqual(fmt_elapsed_compact(61), "1m 01s")
        self.assertEqual(fmt_elapsed_compact(3661), "1h 01m 01s")

    def test_status_indicator_text_keeps_reference_plain_copy_and_animates_header_styles(
        self,
    ) -> None:
        first = build_status_indicator_text("Working", width=80, started_at=100.0, now=100.0)
        second = build_status_indicator_text("Working", width=80, started_at=100.0, now=101.0)

        self.assertEqual(first.plain, "• Working (0s • esc to interrupt)")
        self.assertEqual(second.plain, "• Working (1s • esc to interrupt)")
        self.assertNotEqual(
            [(span.start, span.end, span.style) for span in first.spans],
            [(span.start, span.end, span.style) for span in second.spans],
        )

    def test_enhanced_status_indicator_pulses_prefix_and_adds_long_running_hint(self) -> None:
        first = build_status_indicator_text(
            "Working", width=80, started_at=100.0, now=100.0, enhanced=True
        )
        second = build_status_indicator_text(
            "Working", width=80, started_at=100.0, now=100.18, enhanced=True
        )
        waiting = build_status_indicator_text(
            "Working", width=80, started_at=100.0, now=105.0, enhanced=True
        )

        self.assertEqual(first.plain, "• Working (0s • esc to interrupt)")
        self.assertEqual(second.plain, "● Working (0s • esc to interrupt)")
        self._assert_enhanced_status_line(waiting.plain, "Working")
        self.assertTrue(waiting.plain.endswith("· still working"))

    def test_idle_status_indicator_walks_cat_back_and_forth(self) -> None:
        animator = IdleCatAnimator()
        animator.rng.seed(7)
        samples = [
            build_idle_status_text(width=40, animator=animator, now=index * 0.5).plain
            for index in range(20)
        ]
        offsets = [self._idle_cat_offset(sample) for sample in samples]
        stripped = {sample.strip() for sample in samples}

        self.assertTrue(stripped <= _IDLE_CAT_FRAMES)
        self.assertGreater(len(set(offsets)), 4)
        self.assertGreater(max(offsets), 20)
        self.assertLess(min(offsets), 10)
        self.assertGreater(len(stripped), 1)

    def test_idle_status_indicator_ignores_mouse_when_not_touching_cat(self) -> None:
        baseline = IdleCatAnimator()
        baseline.rng.seed(11)
        baseline.position = 10
        baseline.direction = 1
        baseline.next_move_at = 0.0

        untouched = IdleCatAnimator()
        untouched.rng.seed(11)
        untouched.position = 10
        untouched.direction = 1
        untouched.next_move_at = 0.0

        untouched.observe_mouse(x=35, width=40, now=0.0)

        baseline_render = build_idle_status_text(width=40, animator=baseline, now=0.5).plain
        untouched_render = build_idle_status_text(width=40, animator=untouched, now=0.5).plain

        self.assertEqual(untouched_render, baseline_render)

    def test_idle_status_indicator_reacts_only_when_mouse_touches_cat(self) -> None:
        animator = IdleCatAnimator()
        animator.rng.seed(17)
        animator.position = 10
        animator.direction = 1
        animator.next_move_at = 0.0

        triggered = animator.observe_mouse(x=12, width=40, now=0.0)
        reacted = build_idle_status_text(width=40, animator=animator, now=0.4).plain
        reacted_offset = self._idle_cat_offset(reacted)

        self.assertTrue(triggered)
        self.assertIn(reacted.strip(), _IDLE_CAT_FRAMES)
        self.assertGreater(reacted_offset, 10)

    def test_prompt_composer_uses_reference_chevron_prefix(self) -> None:
        composer = PromptComposer("hello")

        self.assertEqual(composer._prompt_prefix(40), "› ")
        self.assertEqual(composer.build_render_text(40, focused=True).plain, "› hello ")

    def test_prompt_composer_empty_state_uses_reference_style_placeholder(self) -> None:
        composer = PromptComposer("")

        self.assertEqual(
            composer.build_render_text(48, focused=False).plain,
            "› Ask AgentHub to do anything",
        )

    def test_prompt_composer_focused_empty_state_keeps_placeholder_position_like_reference(
        self,
    ) -> None:
        composer = PromptComposer("")

        rendered = composer.build_render_text(48, focused=True)

        self.assertEqual(rendered.plain, "› Ask AgentHub to do anything")
        reverse_spans = [
            (span.start, span.end) for span in rendered.spans if "reverse" in str(span.style)
        ]
        self.assertEqual(reverse_spans, [(2, 3)])

    def test_prompt_composer_renders_local_image_reference_as_reference_placeholder(self) -> None:
        composer = PromptComposer('@"/tmp/cat.png"')

        self.assertEqual(
            composer.build_render_text(48, focused=False).plain,
            "› [Image #1]",
        )

    def test_prompt_composer_keeps_text_after_image_placeholder_like_reference(self) -> None:
        composer = PromptComposer('@"/tmp/cat.png" describe this image')

        self.assertEqual(
            composer.build_render_text(64, focused=False).plain,
            "› [Image #1] describe this image",
        )

    def test_user_message_entry_uses_reference_chevron_prefix(self) -> None:
        rendered = render_transcript_visual_entries([user_message_entry("hello")], width=32)

        self.assertEqual(rendered.lines, ["› hello"])

    def test_user_message_entry_renders_reference_image_placeholders_before_prompt(self) -> None:
        rendered = render_transcript_visual_entries(
            [
                user_message_entry(
                    '@"/tmp/cat.png" @"/tmp/dog.jpg" describe both',
                    attachments=[
                        PromptAttachment(path="/tmp/cat.png", name="cat.png", extension="png"),
                        PromptAttachment(path="/tmp/dog.jpg", name="dog.jpg", extension="jpg"),
                    ],
                )
            ],
            width=48,
        )

        self.assertEqual(
            rendered.lines,
            [
                "  [Image #1]",
                "  [Image #2]",
                "",
                "› describe both",
            ],
        )
        self.assertIn((0, len(rendered.lines[0]), USER_TEXT_STYLE), rendered.line_styles[0])
        self.assertIn((2, len(rendered.lines[0]), USER_IMAGE_STYLE), rendered.line_styles[0])

    def test_user_message_entry_uses_reference_style_surface_background(self) -> None:
        rendered = render_transcript_visual_entries([user_message_entry("hello")], width=32)

        self.assertIn((0, len(rendered.lines[0]), USER_TEXT_STYLE), rendered.line_styles[0])
        self.assertIn((0, 2, USER_PREFIX_STYLE), rendered.line_styles[0])
        self.assertIsNotNone(USER_TEXT_STYLE.bgcolor)
        self.assertEqual(USER_TEXT_STYLE.bgcolor, USER_PREFIX_STYLE.bgcolor)

    def test_completion_time_line_uses_status_theme_tinted_background(self) -> None:
        rendered = render_transcript_visual_entries(
            [assistant_message_entry("done\n🏁 18:13 ⌛ 8s")],
            width=48,
        )

        self.assertEqual(rendered.lines, ["• done", "🏁 18:13 ⌛ 8s"])
        self.assertIn((0, len(rendered.lines[1]), COMPLETION_TIME_STYLE), rendered.line_styles[1])
        self.assertIsNotNone(COMPLETION_TIME_STYLE.bgcolor)

    def test_final_separator_label_supports_multiple_locales(self) -> None:
        app_zh = AgentCliApp(language="zh-CN")
        app_en = AgentCliApp(language="en")

        self.assertEqual(
            live_turn_controller_helpers_service.final_separator_label(
                t_fn=app_zh._t,
                completion_time="15:49",
                elapsed="12s",
            ),
            "完成15:49，用时12s",
        )
        self.assertEqual(
            live_turn_controller_helpers_service.final_separator_label(
                t_fn=app_en._t,
                completion_time="15:49",
                elapsed="12s",
            ),
            "Done 15:49, took 12s",
        )

    def test_transcript_markdown_render_matches_reference_plain_blocks(self) -> None:
        rendered = render_transcript_visual_entries(
            [
                assistant_message_entry(
                    "\n\n    -- Indented code block (4 spaces)\n    SELECT *\n\n```sh\nprintf 'hi\\n'\n```"
                )
            ],
            width=64,
        )

        self.assertEqual(
            rendered.lines,
            [
                "•     -- Indented code block (4 spaces)",
                "      SELECT *",
                "  ",
                "  printf 'hi\\n'",
            ],
        )

    def test_transcript_markdown_plain_code_blocks_do_not_use_inline_code_color(self) -> None:
        rendered = render_transcript_visual_entries(
            [assistant_message_entry("```\nplain text\n```")],
            width=64,
        )

        self.assertEqual(rendered.lines, ["• plain text"])
        self.assertNotIn((2, len(rendered.lines[0]), MARKDOWN_CODE_STYLE), rendered.line_styles[0])

    def test_transcript_markdown_fenced_code_uses_reference_style_syntax_highlight(self) -> None:
        rendered = render_transcript_visual_entries(
            [
                assistant_message_entry(
                    '```python title="demo"\n# note\nif count == 1:\n    return "hi"\n```'
                )
            ],
            width=80,
        )

        self.assertEqual(
            rendered.lines,
            [
                "• # note",
                "  if count == 1:",
                '      return "hi"',
            ],
        )

        comment_line = rendered.lines[0]
        string_line = rendered.lines[2]

        self.assertIn(
            (2, len(comment_line), MARKDOWN_SYNTAX_COMMENT_STYLE), rendered.line_styles[0]
        )
        self.assertIn((2, 4, MARKDOWN_SYNTAX_KEYWORD_STYLE), rendered.line_styles[1])

        string_start = string_line.index('"hi"')
        self.assertIn(
            (string_start, string_start + len('"hi"'), MARKDOWN_SYNTAX_STRING_STYLE),
            rendered.line_styles[2],
        )

    def test_transcript_markdown_colors_bold_and_code_differently(self) -> None:
        rendered = render_transcript_visual_entries(
            [assistant_message_entry("普通文本 **加粗** 和 `code_sample`")],
            width=64,
        )

        self.assertEqual(rendered.lines, ["• 普通文本 加粗 和 code_sample"])
        line = rendered.lines[0]
        line_styles = rendered.line_styles[0]
        bold_start = line.index("加粗")
        code_start = line.index("code_sample")

        self.assertIn((bold_start, bold_start + 2, MARKDOWN_STRONG_STYLE), line_styles)
        self.assertIn(
            (code_start, code_start + len("code_sample"), MARKDOWN_CODE_STYLE), line_styles
        )
        self.assertTrue(MARKDOWN_STRONG_STYLE.bold)
        self.assertIsNone(MARKDOWN_STRONG_STYLE.color)
        self.assertIsNotNone(MARKDOWN_CODE_STYLE.color)

    def test_transcript_markdown_matches_reference_heading_quote_link_and_marker_styles(
        self,
    ) -> None:
        rendered = render_transcript_visual_entries(
            [
                assistant_message_entry(
                    "# 标题\n\n> 引用\n\n1. one\n\n*italic* [docs](https://a.com)"
                )
            ],
            width=80,
        )

        self.assertEqual(
            rendered.lines,
            [
                "• # 标题",
                "  ",
                "  > 引用",
                "  ",
                "  1. one",
                "  ",
                "  italic docs (https://a.com)",
            ],
        )

        heading_line = rendered.lines[0]
        quote_line = rendered.lines[2]
        inline_line = rendered.lines[6]

        self.assertIn((2, len(heading_line), MARKDOWN_H1_STYLE), rendered.line_styles[0])
        self.assertIn((2, len(quote_line), MARKDOWN_BLOCKQUOTE_STYLE), rendered.line_styles[2])
        self.assertIn((2, 5, MARKDOWN_ORDERED_LIST_MARKER_STYLE), rendered.line_styles[4])

        italic_start = inline_line.index("italic")
        href_start = inline_line.index("https://a.com")
        self.assertIn(
            (italic_start, italic_start + len("italic"), MARKDOWN_EMPHASIS_STYLE),
            rendered.line_styles[6],
        )
        self.assertIn(
            (href_start, href_start + len("https://a.com"), MARKDOWN_LINK_STYLE),
            rendered.line_styles[6],
        )

    def test_reasoning_summary_renders_as_dim_italic_reference_style_block(self) -> None:
        rendered = render_transcript_visual_entries(
            [reasoning_message_entry("先检查目录，再决定是否调用工具。")],
            width=64,
        )

        self.assertEqual(rendered.lines, ["• 先检查目录，再决定是否调用工具。"])
        self.assertIn((2, len(rendered.lines[0]), REASONING_TEXT_STYLE), rendered.line_styles[0])

    def test_final_separator_renders_as_reference_rule(self) -> None:
        rendered = render_transcript_visual_entries(
            [final_separator_entry()],
            width=40,
        )

        self.assertEqual(rendered.lines, ["────────────────────────────────────────"])

    async def test_transcript_widget_renders_exact_width_separator_without_trailing_space(
        self,
    ) -> None:
        app = AgentCliApp(language="zh-CN")

        async with app.run_test() as pilot:
            await pilot.pause()
            app._write_activity_event(
                ActivityEvent(
                    title="Explored",
                    status="success",
                    kind="tool",
                    detail="List .",
                )
            )
            app._write_assistant_reply("done")
            await pilot.pause()

            main_log = app.query_one("#main_log", TranscriptArea)
            separator_y = next(
                index
                for index, line in enumerate(main_log.document.lines)
                if "────────────────" in line
            )
            strip = main_log.render_line(separator_y)

            self.assertFalse(strip.text.endswith(" "))
            self.assertEqual(strip.text, str(main_log.document[separator_y]))

    async def test_app_transcript_widget_renders_reference_plain_markdown_blocks(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app._write_assistant_reply("# Title\n\n- one\n- two\n\n```python\nprint('hi')\n```")
            await pilot.pause()

            main_log = app.query_one("#main_log")
            rendered_text = main_log.text

            self.assertIn("• # Title", rendered_text)
            self.assertIn("  - one", rendered_text)
            self.assertIn("  print('hi')", rendered_text)
            self.assertNotIn("```", rendered_text)
            self.assertFalse(any(ch in rendered_text for ch in "┏┗┃━"))

    async def test_app_bottom_dock_uses_reference_style_status_and_footer_layout(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            status_line = app.query_one("#status_line", Static)
            footer = app.query_one("#composer_footer", Static)
            composer = app.query_one("#prompt_composer", PromptComposer)

            self.assertNotIn(app._t("footer.shortcuts"), self._static_plain(status_line))
            self.assertEqual(status_line.styles.background, Color.parse(app._theme.info_surface_bg))
            self.assertEqual(footer.styles.background, Color.parse(app._theme.info_surface_bg))
            self.assertIn(app._t("footer.context_left"), self._static_plain(footer))
            self.assertIn(
                app._t("composer.placeholder"), composer.build_render_text(80, focused=False).plain
            )

            app._idle_status_started_at = monotonic() - app.IDLE_STATUS_DELAY_SECONDS - 1.0
            app._refresh_dynamic_hint()
            await pilot.pause()

            self.assertNotIn(app._t("footer.shortcuts"), self._static_plain(status_line))

    async def test_app_status_line_stays_empty_when_thread_context_exists(self) -> None:
        runtime = FallbackRuntime()
        runtime.thread_id = "27a33bd1fe264ee0aedb17dec9dca7d2"
        runtime.thread_name = "resume current task"
        runtime.history_turns = [
            {
                "user_text": "继续刚才的任务",
                "assistant_text": "已恢复上下文",
            }
        ]

        with TemporaryDirectory() as tmpdir:
            runtime.cwd = Path(tmpdir) / "workspace-demo"
            runtime.cwd.mkdir(parents=True, exist_ok=True)
            app = AgentCliApp(runtime=runtime)

            async with app.run_test() as pilot:
                await pilot.pause()

                status_line = app.query_one("#status_line", Static)
                footer = app.query_one("#composer_footer", Static)
                status_text = self._static_plain(status_line)
                footer_text = self._static_plain(footer)

                self.assertEqual(status_text, "")
                self.assertNotIn("resume current task", status_text)
                self.assertIn("workspace-demo", footer_text)
                self.assertNotIn("fallback", footer_text)
                self.assertNotIn(app._t("footer.shortcuts"), footer_text)
                self.assertIn(app._t("footer.context_left"), footer_text)

    async def test_queue_dominant_hint_overrides_passive_summary_when_busy_with_draft(self) -> None:
        runtime = FallbackRuntime()
        runtime.thread_id = "27a33bd1fe264ee0aedb17dec9dca7d2"
        runtime.thread_name = "resume current task"
        runtime.history_turns = [
            {
                "user_text": "继续刚才的任务",
                "assistant_text": "已恢复上下文",
            }
        ]

        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("finish queued follow-up")
            app._set_busy(True)
            await pilot.pause()

            status_line = app.query_one("#status_line", Static)
            footer = app.query_one("#composer_footer", Static)
            status_text = self._static_plain(status_line)
            footer_text = self._static_plain(footer)

            self.assertIn(app._t("status.working"), status_text)
            self.assertNotIn(app._t("footer.queue_message"), status_text)
            self.assertNotIn("resume current task", status_text)
            self.assertIn(app._t("footer.context_left"), footer_text)
            self.assertIn(app._t("footer.queue_message"), footer_text)

    async def test_quit_confirm_overrides_passive_summary_for_resumed_session(self) -> None:
        runtime = FallbackRuntime()
        runtime.thread_id = "27a33bd1fe264ee0aedb17dec9dca7d2"
        runtime.thread_name = "resume current task"
        runtime.history_turns = [{"user_text": "继续", "assistant_text": "已恢复"}]
        app = AgentCliApp(runtime=runtime)
        app.QUIT_SHORTCUT_TIMEOUT_SECONDS = 30.0

        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_ctrl_c()
            await pilot.pause()

            status_line = app.query_one("#status_line", Static)

            self.assertEqual(self._static_plain(status_line), f"• {app._t('status.quit_confirm')}")
            self.assertNotIn("resume current task", self._static_plain(status_line))

    async def test_app_footer_uses_reference_queue_hint_when_busy_with_draft(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("Summarize recent commits")
            app._set_busy(True)
            await pilot.pause()

            status_line = app.query_one("#status_line", Static)
            footer = app.query_one("#composer_footer", Static)

            self.assertIn(app._t("status.working"), self._static_plain(status_line))
            self.assertNotIn(app._t("footer.queue_message"), self._static_plain(status_line))
            self.assertIn(app._t("footer.queue_message"), self._static_plain(footer))
            self.assertIn(app._t("footer.context_left"), self._static_plain(footer))

    async def test_app_footer_hides_queue_hint_when_busy_slash_is_not_queueable(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("/theme light")
            app._set_busy(True)
            await pilot.pause()

            status_line = app.query_one("#status_line", Static)
            footer = app.query_one("#composer_footer", Static)

            self.assertNotIn(app._t("footer.queue_message"), self._static_plain(status_line))
            self.assertNotIn(app._t("footer.queue_message"), self._static_plain(footer))

    async def test_app_footer_hides_shortcuts_while_typing_when_idle_like_reference(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("draft reply")
            await pilot.pause()

            status_line = app.query_one("#status_line", Static)
            footer = app.query_one("#composer_footer", Static)

            self.assertEqual(self._static_plain(status_line), "")
            self.assertNotIn(app._t("footer.shortcuts"), self._static_plain(footer))
            self.assertIn(app._t("footer.context_left"), self._static_plain(footer))

    async def test_app_prompt_input_echo_remains_visible_while_typing(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("echo check")
            await pilot.pause()

            self.assertIn("echo check", composer.build_render_text(80, focused=True).plain)

    async def test_app_transcript_mode_keeps_footer_navigation_pair(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_toggle_transcript()
            await pilot.pause()

            status_line = app.query_one("#status_line", Static)
            footer = app.query_one("#composer_footer", Static)
            rendered_footer = self._static_plain(footer)

            self.assertEqual(self._static_plain(status_line), "")
            self.assertIn(app._t("footer.transcript_prompt_view"), rendered_footer)
            self.assertIn(app._t("footer.transcript_exit"), rendered_footer)

    async def test_app_footer_plain_text_keeps_provider_summary_and_context_when_width_allows(
        self,
    ) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            line = app._build_footer_line(120)
            provider_summary = build_provider_summary_text(
                status_data=app.runtime.agent.provider_status()
            )

            self.assertIn(provider_summary, line)
            self.assertIn(app._t("footer.context_left"), line)

    async def test_app_footer_plain_text_preserves_right_context_on_narrow_width(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            line = app._build_footer_line(12)

            self.assertNotIn(app._t("footer.shortcuts"), line)
            self.assertTrue(line.startswith("100") or line.startswith("剩余"))
            self.assertLessEqual(len(line), 12)

    async def test_app_footer_plain_text_drops_tiny_left_fragment_before_right_context(
        self,
    ) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            line = app._build_footer_line(20)

            self.assertEqual(line, app._crop_one_line(app._t("footer.context_left"), 20))
            self.assertNotIn(app._t("footer.shortcuts"), line)

    async def test_app_footer_plain_text_busy_draft_keeps_queue_hint_and_crops_context_when_narrow(
        self,
    ) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("draft for queue")
            app._set_busy(True)
            await pilot.pause()

            wide_line = app._build_footer_line(120)
            narrow_line = app._build_footer_line(14)
            status_line = app.query_one("#status_line", Static)

            self.assertIn(app._t("status.working"), self._static_plain(status_line))
            self.assertNotIn(app._t("footer.queue_message"), self._static_plain(status_line))
            self.assertIn(app._t("footer.queue_message"), wide_line)
            self.assertIn(app._t("footer.context_left"), wide_line)
            self.assertTrue(narrow_line.startswith("100") or narrow_line.startswith("剩余"))
            self.assertNotIn(app._t("footer.context_left"), narrow_line)
            self.assertLessEqual(len(narrow_line), 14)

    async def test_app_footer_plain_text_idle_draft_keeps_provider_summary_and_context(
        self,
    ) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("still drafting")
            await pilot.pause()

            line = app._build_footer_line(80)
            provider_summary = build_provider_summary_text(
                status_data=app.runtime.agent.provider_status()
            )

            self.assertIn(provider_summary, line)
            self.assertIn(app._t("footer.context_left"), line)
            self.assertNotIn(app._t("footer.shortcuts"), line)

    async def test_app_busy_status_line_uses_reference_style_working_copy(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_busy(True)
            await pilot.pause()

            status_line = app.query_one("#status_line", Static)

            self._assert_enhanced_status_line(
                self._static_plain(status_line),
                app._t("status.working"),
                interrupt_suffix=app._t("status.interrupt_suffix"),
            )

    async def test_app_busy_status_line_uses_reasoning_bold_header_like_reference(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_busy(True)
            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_reasoning",
                        "type": "reasoning",
                        "text": "**Search** 检查当前目录和文件列表",
                    },
                }
            )
            await pilot.pause()

            status_line = app.query_one("#status_line", Static)

            self._assert_enhanced_status_line(
                self._static_plain(status_line),
                "Search",
                interrupt_suffix=app._t("status.interrupt_suffix"),
            )

    async def test_app_hides_busy_status_line_while_assistant_message_streams_like_reference(
        self,
    ) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_busy(True)
            app._begin_activity_capture()
            app._write_live_turn_event(
                {
                    "type": "item.updated",
                    "item": {
                        "id": "item_0",
                        "type": "agent_message",
                        "text": "我先查看",
                        "phase": "commentary",
                    },
                }
            )
            await pilot.pause()

            status_line = app.query_one("#status_line", Static)

            self.assertEqual(self._static_plain(status_line), "")

    async def test_app_restores_busy_status_line_after_assistant_stream_completion(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_busy(True)
            app._begin_activity_capture()
            app._write_live_turn_event(
                {
                    "type": "item.updated",
                    "item": {
                        "id": "item_0",
                        "type": "agent_message",
                        "text": "我先查看",
                        "phase": "commentary",
                    },
                }
            )
            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_0",
                        "type": "agent_message",
                        "text": "我先查看当前目录。",
                        "phase": "commentary",
                    },
                }
            )
            await pilot.pause()

            status_line = app.query_one("#status_line", Static)

            self._assert_enhanced_status_line(
                self._static_plain(status_line),
                app._t("status.working"),
                interrupt_suffix=app._t("status.interrupt_suffix"),
            )

    async def test_app_keeps_busy_status_hidden_after_final_answer_stream_completion_until_turn_finishes(
        self,
    ) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_busy(True)
            app._begin_activity_capture()
            app._write_live_turn_event(
                {
                    "type": "item.updated",
                    "item": {
                        "id": "item_0",
                        "type": "agent_message",
                        "text": "当前目录下",
                        "phase": "final_answer",
                    },
                }
            )
            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_0",
                        "type": "agent_message",
                        "text": "当前目录下有 README.md。",
                        "phase": "final_answer",
                    },
                }
            )
            await pilot.pause()

            status_line = app.query_one("#status_line", Static)

            self.assertEqual(self._static_plain(status_line), "")

    async def test_app_does_not_append_completion_time_line_after_turn_completion_without_work(
        self,
    ) -> None:
        app = AgentCliApp(language="zh-CN")

        async with app.run_test() as pilot:
            await pilot.pause()
            app._begin_activity_capture()
            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_0",
                        "type": "agent_message",
                        "text": "当前目录下有 README.md。",
                        "phase": "final_answer",
                    },
                }
            )
            app._write_live_turn_event({"type": "turn.completed"})
            app._write_live_turn_event({"type": "turn.completed"})
            await pilot.pause()

            main_log = app.query_one("#main_log")
            rendered_text = main_log.text

            self.assertIn("• 当前目录下有 README.md。", rendered_text)
            completion_lines = [
                line for line in rendered_text.splitlines() if "完成" in line or "Done" in line
            ]
            self.assertEqual(completion_lines, [])

    async def test_app_does_not_append_completion_time_line_for_slash_command_turn(self) -> None:
        app = AgentCliApp(language="zh-CN")

        async with app.run_test() as pilot:
            await pilot.pause()
            app._active_runtime_request_is_slash = True
            app._begin_activity_capture()
            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_0",
                        "type": "agent_message",
                        "text": "provider: ok",
                        "phase": "final_answer",
                    },
                }
            )
            app._write_live_turn_event({"type": "turn.completed"})
            await pilot.pause()

            main_log = app.query_one("#main_log")
            rendered_text = main_log.text

            self.assertIn("• provider: ok", rendered_text)
            completion_lines = [
                line for line in rendered_text.splitlines() if "完成" in line or "Done" in line
            ]
            self.assertEqual(completion_lines, [])

    async def test_app_inserts_separator_before_final_answer_after_tool_work(self) -> None:
        app = AgentCliApp(language="zh-CN")

        async with app.run_test() as pilot:
            await pilot.pause()
            app._begin_activity_capture()
            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_0",
                        "type": "agent_message",
                        "text": "我先查看当前目录。",
                        "phase": "commentary",
                    },
                }
            )
            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_1",
                        "type": "command_execution",
                        "command": '/bin/bash -lc "find . -maxdepth 1 -mindepth 1 | sort"',
                        "aggregated_output": "README.md\nagent_cli\n",
                        "exit_code": 0,
                        "status": "completed",
                    },
                }
            )
            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_2",
                        "type": "agent_message",
                        "text": "当前目录下有 README.md 和 agent_cli。",
                        "phase": "final_answer",
                    },
                }
            )
            await pilot.pause()

            main_log = app.query_one("#main_log")
            rendered_text = main_log.text

            self.assertIn("• 我先查看当前目录。", rendered_text)
            self.assertIn("• Explored", rendered_text)
            separator_lines = [
                line.strip()
                for line in rendered_text.splitlines()
                if "完成" in line and "用时" in line and line.strip().startswith("─")
            ]
            self.assertEqual(len(separator_lines), 1)
            self.assertRegex(separator_lines[0], r"^─{2,}完成\d{2}:\d{2}，用时\d+[sm]─*$")
            self.assertTrue(
                rendered_text.index(separator_lines[0])
                < rendered_text.index("• 当前目录下有 README.md 和 agent_cli。")
            )
            self.assertNotIn("\n完成", rendered_text)

    async def test_late_tool_after_final_demotes_final_and_removes_separator(self) -> None:
        app = AgentCliApp(language="zh-CN")

        async with app.run_test() as pilot:
            await pilot.pause()
            app._begin_activity_capture()
            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_0",
                        "type": "command_execution",
                        "command": "pwd",
                        "aggregated_output": "/repo\n",
                        "exit_code": 0,
                        "status": "completed",
                    },
                }
            )
            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_1",
                        "type": "agent_message",
                        "text": "这个项目的全貌已经很清晰了。",
                        "phase": "final_answer",
                    },
                }
            )
            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_2",
                        "type": "command_execution",
                        "command": "ls",
                        "aggregated_output": "cli\n",
                        "exit_code": 0,
                        "status": "completed",
                    },
                }
            )
            await pilot.pause()

            rendered_text = app.query_one("#main_log").text

            self.assertIn("• 这个项目的全貌已经很清晰了。", rendered_text)
            separator_lines = [
                line
                for line in rendered_text.splitlines()
                if "完成" in line and "用时" in line and line.strip().startswith("─")
            ]
            self.assertEqual(separator_lines, [])

    async def test_backfilled_late_tool_after_final_removes_separator(self) -> None:
        app = AgentCliApp(language="zh-CN")

        async with app.run_test() as pilot:
            await pilot.pause()
            app._begin_activity_capture()
            app._render_canonical_turn_event_backfill(
                [
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item_0",
                            "type": "command_execution",
                            "command": "pwd",
                            "aggregated_output": "/repo\n",
                            "exit_code": 0,
                            "status": "completed",
                        },
                    },
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item_1",
                            "type": "agent_message",
                            "text": "这个项目的全貌已经很清晰了。",
                            "phase": "final_answer",
                        },
                    },
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item_2",
                            "type": "command_execution",
                            "command": "ls",
                            "aggregated_output": "cli\n",
                            "exit_code": 0,
                            "status": "completed",
                        },
                    },
                ]
            )
            await pilot.pause()

            rendered_text = app.query_one("#main_log").text

            self.assertIn("• 这个项目的全貌已经很清晰了。", rendered_text)
            separator_lines = [
                line
                for line in rendered_text.splitlines()
                if "完成" in line and "用时" in line and line.strip().startswith("─")
            ]
            self.assertEqual(separator_lines, [])

    async def test_delegated_child_agent_message_does_not_render_as_top_level_final(
        self,
    ) -> None:
        app = AgentCliApp(language="zh-CN")

        async with app.run_test() as pilot:
            await pilot.pause()
            app._begin_activity_capture()
            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "delegated_agent": {"task_id": "delegate_1", "role": "subagent"},
                    "item": {
                        "id": "delegate_1:item_0",
                        "type": "command_execution",
                        "command": "ls",
                        "aggregated_output": "README.md\n",
                        "exit_code": 0,
                        "status": "completed",
                        "delegated_agent": {"task_id": "delegate_1", "role": "subagent"},
                    },
                }
            )
            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "delegated_agent": {"task_id": "delegate_1", "role": "subagent"},
                    "item": {
                        "id": "delegate_1:item_1",
                        "type": "agent_message",
                        "text": "子 agent 总结不应作为主回答显示。",
                        "phase": "final_answer",
                        "delegated_agent": {"task_id": "delegate_1", "role": "subagent"},
                    },
                }
            )
            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_parent",
                        "type": "agent_message",
                        "text": "父模型总结只显示一次。",
                        "phase": "final_answer",
                    },
                }
            )
            app._write_live_turn_event({"type": "turn.completed"})
            await pilot.pause()

            rendered_text = app.query_one("#main_log").text

            self.assertNotIn("子 agent 总结不应作为主回答显示。", rendered_text)
            self.assertEqual(rendered_text.count("父模型总结只显示一次。"), 1)

    async def test_backfilled_delegated_child_agent_message_does_not_render_as_final(
        self,
    ) -> None:
        app = AgentCliApp(language="zh-CN")

        async with app.run_test() as pilot:
            await pilot.pause()
            app._begin_activity_capture()
            app._render_canonical_turn_event_backfill(
                [
                    {
                        "type": "item.completed",
                        "delegated_agent": {"task_id": "delegate_1", "role": "subagent"},
                        "item": {
                            "id": "delegate_1:item_0",
                            "type": "command_execution",
                            "command": "ls",
                            "aggregated_output": "README.md\n",
                            "exit_code": 0,
                            "status": "completed",
                            "delegated_agent": {
                                "task_id": "delegate_1",
                                "role": "subagent",
                            },
                        },
                    },
                    {
                        "type": "item.completed",
                        "delegated_agent": {"task_id": "delegate_1", "role": "subagent"},
                        "item": {
                            "id": "delegate_1:item_1",
                            "type": "agent_message",
                            "text": "回放的子 agent 总结不应显示。",
                            "phase": "final_answer",
                            "delegated_agent": {
                                "task_id": "delegate_1",
                                "role": "subagent",
                            },
                        },
                    },
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item_parent",
                            "type": "agent_message",
                            "text": "回放父模型总结只显示一次。",
                            "phase": "final_answer",
                        },
                    },
                    {"type": "turn.completed"},
                ]
            )
            await pilot.pause()

            rendered_text = app.query_one("#main_log").text

            self.assertNotIn("回放的子 agent 总结不应显示。", rendered_text)
            self.assertEqual(rendered_text.count("回放父模型总结只显示一次。"), 1)

    async def test_app_exec_status_and_footer_scene_matches_reference_structure(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app._begin_activity_capture()
            app._write_assistant_reply(
                "I’m going to search the repo for where “Change Approved” is rendered to update that view."
            )
            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_cmd_0",
                        "type": "command_execution",
                        "command": '/bin/bash -lc "rg \\"Change Approved\\"\ncat diff_render.rs"',
                        "aggregated_output": "",
                        "exit_code": 0,
                        "status": "completed",
                    },
                }
            )
            app._set_busy(True)
            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_reasoning",
                        "type": "reasoning",
                        "text": "**Investigating rendering code**",
                    },
                }
            )
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("Summarize recent commits")
            await pilot.pause()

            main_log = app.query_one("#main_log")
            status_line = app.query_one("#status_line", Static)
            footer = app.query_one("#composer_footer", Static)

            self.assertEqual(
                main_log.text,
                "• I’m going to search the repo for where “Change Approved” is rendered to update that view.\n\n"
                "• Explored\n"
                "  └ Search Change Approved\n"
                "    Read diff_render.rs",
            )
            self.assertIn("Investigating rendering code", self._static_plain(status_line))
            self.assertIn(app._t("footer.queue_message"), self._static_plain(footer))
            self.assertEqual(
                composer.build_render_text(80, focused=True).plain.rstrip(),
                "› Summarize recent commits",
            )

    async def test_transcript_widget_disables_cursor_line_highlight_for_final_blockquote(
        self,
    ) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app._write_assistant_reply("# 标题\n\n> 引用")
            await pilot.pause()

            main_log = app.query_one("#main_log", TranscriptArea)

            self.assertFalse(main_log.show_cursor)
            self.assertFalse(main_log.highlight_cursor_line)

            quote_strip = main_log.render_line(2)
            quote_segment = next(
                segment for segment in quote_strip._segments if segment.text == "> 引用"
            )

            self.assertEqual(
                quote_segment.style.color, RichColor.parse(app._theme.markdown_blockquote)
            )

    async def test_transcript_widget_disables_textarea_syntax_highlighting_for_markdown(
        self,
    ) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app._write_assistant_reply(
                "# 一级标题\n\n这是一句包含 **加粗** 的文本。\n\n这是一句包含 `code_sample` 的文本。\n\n[docs](https://a.com)\n\n> 这是一个引用块。"
            )
            await pilot.pause()

            main_log = app.query_one("#main_log", TranscriptArea)

            self.assertFalse(getattr(main_log, "_highlight_query", None))
            self.assertFalse(getattr(main_log, "_highlights", {}))

            quote_segment = None
            for y in range(int(main_log.content_size.height or 0) + 2):
                strip = main_log.render_line(y)
                for segment in strip._segments:
                    if "引用块" in segment.text:
                        quote_segment = segment
                        break
                if quote_segment is not None:
                    break

            self.assertIsNotNone(quote_segment)

            assert quote_segment is not None
            self.assertEqual(
                quote_segment.style.color, RichColor.parse(app._theme.markdown_blockquote)
            )

    async def test_app_transcript_renders_reference_style_image_placeholder_user_prompt(
        self,
    ) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app._write_user_prompt(
                '@"/tmp/cat.png" describe this image',
                attachments=[
                    PromptAttachment(path="/tmp/cat.png", name="cat.png", extension="png")
                ],
            )
            await pilot.pause()

            main_log = app.query_one("#main_log")
            rendered_text = main_log.text

            self.assertIn("[Image #1]", rendered_text)
            self.assertIn("› describe this image", rendered_text)
            self.assertNotIn("/tmp/cat.png", rendered_text)

    def test_command_execution_visual_wrap_matches_reference_prefix_structure(self) -> None:
        app = AgentCliApp()
        entry = app._turn_event_entry(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_cmd_wrap",
                    "type": "command_execution",
                    "command": '/bin/bash -lc "set -o pipefail\\ncargo test --all-features --quiet"',
                    "aggregated_output": "",
                    "exit_code": 0,
                    "status": "completed",
                },
            }
        )

        assert entry is not None
        rendered = render_transcript_visual_entries([entry], width=24)

        self.assertEqual(
            rendered.lines,
            [
                "• Ran set -o pipefail",
                "  │ cargo test",
                "  │ --all-features",
                "  │ --quiet",
                "  └ (no output)",
            ],
        )

    def test_mcp_tool_visual_wrap_matches_reference_header_then_tree_layout(self) -> None:
        app = AgentCliApp()
        entry = app._turn_event_entry(
            {
                "type": "item.completed",
                "item": {
                    "id": "item_tool_wrap",
                    "type": "mcp_tool_call",
                    "server": "metrics",
                    "tool": "get_nearby_metric",
                    "arguments": {
                        "query": "very_long_query_that_needs_wrapping_to_display_properly_in_the_history",
                        "limit": 1,
                    },
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": "Line one of the response, which is quite long and needs wrapping.",
                            }
                        ],
                        "structured_content": {},
                    },
                    "error": None,
                    "status": "completed",
                },
            }
        )

        assert entry is not None
        rendered = render_transcript_visual_entries([entry], width=36)

        self.assertEqual(rendered.lines[0], "• Called")
        self.assertTrue(rendered.lines[1].startswith("  └ metrics.get_nearby_metric("))
        self.assertTrue(rendered.lines[2].startswith("    "))
        self.assertTrue(rendered.lines[-1].startswith("    "))
        self.assertTrue(all(len(line) <= 36 for line in rendered.lines))

from __future__ import annotations

import asyncio
import os
import sys
import threading
import tomllib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from rich.cells import cell_len
from rich.color import Color as RichColor
from textual import events
from textual.color import Color
from textual.events import Paste
from textual.widgets import Static, TextArea

from cli.agent_cli.app import AgentCliApp, PromptComposer, SlashCommandPopup, TranscriptArea
from cli.agent_cli.models import (
    REFERENCE_CONVERSATION_INTERRUPTED_TEXT,
    ActivityEvent,
    PromptAttachment,
    PromptResponse,
    ToolEvent,
)
from cli.agent_cli.providers.availability_registry import AvailabilityRegistry
from cli.agent_cli.runtime_core import activity_events_for_tool_event
from cli.agent_cli.terminal_driver import AgentHubLinuxDriver
from cli.agent_cli.ui import crop_one_line, flag_label, short, tool_label
from cli.agent_cli.ui.theme import builtin_theme_ids
from cli.agent_cli.ui.theme_runtime import scrollbar_palette
from cli.agent_cli.ui.transcript_history import (
    activity_entry,
    blank_entry,
    render_transcript_entries,
    render_transcript_visual_entries,
)

try:
    from cli.agent_cli.demo_runtime_support import build_demo_runtime
except ModuleNotFoundError:
    from cli.demo_runtime_support import build_demo_runtime

INTERRUPTED_TRANSCRIPT_TEXT = REFERENCE_CONVERSATION_INTERRUPTED_TEXT


class RecordingRuntime:
    class _Agent:
        @staticmethod
        def provider_status() -> dict[str, str]:
            return {
                "provider_name": "test",
                "provider_model": "test-model",
                "provider_reasoning_effort": "high",
                "provider_ready": "true",
            }

    def __init__(self) -> None:
        self.agent = self._Agent()
        self.activity_callback = None
        self.last_prompt: str | None = None
        self.last_attachments: list[PromptAttachment] = []

    def slash_command_matches(self, query: str) -> list[dict[str, str]]:
        return []

    def slash_command_completion(self, query: str) -> str | None:
        return None

    def handle_prompt(
        self, text: str, *, attachments: list[PromptAttachment] | None = None
    ) -> PromptResponse:
        self.last_prompt = text
        self.last_attachments = list(attachments or [])
        return PromptResponse(
            user_text=text,
            assistant_text="processed",
            attachments=list(attachments or []),
            status=self.agent.provider_status(),
            handled_as_command=False,
        )

    def interrupt_active_run(self) -> dict[str, object]:
        return {"ok": False, "interrupted": False}


class SlashPopupRuntime(RecordingRuntime):
    def __init__(self) -> None:
        super().__init__()
        self._commands = [
            {"name": "help", "usage": "/help", "description": "show available slash commands"},
            {
                "name": "chat",
                "usage": "/chat",
                "description": "switch to the DeepSeek chat-tools line",
            },
            {
                "name": "reasoner",
                "usage": "/reasoner",
                "description": "switch to the DeepSeek reasoner line",
            },
            {
                "name": "providers",
                "usage": "/providers",
                "description": "list configured model providers",
            },
            {
                "name": "models",
                "usage": "/models [provider]",
                "description": "list configured models",
            },
            {
                "name": "provider",
                "usage": "/provider [name]",
                "description": "show current provider or switch provider",
            },
            {
                "name": "model",
                "usage": "/model [name]",
                "description": "show current model or switch model",
            },
            {
                "name": "runtime_status",
                "usage": "/runtime_status",
                "description": "show runtime policy status",
            },
            {
                "name": "runtime_config",
                "usage": "/runtime_config [approval-policy <mode>]",
                "description": "update runtime policy settings for the current session",
            },
            {
                "name": "tools",
                "usage": "/tools",
                "description": "list local toolchain capabilities",
            },
        ]

    def slash_command_matches(self, query: str) -> list[dict[str, str]]:
        prefix = str(query or "").strip().lower().lstrip("/")
        if not prefix:
            return [dict(item) for item in self._commands]
        startswith_matches = [
            dict(item)
            for item in self._commands
            if str(item.get("name") or "").strip().lower().startswith(prefix)
        ]
        if startswith_matches:
            return startswith_matches
        return [
            dict(item)
            for item in self._commands
            if prefix in str(item.get("name") or "").strip().lower()
        ]

    def slash_command_completion(self, query: str) -> str | None:
        matches = self.slash_command_matches(query)
        if len(matches) == 1:
            return f"/{matches[0]['name']} "
        return None


class ParameterPopupRuntime(SlashPopupRuntime):
    class _Agent(RecordingRuntime._Agent):
        def __init__(self) -> None:
            self._provider_availability_registry = AvailabilityRegistry()
            self._provider_availability_registry.mark_success(
                provider_name="openai",
                model="gpt-5.4",
                latency_ms=180,
            )
            self._provider_availability_registry.mark_failure(
                provider_name="openai",
                model="gpt-5.3-reference",
                failure_code="timeout",
                failure_reason="request timeout",
                latency_ms=950,
            )

        @staticmethod
        def provider_status() -> dict[str, str]:
            return {
                "provider_name": "openai",
                "provider_public_name": "openai",
                "provider_model": "gpt_54",
                "provider_reasoning_effort": "high",
                "provider_ready": "true",
            }

        @staticmethod
        def available_providers() -> list[dict[str, str]]:
            return [
                {"provider_name": "openai"},
                {"provider_name": "anthropic"},
            ]

        @staticmethod
        def available_models(provider_name: str | None = None) -> list[dict[str, str]]:
            if provider_name == "anthropic":
                return [
                    {
                        "model_key": "claude_sonnet_4",
                        "model_id": "claude-sonnet-4",
                        "config_provider_name": "anthropic",
                    }
                ]
            return [
                {
                    "model_key": "gpt_54",
                    "model_id": "gpt-5.4",
                    "config_provider_name": "openai",
                    "supported_reasoning_efforts": ["low", "medium", "high", "xhigh"],
                    "default_reasoning_effort": "high",
                },
                {
                    "model_key": "gpt_53_reference",
                    "model_id": "gpt-5.3-reference",
                    "config_provider_name": "openai",
                    "supported_reasoning_efforts": ["low", "medium", "high"],
                    "default_reasoning_effort": "medium",
                },
            ]

    def __init__(self) -> None:
        super().__init__()
        self.agent = self._Agent()


class InterruptRecordingRuntime(RecordingRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.interrupt_calls = 0

    def interrupt_active_run(self) -> dict[str, object]:
        self.interrupt_calls += 1
        return {"ok": True, "interrupted": True}


class SynchronousInterruptActivityRuntime(RecordingRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.interrupt_calls = 0

    def interrupt_active_run(self) -> dict[str, object]:
        self.interrupt_calls += 1
        callback = self.activity_callback
        if callable(callback):
            callback(
                ActivityEvent(
                    title="Interrupt requested for long run",
                    status="info",
                    kind="interrupt",
                )
            )
        return {"ok": True, "interrupted": True}


class BlockingQueueRuntime(RecordingRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []
        self.started_prompts: list[str] = []
        self._release_events: dict[str, threading.Event] = {}
        self._started_events: dict[str, threading.Event] = {}

    def block_prompt(self, prompt: str) -> threading.Event:
        release = threading.Event()
        started = threading.Event()
        self._release_events[prompt] = release
        self._started_events[prompt] = started
        return release

    async def wait_started(self, prompt: str, timeout: float = 1.0) -> None:
        started = self._started_events[prompt]
        await asyncio.wait_for(asyncio.to_thread(started.wait, timeout), timeout=timeout + 0.2)

    def handle_prompt(
        self, text: str, *, attachments: list[PromptAttachment] | None = None
    ) -> PromptResponse:
        self.calls.append(text)
        started = self._started_events.get(text)
        if started is not None:
            started.set()
        release = self._release_events.get(text)
        if release is not None:
            release.wait(5.0)
        self.last_prompt = text
        self.last_attachments = list(attachments or [])
        self.started_prompts.append(text)
        return PromptResponse(
            user_text=text,
            assistant_text=f"processed {text}",
            attachments=list(attachments or []),
            status=self.agent.provider_status(),
            handled_as_command=False,
        )


class InterruptCleanupRuntime(RecordingRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.interrupt_calls = 0
        self.started_prompts: list[str] = []
        self._started_events: dict[str, threading.Event] = {}
        self._finish_events: dict[str, threading.Event] = {}
        self._active_lock = threading.Lock()
        self._active = False

    def block_prompt(self, prompt: str) -> threading.Event:
        started = threading.Event()
        finish = threading.Event()
        self._started_events[prompt] = started
        self._finish_events[prompt] = finish
        return finish

    async def wait_started(self, prompt: str, timeout: float = 1.0) -> None:
        started = self._started_events[prompt]
        await asyncio.wait_for(asyncio.to_thread(started.wait, timeout), timeout=timeout + 0.2)

    def has_active_run(self) -> bool:
        with self._active_lock:
            return self._active

    def handle_prompt(
        self, text: str, *, attachments: list[PromptAttachment] | None = None
    ) -> PromptResponse:
        self.last_prompt = text
        self.last_attachments = list(attachments or [])
        self.started_prompts.append(text)
        started = self._started_events.get(text)
        finish = self._finish_events.get(text)
        with self._active_lock:
            self._active = True
        if started is not None:
            started.set()
        if finish is not None:
            finish.wait(5.0)
        with self._active_lock:
            self._active = False
        return PromptResponse(
            user_text=text,
            assistant_text=f"processed {text}",
            attachments=list(attachments or []),
            status=self.agent.provider_status(),
            handled_as_command=False,
        )

    def interrupt_active_run(self) -> dict[str, object]:
        self.interrupt_calls += 1
        return {"ok": True, "interrupted": True}


class AppUiSmokeTest(unittest.IsolatedAsyncioTestCase):
    class _MouseEventSpy(SimpleNamespace):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            self.stopped = False
            self.prevented = False

        def stop(self) -> None:
            self.stopped = True

        def prevent_default(self) -> None:
            self.prevented = True

    @staticmethod
    def _fake_printable_key(character: str) -> SimpleNamespace:
        return SimpleNamespace(
            key=character,
            character=character,
            is_printable=True,
            stop=lambda: None,
            prevent_default=lambda: None,
        )

    def assert_cursor_render(
        self,
        composer: PromptComposer,
        width: int,
        expected_plain: str,
        cursor_start: int,
    ) -> None:
        rendered = composer.build_render_text(width, focused=True)
        self.assertEqual(rendered.plain, expected_plain)
        reverse_spans = [
            (span.start, span.end) for span in rendered.spans if "reverse" in str(span.style)
        ]
        self.assertEqual(reverse_spans, [(cursor_start, cursor_start + 1)])

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

    def _status_line_plain(self, app: AgentCliApp) -> str:
        return self._static_plain(app.query_one("#status_line", Static))

    def _footer_plain(self, app: AgentCliApp) -> str:
        return self._static_plain(app.query_one("#composer_footer", Static))

    def _simulate_submit_without_runtime(
        self, app: AgentCliApp
    ) -> tuple[str, list[PromptAttachment]]:
        display_text = app._current_prompt_text().strip()
        text, attachments = app._prepare_prompt_submission(display_text)
        echo_text = app._expand_pending_pastes(display_text).strip()
        actual_chars = len(text)
        if actual_chars > app.MAX_USER_INPUT_TEXT_CHARS:
            app._write_system_notice(app._user_input_too_large_message(actual_chars))
            app._focus_input()
            return "", []
        app._clear_prompt_text()
        app._refresh_prompt_composer()
        if not text:
            app._focus_input()
            return "", []
        app.prompt_count += 1
        app._record_prompt_history(text)
        app._write_user_prompt(echo_text, attachments=attachments)
        app._focus_input()
        return text, attachments

    def test_agent_cli_app_uses_safe_linux_driver_on_posix(self) -> None:
        app = AgentCliApp()
        if sys.platform == "win32":
            self.assertNotEqual(app.driver_class, AgentHubLinuxDriver)
        else:
            self.assertIs(app.driver_class, AgentHubLinuxDriver)

    def test_prompt_composer_renders_reference_style_prefix_and_cursor(self) -> None:
        composer = PromptComposer("abc")
        self.assert_cursor_render(composer, 12, "› abc ", 5)

    def test_prompt_composer_renders_empty_prompt_with_cursor(self) -> None:
        composer = PromptComposer("")
        self.assert_cursor_render(composer, 32, "› Ask AgentHub to do anything", 2)

    def test_prompt_composer_wraps_with_continuation_indent(self) -> None:
        composer = PromptComposer("abcdef")
        self.assert_cursor_render(composer, 5, "› abc\n  def\n   ", 14)

    def test_prompt_composer_wraps_cjk_using_display_width(self) -> None:
        composer = PromptComposer("你好ab")
        self.assert_cursor_render(composer, 6, "› 你好\n  ab ", 9)

    def test_prompt_composer_supports_middle_insertion(self) -> None:
        composer = PromptComposer("helo")
        composer.move_cursor_left()
        composer.insert_text("l")

        self.assertEqual(composer.text, "hello")
        self.assertEqual(composer.cursor_pos, 4)
        self.assert_cursor_render(composer, 12, "› hello", 6)

    def test_prompt_composer_supports_home_end_and_delete(self) -> None:
        composer = PromptComposer("abc\ndef")
        composer.move_cursor_home()
        self.assertEqual(composer.cursor_pos, 4)
        composer.delete_forward()
        self.assertEqual(composer.text, "abc\nef")
        composer.move_cursor_end()
        self.assertEqual(composer.cursor_pos, len(composer.text))

    def test_prompt_composer_supports_vertical_cursor_moves(self) -> None:
        composer = PromptComposer("abcd\nef")
        composer.move_cursor_up()
        self.assertEqual(composer.cursor_pos, 2)
        composer.move_cursor_down()
        self.assertEqual(composer.cursor_pos, 7)

    async def test_prompt_composer_render_uses_custom_text_rendering_in_app(self) -> None:
        app = AgentCliApp(runtime=RecordingRuntime())

        async with app.run_test() as pilot:
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.insert_text("abc")
            await pilot.pause()

            rendered = composer.render()
            self.assertEqual(type(rendered).__name__, "Text")
            self.assertIn("› abc", rendered.plain)

    async def test_app_compose_matches_reference_like_layout(self) -> None:
        app = AgentCliApp()

        async with app.run_test():
            self.assertIsInstance(app.query_one("#main_log"), TranscriptArea)
            self.assertIsInstance(app.query_one("#main_log"), TextArea)
            self.assertIsInstance(app.query_one("#prompt_composer"), PromptComposer)
            self.assertIsInstance(app.query_one("#slash_popup"), SlashCommandPopup)
            self.assertIsInstance(app.query_one("#status_line"), Static)
            self.assertIsInstance(app.query_one("#composer_footer"), Static)
            self.assertEqual(
                [child.id for child in app.query_one("#bottom_dock").children],
                ["slash_popup", "status_line", "composer_shell", "composer_footer"],
            )

    async def test_app_accepts_injected_runtime(self) -> None:
        app = AgentCliApp(runtime=build_demo_runtime())

        async with app.run_test():
            self.assertEqual(
                app.runtime.agent.provider_status()["provider_model"], "deepseek-reasoner"
            )

    async def test_idle_footer_shows_provider_model_and_effort(self) -> None:
        app = AgentCliApp(runtime=RecordingRuntime())

        async with app.run_test() as pilot:
            await pilot.pause()

            footer = self._footer_plain(app)
            status_line = self._status_line_plain(app)

            self.assertIn("test", footer)
            self.assertIn("test-model", footer)
            self.assertIn("high", footer)
            self.assertNotIn("test-model", status_line)

    async def test_busy_footer_keeps_provider_summary_left_and_context_right(self) -> None:
        app = AgentCliApp(runtime=RecordingRuntime())

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_busy(True)
            await pilot.pause()

            footer = self._footer_plain(app)

            self.assertIn("test", footer)
            self.assertIn("test-model", footer)
            self.assertIn("high", footer)
            self.assertIn(app._t("footer.context_left"), footer)
            self.assertLess(footer.index("test-model"), footer.index(app._t("footer.context_left")))

    async def test_prompt_composer_keeps_initial_focus(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertIs(app.focused, app.query_one("#prompt_composer", PromptComposer))

    async def test_prompt_composer_recovers_keyboard_input_when_focus_is_lost(self) -> None:
        runtime = RecordingRuntime()
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            app.set_focus(None)
            await pilot.press("h")
            await asyncio.sleep(0.1)
            composer = app.query_one("#prompt_composer", PromptComposer)
            self.assertEqual(composer.text, "h")
            self.assertIs(app.focused, composer)
            await pilot.press("enter")
            await app._wait_for_runtime_idle()

        self.assertEqual(runtime.last_prompt, "h")

    async def test_app_mouse_up_outside_composer_refocuses_prompt(self) -> None:
        app = AgentCliApp()
        focus_calls: list[str] = []

        async with app.run_test() as pilot:
            await pilot.pause()
            main_log = app.query_one("#main_log", TranscriptArea)
            original_focus_input = app._focus_input

            def _tracked_focus_input() -> None:
                focus_calls.append("focus")
                original_focus_input()

            app._focus_input = _tracked_focus_input
            app.on_mouse_up(SimpleNamespace(button=1, widget=main_log))
            await pilot.pause()

            self.assertGreaterEqual(len(focus_calls), 1)
            self.assertIs(app.focused, app.query_one("#prompt_composer", PromptComposer))

    async def test_app_mouse_up_on_composer_does_not_refocus_again(self) -> None:
        app = AgentCliApp()
        focus_calls: list[str] = []

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            original_focus_input = app._focus_input

            def _tracked_focus_input() -> None:
                focus_calls.append("focus")
                original_focus_input()

            app._focus_input = _tracked_focus_input
            app.on_mouse_up(SimpleNamespace(button=1, widget=composer))
            await pilot.pause()

            self.assertLessEqual(len(focus_calls), 1)
            self.assertIs(app.focused, composer)

    async def test_initial_transcript_starts_empty(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            self.assertEqual(app.query_one("#main_log", TranscriptArea).text, "")

    async def test_escape_requests_interrupt_when_busy(self) -> None:
        runtime = InterruptRecordingRuntime()
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_busy(True)
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(runtime.interrupt_calls, 1)
            self.assertEqual(app.query_one("#main_log", TranscriptArea).text, "")
            self.assertTrue(app._live_turn_interrupt_requested)

    async def test_escape_interrupt_handles_same_thread_runtime_activity(self) -> None:
        runtime = SynchronousInterruptActivityRuntime()
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_busy(True)
            await pilot.press("escape")
            await pilot.pause()
            transcript = app.query_one("#main_log", TranscriptArea).text

        self.assertEqual(runtime.interrupt_calls, 1)
        self.assertEqual(transcript, "")

    async def test_escape_interrupt_uses_single_app_entry_when_focus_leaves_composer(self) -> None:
        runtime = InterruptRecordingRuntime()
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_busy(True)
            app.query_one("#main_log", TranscriptArea).focus()
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            transcript = app.query_one("#main_log", TranscriptArea).text

        self.assertEqual(runtime.interrupt_calls, 1)
        self.assertEqual(transcript, "")

    async def test_escape_releases_busy_ui_while_runtime_cleanup_finishes(self) -> None:
        runtime = InterruptCleanupRuntime()
        finish = runtime.block_prompt("cleanup job")
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("cleanup job")
            await app.action_submit_prompt()
            await runtime.wait_started("cleanup job")
            await pilot.pause()

            self.assertTrue(app._busy)
            self.assertTrue(app._has_pending_runtime_work())

            await pilot.press("escape")
            await pilot.pause()

            self.assertEqual(runtime.interrupt_calls, 1)
            self.assertFalse(app._busy)
            self.assertTrue(app._has_pending_runtime_work())

            finish.set()
            await app._wait_for_runtime_idle()
            await pilot.pause()

            self.assertFalse(app._busy)
            self.assertFalse(app._has_pending_runtime_work())

    async def test_submit_after_escape_interrupt_queues_followup_without_steer_notice(self) -> None:
        runtime = InterruptCleanupRuntime()
        finish_first = runtime.block_prompt("cleanup job")
        finish_followup = runtime.block_prompt("应该在根目录下 gui 目录下")
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("cleanup job")
            await app.action_submit_prompt()
            await runtime.wait_started("cleanup job")
            await pilot.pause()

            await pilot.press("escape")
            await pilot.pause()

            self.assertFalse(app._busy)
            self.assertTrue(app._has_pending_runtime_work())

            app._set_prompt_text("应该在根目录下 gui 目录下")
            await app.action_submit_prompt()
            await pilot.pause()

            transcript_before_cleanup = app.query_one("#main_log", TranscriptArea).text
            self.assertIn("› 应该在根目录下 gui 目录下", transcript_before_cleanup)
            self.assertNotIn(
                "Current runtime does not support in-place steering",
                transcript_before_cleanup,
            )
            self.assertEqual(runtime.started_prompts, ["cleanup job"])

            finish_first.set()
            await runtime.wait_started("应该在根目录下 gui 目录下")
            await pilot.pause()
            self.assertEqual(runtime.started_prompts, ["cleanup job", "应该在根目录下 gui 目录下"])

            finish_followup.set()
            await app._wait_for_runtime_idle()
            await pilot.pause()

            transcript = app.query_one("#main_log", TranscriptArea).text
            self.assertIn("• processed 应该在根目录下 gui 目录下", transcript)
            self.assertNotIn("Current runtime does not support in-place steering", transcript)

    async def test_question_mark_toggles_shortcut_overlay_when_composer_empty(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            await pilot.press("?")
            await pilot.pause()

            self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "")
            self.assertIn(app._t("footer.shortcuts_overlay_line1"), self._status_line_plain(app))
            self.assertIn(app._t("footer.shortcuts_overlay_line2"), self._footer_plain(app))

            await pilot.press("?")
            await pilot.pause()

            self.assertNotIn(app._t("footer.shortcuts"), self._status_line_plain(app))
            self.assertIn(app._t("footer.context_left"), self._footer_plain(app))

    async def test_question_mark_is_literal_after_typing(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()

            await pilot.press("h")
            app._flush_prompt_composer_burst()
            await pilot.pause()

            await pilot.press("?")
            app._flush_prompt_composer_burst()
            await pilot.pause()

            self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "h?")
            self.assertNotIn(app._t("footer.shortcuts_overlay_line1"), self._status_line_plain(app))

    def test_elapsed_compact_matches_reference_style(self) -> None:
        self.assertEqual(AgentCliApp._format_elapsed_compact(0), "0s")
        self.assertEqual(AgentCliApp._format_elapsed_compact(59), "59s")
        self.assertEqual(AgentCliApp._format_elapsed_compact(60), "1m 00s")
        self.assertEqual(AgentCliApp._format_elapsed_compact(65), "1m 05s")
        self.assertEqual(AgentCliApp._format_elapsed_compact(3661), "1h 01m 01s")

    async def test_busy_composer_hint_shows_reference_like_running_status(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_busy(True)
            await pilot.pause()
            hint = self._status_line_plain(app)

        self.assertIn(hint[:1], {"•", "●", "◦"})
        self.assertIn(" Working (", hint)
        self.assertIn("esc to interrupt", hint)

    async def test_busy_composer_hint_updates_with_running_activity_title(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_busy(True)
            app._write_live_activity_event(
                ActivityEvent(
                    title="python -V",
                    status="running",
                    kind="command",
                )
            )
            await pilot.pause()
            hint = self._status_line_plain(app)

        self.assertIn(hint[:1], {"•", "●", "◦"})
        self.assertIn(" Running python -V (", hint)
        self.assertIn("esc to interrupt", hint)

    async def test_busy_composer_hint_prefers_reference_style_file_search_label_from_queue(
        self,
    ) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app._queued_run_labels.append("/file_search 数据安全管理办法 --path docs")
            app._set_busy(True)
            await pilot.pause()
            hint = self._status_line_plain(app)

        self.assertIn(hint[:1], {"•", "●", "◦"})
        self.assertIn(" Searching files (", hint)
        self.assertIn("esc to interrupt", hint)

    async def test_busy_composer_hint_prefers_patch_approval_label_from_queue(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app._queued_run_labels.append("/apply_patch *** Begin Patch")
            app._set_busy(True)
            await pilot.pause()
            hint = self._status_line_plain(app)

        self.assertIn(hint[:1], {"•", "●", "◦"})
        self.assertIn(" Requesting patch approval (", hint)
        self.assertIn("esc to interrupt", hint)

    async def test_paste_prompt_inserts_clipboard_text(self) -> None:
        app = AgentCliApp()
        app._read_clipboard_text = lambda: "\u4f60\u597d\uff0c\u4f01\u4e1a\u5fae\u4fe1"

        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_paste_prompt()
            await pilot.pause()
            self.assertEqual(
                app.query_one("#prompt_composer", PromptComposer).text,
                "\u4f60\u597d\uff0c\u4f01\u4e1a\u5fae\u4fe1",
            )

    async def test_native_paste_event_inserts_text_into_composer(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.on_paste(Paste("hello\nworld"))
            await pilot.pause()
            self.assertEqual(composer.text, "hello\nworld")

    async def test_ctrl_v_uses_clipboard_text(self) -> None:
        app = AgentCliApp()
        app._read_clipboard_text = lambda: "ctrl-v paste"

        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+v")
            await pilot.pause()
            self.assertEqual(
                app.query_one("#prompt_composer", PromptComposer).text,
                "ctrl-v paste",
            )

    async def test_short_unicode_native_paste_event_bypasses_paste_pipeline(self) -> None:
        app = AgentCliApp()
        pasted: list[str] = []
        app.handle_paste_burst = lambda text: pasted.append(text)

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.on_paste(Paste("，"))
            await pilot.pause()

            self.assertEqual(pasted, [])
            self.assertEqual(composer.text, "，")

    async def test_paste_prompt_normalizes_dragged_windows_file_path(self) -> None:
        app = AgentCliApp()
        app._read_clipboard_text = lambda: '"C:\\Users\\Alice\\Desktop\\demo file.txt"'

        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_paste_prompt()
            await pilot.pause()
            self.assertEqual(
                app.query_one("#prompt_composer", PromptComposer).text,
                '@"C:\\Users\\Alice\\Desktop\\demo file.txt"',
            )

    async def test_paste_prompt_normalizes_multiple_dragged_windows_paths(self) -> None:
        app = AgentCliApp()
        app._read_clipboard_text = lambda: (
            '"C:\\Users\\Alice\\Desktop\\demo file.txt" ' '"D:\\Work\\notes.md"'
        )

        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_paste_prompt()
            await pilot.pause()
            self.assertEqual(
                app.query_one("#prompt_composer", PromptComposer).text,
                '@"C:\\Users\\Alice\\Desktop\\demo file.txt" @D:\\Work\\notes.md',
            )

    async def test_paste_prompt_normalizes_file_url_to_windows_path(self) -> None:
        app = AgentCliApp()
        app._read_clipboard_text = lambda: "file:///C:/Users/Alice/Desktop/demo%20file.txt"

        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_paste_prompt()
            await pilot.pause()
            self.assertEqual(
                app.query_one("#prompt_composer", PromptComposer).text,
                '@"C:\\Users\\Alice\\Desktop\\demo file.txt"',
            )

    async def test_file_reference_paste_expands_to_plain_path_on_submit(self) -> None:
        app = AgentCliApp()
        app._read_clipboard_text = lambda: '"C:\\Users\\Alice\\Desktop\\demo file.txt"'

        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_paste_prompt()
            await pilot.pause()
            self.assertEqual(
                app.query_one("#prompt_composer", PromptComposer).text,
                '@"C:\\Users\\Alice\\Desktop\\demo file.txt"',
            )
            submitted_text, attachments = self._simulate_submit_without_runtime(app)
            await pilot.pause()
            self.assertEqual(submitted_text, '"C:\\Users\\Alice\\Desktop\\demo file.txt"')
            self.assertEqual(
                [item.path for item in attachments], ["C:\\Users\\Alice\\Desktop\\demo file.txt"]
            )
            transcript = app.query_one("#main_log", TranscriptArea).text
            self.assertIn('› @"C:\\Users\\Alice\\Desktop\\demo file.txt"', transcript)

    async def test_manual_attachment_reference_expands_to_plain_path_on_submit(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text('Summarize @"C:\\Users\\Alice\\Desktop\\demo file.txt"')
            submitted_text, attachments = self._simulate_submit_without_runtime(app)
            await pilot.pause()
            self.assertEqual(submitted_text, 'Summarize "C:\\Users\\Alice\\Desktop\\demo file.txt"')
            self.assertEqual([item.name for item in attachments], ["demo file.txt"])

    async def test_paste_prompt_reports_empty_clipboard(self) -> None:
        app = AgentCliApp()
        app._read_clipboard_text = lambda: ""

        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_paste_prompt()
            await pilot.pause()
            self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "")
            self.assertIn("Clipboard is empty.", app.query_one("#main_log", TranscriptArea).text)

    async def test_large_paste_uses_placeholder_in_composer(self) -> None:
        app = AgentCliApp()
        large = "x" * (AgentCliApp.LARGE_PASTE_CHAR_THRESHOLD + 23)
        app._read_clipboard_text = lambda: large

        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_paste_prompt()
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            self.assertEqual(composer.text, f"[Pasted Content {len(large)} chars]")
            self.assertEqual(app._pending_pastes, [(composer.text, large)])

    async def test_large_paste_expands_on_submit_and_transcript_shows_full_text(self) -> None:
        app = AgentCliApp()
        large = "x" * (AgentCliApp.LARGE_PASTE_CHAR_THRESHOLD + 11)
        app._read_clipboard_text = lambda: large

        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_paste_prompt()
            await pilot.pause()
            placeholder = app.query_one("#prompt_composer", PromptComposer).text
            submitted_text, _ = self._simulate_submit_without_runtime(app)
            await pilot.pause()
            transcript = app.query_one("#main_log", TranscriptArea).text
            self.assertEqual(submitted_text, large)
            self.assertNotIn(f"› {placeholder}", transcript)
            self.assertIn(f"› {large}", transcript)
            self.assertEqual(app._pending_pastes, [])

    async def test_submit_at_character_limit_succeeds(self) -> None:
        app = AgentCliApp()
        app.MAX_USER_INPUT_TEXT_CHARS = 10

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("x" * 10)
            submitted_text, _ = self._simulate_submit_without_runtime(app)
            await pilot.pause()

            self.assertEqual(submitted_text, "x" * 10)
            self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "")
            self.assertNotIn(
                app._user_input_too_large_message(10),
                app.query_one("#main_log", TranscriptArea).text,
            )

    async def test_oversized_submit_reports_error_and_preserves_draft(self) -> None:
        runtime = RecordingRuntime()
        app = AgentCliApp(runtime=runtime)
        app.MAX_USER_INPUT_TEXT_CHARS = 10

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("x" * 11)
            await app.action_submit_prompt()
            await pilot.pause()

            self.assertIsNone(runtime.last_prompt)
            self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "x" * 11)
            self.assertIn(
                app._user_input_too_large_message(11),
                app.query_one("#main_log", TranscriptArea).text,
            )

    async def test_oversized_submit_with_large_paste_placeholder_preserves_draft(self) -> None:
        runtime = RecordingRuntime()
        app = AgentCliApp(runtime=runtime)
        app.LARGE_PASTE_CHAR_THRESHOLD = 5
        app.MAX_USER_INPUT_TEXT_CHARS = 10
        large = "x" * 11
        app._read_clipboard_text = lambda: large

        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_paste_prompt()
            await pilot.pause()

            composer = app.query_one("#prompt_composer", PromptComposer)
            placeholder = composer.text
            await app.action_submit_prompt()
            await pilot.pause()

            self.assertIsNone(runtime.last_prompt)
            self.assertEqual(composer.text, placeholder)
            self.assertEqual(app._pending_pastes, [(placeholder, large)])
            self.assertIn(
                app._user_input_too_large_message(11),
                app.query_one("#main_log", TranscriptArea).text,
            )

    async def test_right_click_on_composer_accepts_native_paste_event(self) -> None:
        app = AgentCliApp()
        app._read_clipboard_text = lambda: (_ for _ in ()).throw(
            AssertionError("sync clipboard read should not happen")
        )

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("hello")
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.on_mouse_down(
                SimpleNamespace(button=3, stop=lambda: None, prevent_default=lambda: None)
            )
            composer.on_paste(Paste(" pasted"))
            await pilot.pause()
            self.assertEqual(composer.text, "hello pasted")

    async def test_left_click_on_composer_moves_cursor_without_pasting(self) -> None:
        app = AgentCliApp()
        app._read_clipboard_text = lambda: " pasted"

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("hello")
            composer.build_render_text(12, focused=True)

            composer.on_mouse_down(
                SimpleNamespace(button=1, x=4, y=0, stop=lambda: None, prevent_default=lambda: None)
            )
            await pilot.pause()

            self.assertEqual(composer.cursor_pos, 2)
            self.assertEqual(composer.text, "hello")

    async def test_left_click_on_wrapped_mixed_width_composer_moves_to_visual_row(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("你好ab世界")
            composer.build_render_text(6, focused=True)
            composer._navigation_total_width = lambda: 6

            composer.on_mouse_down(
                SimpleNamespace(button=1, x=3, y=1, stop=lambda: None, prevent_default=lambda: None)
            )
            await pilot.pause()
            self.assertEqual(composer.cursor_pos, 3)

            composer.on_mouse_down(
                SimpleNamespace(button=1, x=4, y=2, stop=lambda: None, prevent_default=lambda: None)
            )
            await pilot.pause()
            self.assertEqual(composer.cursor_pos, 6)
            self.assertIs(app.focused, composer)

    async def test_mouse_drag_creates_selection_in_composer(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("hello")
            composer.build_render_text(12, focused=True)

            composer.on_mouse_down(
                SimpleNamespace(button=1, x=3, y=0, stop=lambda: None, prevent_default=lambda: None)
            )
            composer.on_mouse_move(
                SimpleNamespace(x=6, y=0, stop=lambda: None, prevent_default=lambda: None)
            )
            composer.on_mouse_up(
                SimpleNamespace(button=1, stop=lambda: None, prevent_default=lambda: None)
            )
            await pilot.pause()

            self.assertTrue(composer.has_selection)
            self.assertEqual(composer.selected_text, "ell")

    async def test_mouse_drag_clamps_to_visible_boundaries(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("abcdefghij")
            composer._navigation_total_width = lambda: 5
            composer.build_render_text(5, focused=True)

            composer.on_mouse_down(
                SimpleNamespace(button=1, x=3, y=0, stop=lambda: None, prevent_default=lambda: None)
            )
            composer.on_mouse_move(
                SimpleNamespace(x=99, y=99, stop=lambda: None, prevent_default=lambda: None)
            )
            composer.on_mouse_up(
                SimpleNamespace(button=1, stop=lambda: None, prevent_default=lambda: None)
            )
            await pilot.pause()

            self.assertTrue(composer.has_selection)
            self.assertEqual(composer.selected_text, "bcdefghij")

    async def test_double_click_selects_word(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("hello world")
            composer.build_render_text(20, focused=True)

            event = SimpleNamespace(
                button=1, x=4, y=0, stop=lambda: None, prevent_default=lambda: None
            )
            composer.on_mouse_down(event)
            composer.on_mouse_down(event)
            await pilot.pause()

            self.assertTrue(composer.has_selection)
            self.assertEqual(composer.selected_text, "hello")

    async def test_triple_click_selects_logical_line(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("alpha\nbeta\ngamma")
            composer.build_render_text(20, focused=True)

            event = SimpleNamespace(
                button=1, x=3, y=1, stop=lambda: None, prevent_default=lambda: None
            )
            composer.on_mouse_down(event)
            composer.on_mouse_down(event)
            composer.on_mouse_down(event)
            await pilot.pause()

            self.assertTrue(composer.has_selection)
            self.assertEqual(composer.selected_text, "beta")

    async def test_right_click_copies_selected_composer_text_instead_of_pasting(self) -> None:
        app = AgentCliApp()
        copied: list[str] = []
        app.copy_to_clipboard = lambda text: copied.append(text)
        app._read_clipboard_text = lambda: " pasted"

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("alpha\nbeta\ngamma")
            composer.build_render_text(20, focused=True)

            event = SimpleNamespace(
                button=1, x=3, y=1, stop=lambda: None, prevent_default=lambda: None
            )
            composer.on_mouse_down(event)
            composer.on_mouse_down(event)
            composer.on_mouse_down(event)
            await pilot.pause()

            right_click = self._MouseEventSpy(button=3)
            composer.on_mouse_down(right_click)
            await pilot.pause()

            self.assertEqual(copied, ["beta"])
            self.assertEqual(composer.text, "alpha\nbeta\ngamma")
            self.assertFalse(composer.has_selection)
            self.assertEqual(composer.selected_text, "")
            self.assertTrue(right_click.stopped)
            self.assertTrue(right_click.prevented)

    async def test_right_click_copy_suppresses_following_native_paste_event(self) -> None:
        app = AgentCliApp()
        copied: list[str] = []
        app.copy_to_clipboard = lambda text: copied.append(text)
        app._read_clipboard_text = lambda: " pasted"

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("alpha\nbeta\ngamma")
            composer.build_render_text(20, focused=True)

            event = SimpleNamespace(
                button=1, x=3, y=1, stop=lambda: None, prevent_default=lambda: None
            )
            composer.on_mouse_down(event)
            composer.on_mouse_down(event)
            composer.on_mouse_down(event)
            await pilot.pause()

            right_click = self._MouseEventSpy(button=3)
            composer.on_mouse_down(right_click)
            composer.on_paste(Paste(" pasted"))
            await pilot.pause()

            self.assertEqual(copied, ["beta"])
            self.assertEqual(composer.text, "alpha\nbeta\ngamma")
            self.assertTrue(right_click.stopped)
            self.assertTrue(right_click.prevented)

    async def test_global_right_click_copies_selected_composer_text_anywhere(self) -> None:
        app = AgentCliApp()
        copied: list[str] = []
        app.copy_to_clipboard = lambda text: copied.append(text)
        app._read_clipboard_text = lambda: (_ for _ in ()).throw(
            AssertionError("clipboard read should not happen while a selection exists")
        )

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            main_log = app.query_one("#main_log", TranscriptArea)
            composer.set_text("hello world")
            composer._selection_anchor = 0
            composer._cursor_pos = 5
            composer._sync()
            event = self._MouseEventSpy(button=3, widget=main_log)

            app.on_mouse_down(event)
            await pilot.pause()

            self.assertEqual(copied, ["hello"])
            self.assertFalse(composer.has_selection)
            self.assertEqual(composer.text, "hello world")
            self.assertTrue(event.stopped)
            self.assertTrue(event.prevented)

    async def test_right_click_on_composer_does_not_sync_read_clipboard(self) -> None:
        app = AgentCliApp()
        app._read_clipboard_text = lambda: (_ for _ in ()).throw(
            AssertionError("sync clipboard read should not happen")
        )

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("hello")

            composer.on_mouse_down(
                SimpleNamespace(button=3, stop=lambda: None, prevent_default=lambda: None)
            )
            await pilot.pause()

            self.assertEqual(composer.text, "hello")

    async def test_attachment_reference_selection_and_delete_are_atomic(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text('read @"C:\\docs\\demo file.txt" now')
            composer._selection_anchor = 8
            composer._cursor_pos = 15
            await pilot.pause()

            self.assertEqual(composer.selected_text, '@"C:\\docs\\demo file.txt"')
            composer.delete_selection()
            await pilot.pause()
            self.assertEqual(composer.text, "read  now")

    async def test_paste_placeholder_delete_is_atomic(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("[Pasted Content 12 chars] tail")
            composer._cursor_pos = 4

            await pilot.press("delete")
            await pilot.pause()
            self.assertEqual(composer.text, " tail")

    async def test_ctrl_c_copies_selection_without_clearing_prompt(self) -> None:
        app = AgentCliApp()
        copied: list[str] = []
        app.copy_to_clipboard = lambda text: copied.append(text)

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("hello")
            composer.move_cursor_left(extend=True)
            composer.move_cursor_left(extend=True)

            await pilot.press("ctrl+c")
            await pilot.pause()

            self.assertEqual(copied, ["lo"])
            self.assertEqual(composer.text, "hello")
            self.assertTrue(composer.has_selection)

    async def test_ctrl_x_cuts_selection_and_ctrl_z_ctrl_shift_z_restore_it(self) -> None:
        app = AgentCliApp()
        copied: list[str] = []
        app.copy_to_clipboard = lambda text: copied.append(text)

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("hello")
            composer.move_cursor_left(extend=True)
            composer.move_cursor_left(extend=True)

            await pilot.press("ctrl+x")
            await pilot.pause()
            self.assertEqual(copied, ["lo"])
            self.assertEqual(composer.text, "hel")

            await pilot.press("ctrl+z")
            await pilot.pause()
            self.assertEqual(composer.text, "hello")

            await pilot.press("ctrl+shift+z")
            await pilot.pause()
            self.assertEqual(composer.text, "hel")

    async def test_action_focused_undo_or_noop_uses_prompt_composer(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("hel")
            composer.insert_text("lo")
            self.assertEqual(composer.text, "hello")

            app.action_focused_undo_or_noop()
            await pilot.pause()

            self.assertEqual(composer.text, "hel")

    async def test_right_click_on_composer_skips_empty_clipboard_notice(self) -> None:
        app = AgentCliApp()
        app._read_clipboard_text = lambda: (_ for _ in ()).throw(
            AssertionError("sync clipboard read should not happen")
        )

        async with app.run_test() as pilot:
            await pilot.pause()
            initial_transcript = app.query_one("#main_log", TranscriptArea).text
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.on_mouse_down(
                SimpleNamespace(button=3, stop=lambda: None, prevent_default=lambda: None)
            )
            await pilot.pause()
            self.assertEqual(composer.text, "")
            self.assertEqual(app.query_one("#main_log", TranscriptArea).text, initial_transcript)

    async def test_global_right_click_pastes_clipboard_into_composer(self) -> None:
        app = AgentCliApp()
        app._read_clipboard_text = lambda: " pasted"

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            main_log = app.query_one("#main_log", TranscriptArea)
            composer.set_text("hello")
            event = self._MouseEventSpy(button=3, widget=main_log)

            app.on_mouse_down(event)
            await pilot.pause()

            self.assertEqual(composer.text, "hello pasted")
            self.assertTrue(event.stopped)
            self.assertTrue(event.prevented)
            self.assertIs(app.focused, composer)

    async def test_ctrl_c_clears_prompt_instead_of_quitting(self) -> None:
        app = AgentCliApp()
        app.QUIT_SHORTCUT_TIMEOUT_SECONDS = 30.0

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("hello world")
            await pilot.press("ctrl+c")
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            self.assertEqual(composer.text, "")
            self.assertIs(app.focused, composer)

    async def test_second_ctrl_c_within_timeout_exits(self) -> None:
        app = AgentCliApp()
        app.QUIT_SHORTCUT_TIMEOUT_SECONDS = 30.0
        exited: list[bool] = []
        app.exit = lambda *args, **kwargs: exited.append(True)

        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_ctrl_c()
            await pilot.pause()
            self.assertEqual(exited, [])
            app.action_ctrl_c()
            await pilot.pause()
            self.assertEqual(exited, [True])

    async def test_second_ctrl_c_within_timeout_starts_shutdown_before_exit(self) -> None:
        app = AgentCliApp()
        app.QUIT_SHORTCUT_TIMEOUT_SECONDS = 30.0
        app.runtime.thread_id = "thread_ctrl_c_exit"
        calls: list[str] = []
        original_begin_shutdown = app._begin_shutdown

        def tracked_begin_shutdown() -> None:
            calls.append("shutdown")
            original_begin_shutdown()

        app._begin_shutdown = tracked_begin_shutdown
        app.exit = lambda *args, **kwargs: calls.append("exit")

        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_ctrl_c()
            await pilot.pause()
            app.action_ctrl_c()
            await pilot.pause()

            self.assertEqual(calls, ["shutdown", "exit"])
            self.assertTrue(app._shutdown_initiated)
            self.assertTrue(app._exit_requested)
            self.assertEqual(app._exit_thread_id, "thread_ctrl_c_exit")
            self.assertEqual(app._exit_resume_command, "agenthub resume thread_ctrl_c_exit")
            self.assertIsNone(app._dynamic_hint_timer)
            self.assertIsNone(app._prompt_burst_timer)

    async def test_begin_shutdown_closes_preview_pane_once(self) -> None:
        app = AgentCliApp()
        calls: list[str] = []

        os.environ["AGENTHUB_TMUX_LAYOUT_OWNS_PREVIEW"] = "1"
        with patch(
            "cli.agent_cli.ui.transcript_preview_pane.close_preview_pane",
            side_effect=lambda: calls.append("close"),
        ):
            try:
                async with app.run_test() as pilot:
                    await pilot.pause()
                    app._begin_shutdown()
                    app._begin_shutdown()
                    await pilot.pause()
            finally:
                os.environ.pop("AGENTHUB_TMUX_LAYOUT_OWNS_PREVIEW", None)

        self.assertEqual(calls, ["close"])

    async def test_begin_shutdown_does_not_close_unowned_preview_pane(self) -> None:
        app = AgentCliApp()
        calls: list[str] = []
        os.environ.pop("AGENTHUB_TMUX_LAYOUT_OWNS_PREVIEW", None)

        with patch(
            "cli.agent_cli.ui.transcript_preview_pane.close_preview_pane",
            side_effect=lambda: calls.append("close"),
        ):
            async with app.run_test() as pilot:
                await pilot.pause()
                app._begin_shutdown()
                await pilot.pause()

        self.assertEqual(calls, [])

    async def test_preview_close_command_closes_and_disables_preview_pane(self) -> None:
        app = AgentCliApp()
        os.environ.pop("AGENTHUB_PREVIEW_DISABLED", None)
        response = PromptResponse(
            user_text="/preview close",
            assistant_text="Preview close requested.",
            tool_events=[
                ToolEvent(
                    name="preview_control_requested",
                    ok=True,
                    summary="preview close",
                    payload={"action": "close"},
                )
            ],
            handled_as_command=True,
        )
        calls: list[str] = []

        with patch(
            "cli.agent_cli.ui.transcript_preview_pane.close_preview_pane",
            side_effect=lambda: calls.append("close") or True,
        ):
            async with app.run_test() as pilot:
                await pilot.pause()
                app._handle_runtime_response(response)
                await pilot.pause()

        self.assertEqual(calls, ["close"])
        self.assertEqual(os.environ.get("AGENTHUB_PREVIEW_DISABLED"), "1")
        os.environ.pop("AGENTHUB_PREVIEW_DISABLED", None)

    async def test_preview_open_command_enables_and_opens_preview_pane(self) -> None:
        app = AgentCliApp()
        os.environ["AGENTHUB_PREVIEW_DISABLED"] = "1"
        response = PromptResponse(
            user_text="/preview open",
            assistant_text="Preview open requested.",
            tool_events=[
                ToolEvent(
                    name="preview_control_requested",
                    ok=True,
                    summary="preview open",
                    payload={"action": "open"},
                )
            ],
            handled_as_command=True,
        )
        calls: list[str] = []

        with patch(
            "cli.agent_cli.ui.transcript_preview_pane.open_preview_pane",
            side_effect=lambda: calls.append("open") or "%9",
        ):
            async with app.run_test() as pilot:
                await pilot.pause()
                app._handle_runtime_response(response)
                await pilot.pause()

        self.assertEqual(calls, ["open"])
        self.assertNotIn("AGENTHUB_PREVIEW_DISABLED", os.environ)

    async def test_ctrl_c_hint_can_clear_without_quitting(self) -> None:
        app = AgentCliApp()
        app.QUIT_SHORTCUT_TIMEOUT_SECONDS = 30.0

        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_ctrl_c()
            await pilot.pause()
            self.assertEqual(self._status_line_plain(app), "• Press Ctrl+C again to quit")
            app._clear_quit_shortcut()
            await pilot.pause()
            self.assertEqual(self._status_line_plain(app), "")

    async def test_ctrl_c_interrupts_busy_run_and_arms_quit_shortcut(self) -> None:
        runtime = InterruptRecordingRuntime()
        app = AgentCliApp(runtime=runtime)
        app.QUIT_SHORTCUT_TIMEOUT_SECONDS = 30.0

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_busy(True)
            await pilot.press("ctrl+c")
            await pilot.pause()

            self.assertEqual(runtime.interrupt_calls, 1)
            self.assertTrue(app._quit_shortcut_active())
            self.assertEqual(self._status_line_plain(app), "• Press Ctrl+C again to quit")
            self.assertEqual(app.query_one("#main_log", TranscriptArea).text, "")

    async def test_second_ctrl_c_during_busy_run_exits(self) -> None:
        runtime = InterruptRecordingRuntime()
        app = AgentCliApp(runtime=runtime)
        app.QUIT_SHORTCUT_TIMEOUT_SECONDS = 30.0
        exited: list[bool] = []
        app.exit = lambda *args, **kwargs: exited.append(True)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_busy(True)
            await pilot.press("ctrl+c")
            await pilot.pause()
            await pilot.press("ctrl+c")
            await pilot.pause()

        self.assertEqual(runtime.interrupt_calls, 1)
        self.assertEqual(exited, [True])

    async def test_refresh_dynamic_hint_noops_after_shutdown_begins(self) -> None:
        app = AgentCliApp()
        refresh_calls: list[int] = []

        async with app.run_test() as pilot:
            await pilot.pause()
            app._begin_shutdown()
            app._update_bottom_dock = lambda width: refresh_calls.append(width)

            app._refresh_dynamic_hint()
            await pilot.pause()

            self.assertEqual(refresh_calls, [])

    async def test_fast_large_ascii_burst_uses_placeholder(self) -> None:
        app = AgentCliApp()
        count = AgentCliApp.LARGE_PASTE_CHAR_THRESHOLD + 5

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            event = self._fake_printable_key("x")
            for _ in range(count):
                composer.on_key(event)
            await asyncio.sleep(PromptComposer.PASTE_BURST_FLUSH_SECONDS + 0.05)
            composer.flush_paste_burst()
            await pilot.pause()
            expected = f"[Pasted Content {count} chars]"
            self.assertEqual(composer.text, expected)
            self.assertEqual(app._pending_pastes, [(expected, "x" * count)])

    async def test_first_ascii_char_flushes_as_typed_after_short_delay(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.on_key(self._fake_printable_key("h"))
            self.assertEqual(composer.text, "")
            await asyncio.sleep(PromptComposer.PASTE_BURST_FLUSH_SECONDS + 0.05)
            await pilot.pause()
            self.assertEqual(composer.text, "h")
            self.assertEqual(app._pending_pastes, [])

    async def test_humanlike_ascii_typing_does_not_create_paste_placeholder(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            for character in "hello":
                composer.on_key(self._fake_printable_key(character))
                await asyncio.sleep(PromptComposer.PASTE_BURST_FLUSH_SECONDS + 0.02)
                await pilot.pause()
            composer.flush_paste_burst()
            await pilot.pause()
            self.assertEqual(composer.text, "hello")
            self.assertEqual(app._pending_pastes, [])

    async def test_editing_away_placeholder_clears_pending_paste(self) -> None:
        app = AgentCliApp()
        large = "x" * (AgentCliApp.LARGE_PASTE_CHAR_THRESHOLD + 9)
        app._read_clipboard_text = lambda: large

        async with app.run_test() as pilot:
            await pilot.pause()
            app.action_paste_prompt()
            await pilot.pause()
            self.assertEqual(len(app._pending_pastes), 1)
            app._set_prompt_text("manual replacement")
            await pilot.pause()
            self.assertEqual(app._pending_pastes, [])

    async def test_submit_prompt_clears_composer_and_logs_user_text(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("Summarize and prepare a safe draft.")
            submitted_text, _ = self._simulate_submit_without_runtime(app)
            await pilot.pause()
            self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "")
            transcript = app.query_one("#main_log", TranscriptArea).text
            self.assertIn("› Summarize and prepare a safe draft.", transcript)
            self.assertEqual(submitted_text, "Summarize and prepare a safe draft.")
            self.assertNotIn("\nyou\n", transcript)
            self.assertNotIn("\nassistant\n", transcript)

    async def test_enter_submits_prompt(self) -> None:
        app = AgentCliApp()
        submitted: list[str] = []
        submit_scheduled = asyncio.Event()

        async def record_submit() -> None:
            submitted.append(app._current_prompt_text())
            app._clear_prompt_text()
            app._refresh_prompt_composer()
            submit_scheduled.set()

        app.action_submit_prompt = record_submit  # type: ignore[method-assign]

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("Send on enter")
            await pilot.press("enter")
            await asyncio.wait_for(submit_scheduled.wait(), timeout=1.0)
            await pilot.pause()
            self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "")
            self.assertEqual(submitted, ["Send on enter"])

    async def test_render_response_can_show_commentary_before_final_answer(self) -> None:
        app = AgentCliApp()

        async with app.run_test():
            app._render_response(
                PromptResponse(
                    user_text="hello",
                    commentary_text="Inspecting current project state.",
                    assistant_text="Current directory contents are ready.",
                    status=app.runtime.agent.provider_status(),
                )
            )
            transcript = app.query_one("#main_log", TranscriptArea).text

        self.assertIn("◦ Inspecting current project state.", transcript)
        self.assertIn("• Current directory contents are ready.", transcript)
        self.assertLess(
            transcript.index("◦ Inspecting current project state."),
            transcript.index("• Current directory contents are ready."),
        )
        self.assertNotIn("─" * 77, transcript)

    async def test_render_command_response_uses_structured_display_text(self) -> None:
        app = AgentCliApp()

        async with app.run_test():
            app._render_response(
                PromptResponse(
                    user_text="/provider openai",
                    assistant_text=(
                        "switched provider to openai and saved as user default\n"
                        "provider_name=openai\n"
                        "provider_model=gpt-5.5"
                    ),
                    command_display_text="switched provider to openai and saved as user default",
                    handled_as_command=True,
                    status=app.runtime.agent.provider_status(),
                )
            )
            transcript = app.query_one("#main_log", TranscriptArea).text

        self.assertIn("• switched provider to openai and saved as user default", transcript)
        self.assertNotIn("provider_model=gpt-5.5", transcript)

    async def test_live_turn_events_render_incrementally_and_deduplicates_phase_less_final_backfill(
        self,
    ) -> None:
        app = AgentCliApp()

        async with app.run_test():
            app._begin_activity_capture()
            app._write_live_turn_event(
                {
                    "type": "item.started",
                    "item": {"id": "item_reason", "type": "reasoning", "text": "先检查 workspace"},
                }
            )
            app._write_live_turn_event(
                {
                    "type": "item.updated",
                    "item": {
                        "id": "item_reason",
                        "type": "reasoning",
                        "text": "先检查 workspace，再读入口",
                    },
                }
            )
            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_msg",
                        "type": "agent_message",
                        "text": "入口在 cli/agent_cli/headless.py",
                    },
                }
            )
            app._render_response(
                PromptResponse(
                    user_text="hello",
                    commentary_text="先检查 workspace，再读入口",
                    assistant_text="入口在 cli/agent_cli/headless.py",
                    status=app.runtime.agent.provider_status(),
                    response_items=[],
                )
            )
            transcript = app.query_one("#main_log", TranscriptArea).text

        self.assertIn(
            "• 入口在 cli/agent_cli/headless.py\n\n◦ 先检查 workspace，再读入口",
            transcript,
        )
        self.assertEqual(transcript.count("• 入口在 cli/agent_cli/headless.py"), 1)

    async def test_live_turn_completed_promotes_last_agent_message_to_final_layer(self) -> None:
        app = AgentCliApp(language="zh-CN")

        async with app.run_test():
            app._begin_activity_capture()
            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_preamble",
                        "type": "agent_message",
                        "text": "我先查看当前目录内容。",
                    },
                }
            )
            app._write_live_turn_event(
                {
                    "type": "item.started",
                    "item": {
                        "id": "item_tool",
                        "type": "mcp_tool_call",
                        "tool": "list_dir",
                        "arguments": {"dir_path": "."},
                        "status": "in_progress",
                    },
                }
            )
            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_tool",
                        "type": "mcp_tool_call",
                        "tool": "list_dir",
                        "arguments": {"dir_path": "."},
                        "result": {
                            "content": [{"type": "text", "text": "E1: [file] README.md"}],
                            "structured_content": {"dir_path": ".", "count": 1},
                        },
                        "status": "completed",
                    },
                }
            )
            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_answer",
                        "type": "agent_message",
                        "text": "当前目录内容已经列出来了。",
                    },
                }
            )
            before_completed = app.query_one("#main_log", TranscriptArea).text
            app._write_live_turn_event({"type": "turn.completed"})
            after_completed = app.query_one("#main_log", TranscriptArea).text

        self.assertIn("◦ 我先查看当前目录内容。", before_completed)
        self.assertIn("◆ Explored", before_completed)
        self.assertIn("  └ List .", before_completed)
        self.assertIn("• 当前目录内容已经列出来了。", before_completed)
        self.assertIn("◆ Explored\n  └ List .", after_completed)
        self.assertRegex(after_completed, r"─{2,}完成\d{2}:\d{2}，用时\d+[sm]─*")
        self.assertIn("• 当前目录内容已经列出来了。", after_completed)

    async def test_live_command_execution_turn_events_render_incrementally(self) -> None:
        app = AgentCliApp()

        async with app.run_test():
            app._begin_activity_capture()
            app._write_live_turn_event(
                {
                    "type": "item.started",
                    "item": {
                        "id": "item_cmd",
                        "type": "command_execution",
                        "command": "python -V",
                        "aggregated_output": "",
                        "exit_code": None,
                        "status": "in_progress",
                    },
                }
            )
            started_transcript = app.query_one("#main_log", TranscriptArea).text
            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_cmd",
                        "type": "command_execution",
                        "command": "python -V",
                        "aggregated_output": "Python 3.13.0",
                        "exit_code": 0,
                        "status": "completed",
                    },
                }
            )
            completed_transcript = app.query_one("#main_log", TranscriptArea).text

        self.assertIn("$ Running python -V", started_transcript)
        self.assertIn("$ Ran python -V", completed_transcript)
        self.assertNotIn("$ Running python -V", completed_transcript)
        self.assertIn("  └ Python 3.13.0", completed_transcript)

    async def test_live_provider_shell_turn_events_collapse_to_single_command_execution_entry(
        self,
    ) -> None:
        app = AgentCliApp()

        async with app.run_test():
            app._begin_activity_capture()
            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "shell_call",
                        "call_id": "call_shell_1",
                        "action": {
                            "type": "exec",
                            "command": ["python", "-V"],
                        },
                        "status": "completed",
                    },
                }
            )
            started_transcript = app.query_one("#main_log", TranscriptArea).text
            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "shell_call_output",
                        "call_id": "call_shell_1",
                        "status": "completed",
                        "output": [
                            {
                                "stdout": "Python 3.13.0\n",
                                "stderr": "",
                                "outcome": {"type": "exit", "exit_code": 0},
                            }
                        ],
                    },
                }
            )
            completed_transcript = app.query_one("#main_log", TranscriptArea).text

        self.assertIn("$ Ran python -V", started_transcript)
        self.assertIn("$ Ran python -V", completed_transcript)
        self.assertEqual(completed_transcript.count("$ Ran python -V"), 1)
        self.assertIn("  └ Python 3.13.0", completed_transcript)
        self.assertNotIn("shell_call", completed_transcript)

    async def test_failed_command_activity_is_replaced_by_matching_command_execution_turn_item(
        self,
    ) -> None:
        app = AgentCliApp()
        command = 'cd /home/lyc/project/gemini-cli && grep -c "<<<<<<< Updated upstream" package-lock.json'

        async with app.run_test():
            app._begin_activity_capture()
            app._write_live_activity_event(
                ActivityEvent(
                    title=f"Command failed: {command}",
                    status="error",
                    kind="command",
                    detail="exit 1 | 0.01s",
                    params={"command": command, "call_id": "call_shell_1"},
                )
            )
            activity_transcript = app.query_one("#main_log", TranscriptArea).text

            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "call_shell_1",
                        "type": "command_execution",
                        "command": command,
                        "aggregated_output": "package-lock.json:0",
                        "exit_code": 1,
                        "status": "failed",
                    },
                }
            )
            completed_transcript = app.query_one("#main_log", TranscriptArea).text

        self.assertIn("✗ Command failed:", activity_transcript)
        self.assertIn("✗ Ran cd /home/lyc/project/gemini-cli", completed_transcript)
        self.assertIn('grep -c "<<<<<<< Updated upstream"', completed_transcript)
        self.assertIn("  └ package-lock.json:0", completed_transcript)
        self.assertNotIn("✗ Command failed:", completed_transcript)

    async def test_interrupt_hides_todo_updates_and_keeps_only_interrupted_final_message(
        self,
    ) -> None:
        runtime = InterruptRecordingRuntime()
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._begin_activity_capture()
            app._write_live_turn_event(
                {
                    "type": "item.started",
                    "item": {
                        "id": "item_plan",
                        "type": "todo_list",
                        "items": [{"text": "inspect workspace", "completed": False}],
                    },
                }
            )
            self.assertIn("□ Todo List", app.query_one("#main_log", TranscriptArea).text)

            app._set_busy(True)
            app.action_interrupt_run()
            await pilot.pause()

            interrupted_transcript = app.query_one("#main_log", TranscriptArea).text
            self.assertEqual(runtime.interrupt_calls, 1)
            self.assertNotIn("□ Todo List", interrupted_transcript)
            self.assertIn(app._t("assistant.conversation_interrupted"), interrupted_transcript)

            app._write_live_turn_event(
                {
                    "type": "item.updated",
                    "item": {
                        "id": "item_plan",
                        "type": "todo_list",
                        "items": [{"text": "inspect workspace", "completed": True}],
                    },
                }
            )
            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {"id": "item_msg", "type": "agent_message", "text": "继续执行中"},
                }
            )
            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_interrupt",
                        "type": "agent_message",
                        "text": REFERENCE_CONVERSATION_INTERRUPTED_TEXT,
                    },
                }
            )
            final_transcript = app.query_one("#main_log", TranscriptArea).text

        self.assertNotIn("□ Todo List", final_transcript)
        self.assertNotIn("继续执行中", final_transcript)
        self.assertIn(app._t("assistant.conversation_interrupted"), final_transcript)

    async def test_interrupt_suppresses_todo_backfill_after_runtime_response(self) -> None:
        runtime = InterruptRecordingRuntime()
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._begin_activity_capture()
            app._set_busy(True)
            app.action_interrupt_run()
            await pilot.pause()

            app._render_response(
                PromptResponse(
                    user_text="plan task",
                    assistant_text=REFERENCE_CONVERSATION_INTERRUPTED_TEXT,
                    status=app.runtime.agent.provider_status(),
                    turn_events=[
                        {
                            "type": "item.updated",
                            "item": {
                                "id": "item_plan",
                                "type": "todo_list",
                                "items": [{"text": "inspect workspace", "completed": False}],
                            },
                        },
                        {
                            "type": "item.completed",
                            "item": {
                                "id": "item_msg",
                                "type": "agent_message",
                                "text": REFERENCE_CONVERSATION_INTERRUPTED_TEXT,
                            },
                        },
                        {"type": "turn.completed"},
                    ],
                )
            )
            transcript = app.query_one("#main_log", TranscriptArea).text

        self.assertNotIn("□ Todo List", transcript)
        self.assertIn(app._t("assistant.conversation_interrupted"), transcript)
        self.assertEqual(
            sum(
                1
                for entry in app._transcript_entries
                if str(entry.raw_content or "").strip()
                == app._t("assistant.conversation_interrupted")
            ),
            1,
        )

    async def test_interrupt_message_is_localized_in_zh_cn_ui_and_uses_error_style(self) -> None:
        app = AgentCliApp(runtime=RecordingRuntime(), language="zh-CN")

        async with app.run_test():
            app._render_response(
                PromptResponse(
                    user_text="中断一下",
                    assistant_text=REFERENCE_CONVERSATION_INTERRUPTED_TEXT,
                    status=app.runtime.agent.provider_status(),
                )
            )
            transcript = app.query_one("#main_log", TranscriptArea).text
            rendered = render_transcript_visual_entries(
                app._transcript_entries, width=80, theme=app._theme
            )

        self.assertIn("对话已中断，请告诉模型接下来需要如何调整。", transcript)
        self.assertNotIn(REFERENCE_CONVERSATION_INTERRUPTED_TEXT, transcript)
        self.assertEqual(rendered.lines, ["• 对话已中断，请告诉模型接下来需要如何调整。"])
        error_spans = [
            style
            for _start, _end, style in rendered.line_styles[0]
            if style.color == RichColor.parse(app._theme.error)
        ]
        self.assertTrue(error_spans)
        self.assertTrue(any(bool(style.bold) for style in error_spans))

    async def test_live_mcp_tool_turn_events_render_incrementally_and_skip_final_duplicate_activity(
        self,
    ) -> None:
        app = AgentCliApp()
        tool_event = ToolEvent(
            name="list_dir",
            ok=True,
            summary="entries=2",
            payload={
                "dir_path": "cli/agent_cli/providers",
                "count": 2,
                "entries": [
                    {
                        "index": 1,
                        "kind": "file",
                        "path": "cli/agent_cli/providers/openai_planner.py",
                    },
                    {"index": 2, "kind": "file", "path": "cli/agent_cli/providers/tool_calls.py"},
                ],
                "text": "E1: [file] cli/agent_cli/providers/openai_planner.py\nE2: [file] cli/agent_cli/providers/tool_calls.py",
            },
        )

        async with app.run_test():
            app._begin_activity_capture()
            app._write_live_turn_event(
                {
                    "type": "item.started",
                    "item": {
                        "id": "item_tool",
                        "type": "mcp_tool_call",
                        "tool": "list_dir",
                        "arguments": {"dir_path": "cli/agent_cli/providers"},
                        "status": "in_progress",
                    },
                }
            )
            started_transcript = app.query_one("#main_log", TranscriptArea).text

            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_tool",
                        "type": "mcp_tool_call",
                        "tool": "list_dir",
                        "arguments": {"dir_path": "cli/agent_cli/providers"},
                        "result": {
                            "content": [{"type": "text", "text": tool_event.payload["text"]}],
                            "structured_content": dict(tool_event.payload),
                        },
                        "status": "completed",
                    },
                }
            )
            completed_transcript = app.query_one("#main_log", TranscriptArea).text

            app._render_response(
                PromptResponse(
                    user_text="inspect providers",
                    assistant_text="已列出目录。",
                    activity_events=activity_events_for_tool_event(tool_event),
                    status=app.runtime.agent.provider_status(),
                )
            )
            final_transcript = app.query_one("#main_log", TranscriptArea).text

        self.assertIn("◆ Exploring", started_transcript)
        self.assertIn("  └ List cli/agent_cli/providers", started_transcript)
        self.assertIn("◆ Explored", completed_transcript)
        self.assertIn("  └ List cli/agent_cli/providers", completed_transcript)
        self.assertNotIn("◆ Exploring", completed_transcript)
        self.assertEqual(final_transcript.count("◆ Explored"), 1)

    async def test_live_web_search_turn_events_render_compact_web_cell_without_raw_tool_invocation(
        self,
    ) -> None:
        app = AgentCliApp()

        async with app.run_test():
            app._begin_activity_capture()
            app._write_live_turn_event(
                {
                    "type": "item.started",
                    "item": {
                        "id": "item_web",
                        "type": "mcp_tool_call",
                        "server": "local",
                        "tool": "web_search",
                        "arguments": {"query": "北京 今天天气", "limit": 5},
                        "search_phase": "search_dispatched",
                        "status": "in_progress",
                    },
                }
            )
            started_transcript = app.query_one("#main_log", TranscriptArea).text

            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_web",
                        "type": "mcp_tool_call",
                        "server": "local",
                        "tool": "web_search",
                        "arguments": {"query": "北京 今天天气", "limit": 5},
                        "search_phase": "search_results_received",
                        "result": {
                            "content": [{"type": "text", "text": "北京当前多云，22°C。"}],
                            "structured_content": {
                                "query": "北京 今天天气",
                                "count": 1,
                                "engine": "openai_native_web_search",
                                "web_search_route": {
                                    "effective_backend_id": "provider_native_openai_responses_web_search",
                                    "effective_backend_kind": "provider_native",
                                    "execution_path": "openai_responses_native",
                                },
                                "results": [
                                    {
                                        "rank": 1,
                                        "title": "北京天气",
                                        "url": "https://weather.com/weather/today/l/Beijing",
                                        "source_domain": "weather.com",
                                        "credibility_label": "high",
                                    }
                                ],
                            },
                        },
                        "status": "completed",
                    },
                }
            )
            completed_transcript = app.query_one("#main_log", TranscriptArea).text

        self.assertIn("⌕ Searching the web", started_transcript)
        self.assertIn("  └ 北京 今天天气", started_transcript)
        self.assertIn("  │ state: search_dispatched", started_transcript)
        self.assertIn("⌕ Native web search", completed_transcript)
        self.assertIn("  └ 北京 今天天气", completed_transcript)
        self.assertIn("  │ state: search_results_received", completed_transcript)
        self.assertIn("  │ backend: native", completed_transcript)
        self.assertIn("  │ count: 1", completed_transcript)
        self.assertNotIn("local.web_search", completed_transcript)
        self.assertEqual(completed_transcript.count("⌕ Searching the web"), 0)

    async def test_live_web_search_turn_events_render_compact_interrupted_reason(self) -> None:
        app = AgentCliApp()

        async with app.run_test():
            app._begin_activity_capture()
            app._write_live_turn_event(
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_web_fail",
                        "type": "mcp_tool_call",
                        "server": "local",
                        "tool": "web_search",
                        "arguments": {"query": "北京 明天天气", "limit": 5},
                        "result": {
                            "content": [{"type": "text", "text": ""}],
                            "structured_content": {
                                "ok": False,
                                "query": "北京 明天天气",
                                "count": 0,
                                "engine": "openai_native_web_search",
                                "display_message": "native web search response was incomplete before usable results were received",
                                "web_search_outcome": "native_interrupted",
                                "web_search_route": {
                                    "effective_backend_id": "provider_native_openai_responses_web_search",
                                    "effective_backend_kind": "provider_native",
                                    "execution_path": "openai_responses_native",
                                },
                            },
                        },
                        "status": "completed",
                    },
                }
            )
            transcript = app.query_one("#main_log", TranscriptArea).text

        self.assertIn("✗ Native web search failed", transcript)
        self.assertIn("  └ 北京 明天天气", transcript)
        self.assertIn("  │ state: native_interrupted", transcript)
        self.assertIn("  │ backend: native", transcript)
        self.assertIn("reason: native web search response was incomplete", transcript)
        self.assertIn("were received", transcript)

    async def test_activity_commentary_and_final_reply_stay_visually_grouped_by_layer(self) -> None:
        app = AgentCliApp()

        async with app.run_test():
            app._write_activity_event(
                ActivityEvent(
                    title="select_conversation",
                    status="running",
                    kind="tool",
                )
            )
            app._render_response(
                PromptResponse(
                    user_text="hello",
                    commentary_text="Inspecting current project state.",
                    assistant_text="Current directory contents are ready.",
                    status=app.runtime.agent.provider_status(),
                )
            )
            transcript = app.query_one("#main_log", TranscriptArea).text

        self.assertIn(
            "◆ Running select_conversation\n\n◦ Inspecting current project state.",
            transcript,
        )
        self.assertLess(
            transcript.index("◦ Inspecting current project state."),
            transcript.index("• Current directory contents are ready."),
        )

    def test_transcript_block_formats_match_reference_style(self) -> None:
        self.assertEqual(
            AgentCliApp._format_transcript_block(
                "你好", first_prefix="› ", continuation_prefix="  "
            ),
            ["› 你好"],
        )
        self.assertEqual(
            AgentCliApp._format_transcript_block(
                "你好！有什么我可以帮你的吗？", first_prefix="• ", continuation_prefix="  "
            ),
            ["• 你好！有什么我可以帮你的吗？"],
        )
        self.assertEqual(
            AgentCliApp._format_transcript_block(
                "第一行\n第二行", first_prefix="› ", continuation_prefix="  "
            ),
            ["› 第一行", "  第二行"],
        )

    async def test_ctrl_j_inserts_newline(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("line1")
            await pilot.press("ctrl+j")
            await pilot.pause()
            self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "line1\n")

    async def test_escape_then_enter_fallback_inserts_newline_without_submitting(self) -> None:
        app = AgentCliApp(runtime=RecordingRuntime())

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("line1")
            await pilot.pause()

            await pilot.press("escape", "enter")
            await pilot.pause()

            composer = app.query_one("#prompt_composer", PromptComposer)
            transcript = app.query_one("#main_log", TranscriptArea).text
            self.assertEqual(composer.text, "line1\n")
            self.assertEqual(getattr(app.runtime, "last_prompt", None), None)
            self.assertEqual(transcript.strip(), "")

    async def test_ctrl_left_moves_cursor_by_word(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("alpha beta")
            await pilot.press("ctrl+left")
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            self.assertEqual(composer.cursor_pos, 6)
            self.assert_cursor_render(composer, 16, "› alpha beta", 8)

    async def test_ctrl_right_moves_cursor_by_word(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("alpha beta")
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.move_cursor_home()
            await pilot.press("ctrl+right")
            await pilot.pause()
            self.assertEqual(composer.cursor_pos, 5)
            self.assert_cursor_render(composer, 16, "› alpha beta", 7)

    async def test_up_arrow_recalls_persistent_prompt_history_across_app_instances(self) -> None:
        with TemporaryDirectory() as tmpdir:
            history_home = Path(tmpdir)
            seed_app = AgentCliApp(prompt_history_home=history_home)
            seed_app._record_prompt_history("first command")
            seed_app._record_prompt_history("second command")
            app = AgentCliApp(prompt_history_home=history_home)

            async with app.run_test() as pilot:
                await pilot.pause()
                composer = app.query_one("#prompt_composer", PromptComposer)
                self.assertEqual(composer.text, "")

                await pilot.press("down")
                await pilot.pause()
                self.assertEqual(composer.text, "")

                await pilot.press("up")
                await pilot.pause()
                self.assertEqual(composer.text, "second command")

                await pilot.press("up")
                await pilot.pause()
                self.assertEqual(composer.text, "first command")

                await pilot.press("down")
                await pilot.pause()
                self.assertEqual(composer.text, "second command")

                await pilot.press("down")
                await pilot.pause()
                self.assertEqual(composer.text, "")

    async def test_ctrl_p_and_ctrl_n_navigate_prompt_history(self) -> None:
        with TemporaryDirectory() as tmpdir:
            history_home = Path(tmpdir)
            seed_app = AgentCliApp(prompt_history_home=history_home)
            seed_app._record_prompt_history("first command")
            seed_app._record_prompt_history("second command")
            app = AgentCliApp(prompt_history_home=history_home)

            async with app.run_test() as pilot:
                await pilot.pause()
                composer = app.query_one("#prompt_composer", PromptComposer)
                self.assertEqual(composer.text, "")

                composer.post_message(events.Key("ctrl+p", None))
                await pilot.pause()
                self.assertEqual(composer.text, "second command")

                composer.post_message(events.Key("ctrl+p", None))
                await pilot.pause()
                self.assertEqual(composer.text, "first command")

                composer.post_message(events.Key("ctrl+n", None))
                await pilot.pause()
                self.assertEqual(composer.text, "second command")

                composer.post_message(events.Key("ctrl+n", None))
                await pilot.pause()
                self.assertEqual(composer.text, "")

    def test_prompt_history_store_metadata_and_lookup(self) -> None:
        with TemporaryDirectory() as tmpdir:
            history_home = Path(tmpdir)
            app = AgentCliApp(prompt_history_home=history_home)
            app._record_prompt_history("alpha")
            app._record_prompt_history("beta")

            reloaded = AgentCliApp(prompt_history_home=history_home)
            self.assertEqual(reloaded._prompt_history.history_entry_count, 2)
            self.assertEqual(
                reloaded._prompt_history.store.lookup(reloaded._prompt_history.history_log_id, 0),
                "alpha",
            )
            self.assertEqual(
                reloaded._prompt_history.store.lookup(reloaded._prompt_history.history_log_id, 1),
                "beta",
            )

    async def test_slash_popup_shows_matching_help_command(self) -> None:
        app = AgentCliApp(runtime=SlashPopupRuntime())

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("/he")
            await pilot.pause()
            popup = app.query_one("#slash_popup", SlashCommandPopup)
            self.assertEqual(popup.styles.display, "block")
            self.assertIn("/help", popup.render().plain)
            self.assertIn("show available slash commands", popup.render().plain)
            self.assertTrue(any("bold" in str(span.style) for span in popup.render().spans))

    async def test_busy_slash_popup_shows_disabled_commands(self) -> None:
        app = AgentCliApp(runtime=SlashPopupRuntime())

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_busy(True)
            app._set_prompt_text("/ch")
            await pilot.pause()
            popup = app.query_one("#slash_popup", SlashCommandPopup)
            self.assertEqual(popup.styles.display, "block")
            rendered = popup.render().plain
            self.assertIn("/chat", rendered)
            self.assertIn("Slash commands are unavailable while a task is in progress.", rendered)

    async def test_post_interrupt_slash_popup_does_not_disable_commands(self) -> None:
        app = AgentCliApp(runtime=SlashPopupRuntime())

        async with app.run_test() as pilot:
            await pilot.pause()
            app._has_pending_runtime_work = lambda: True  # type: ignore[method-assign]
            app._live_turn_interrupt_requested = True
            app._set_prompt_text("/ch")
            await pilot.pause()
            popup = app.query_one("#slash_popup", SlashCommandPopup)
            self.assertEqual(popup.styles.display, "block")
            rendered = popup.render().plain
            self.assertIn("/chat", rendered)
            self.assertNotIn(
                "Slash commands are unavailable while a task is in progress.", rendered
            )

    async def test_busy_tab_does_not_autocomplete_slash_command(self) -> None:
        app = AgentCliApp(runtime=SlashPopupRuntime())

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_busy(True)
            app._set_prompt_text("/ch")
            await pilot.press("tab")
            await pilot.pause()
            self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "/ch")
            popup = app.query_one("#slash_popup", SlashCommandPopup)
            self.assertEqual(popup.styles.display, "block")
            self.assertIn("/chat", popup.render().plain)

    async def test_busy_enter_does_not_autocomplete_or_submit_slash_command(self) -> None:
        app = AgentCliApp(runtime=SlashPopupRuntime())

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_busy(True)
            app._set_prompt_text("/ch")
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(app.prompt_count, 0)
            self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "/ch")
            popup = app.query_one("#slash_popup", SlashCommandPopup)
            self.assertEqual(popup.styles.display, "block")
            self.assertIn("/chat", popup.render().plain)

    async def test_busy_tab_can_autocomplete_slash_when_policy_allows_command(self) -> None:
        app = AgentCliApp(runtime=SlashPopupRuntime())

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_busy(True)
            app._set_prompt_text("/he")
            await pilot.press("tab")
            await pilot.pause()
            self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "/help ")

    async def test_busy_enter_submits_slash_when_policy_allows_command(self) -> None:
        app = AgentCliApp(runtime=SlashPopupRuntime())
        enqueued: list[str] = []

        async def _enqueue(text: str, attachments: list[PromptAttachment]) -> None:
            del attachments
            enqueued.append(text)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._enqueue_runtime_request = _enqueue  # type: ignore[method-assign]
            app._set_busy(True)
            app._set_prompt_text("/he")
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(enqueued, ["/help"])
            self.assertEqual(app.prompt_count, 1)

    async def test_busy_slash_single_available_command_supports_tab_then_enter_submit(self) -> None:
        app = AgentCliApp(runtime=SlashPopupRuntime())
        enqueued: list[str] = []

        async def _enqueue(text: str, attachments: list[PromptAttachment]) -> None:
            del attachments
            enqueued.append(text)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._enqueue_runtime_request = _enqueue  # type: ignore[method-assign]
            app._set_busy(True)
            app._set_prompt_text("/hel")

            await pilot.press("tab")
            await pilot.pause()
            self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "/help ")

            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(enqueued, ["/help"])
            self.assertEqual(app.prompt_count, 1)

    async def test_busy_popup_still_shows_disabled_reason_for_unavailable_commands(self) -> None:
        app = AgentCliApp(runtime=SlashPopupRuntime())

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_busy(True)
            app._set_prompt_text("/")
            await pilot.pause()

            popup = app.query_one("#slash_popup", SlashCommandPopup)
            rendered = popup.render().plain
            self.assertIn("/help", rendered)
            self.assertIn("/chat", rendered)
            self.assertIn("Slash commands are unavailable while a task is in progress.", rendered)

    async def test_at_file_popup_shows_workspace_matches(self) -> None:
        app = AgentCliApp()
        app._workspace_files_cache = ["app.py", "README.md", "tests/test_app_ui_smoke.py"]

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("@ap")
            await pilot.pause()
            popup = app.query_one("#slash_popup", SlashCommandPopup)
            self.assertEqual(popup.styles.display, "block")
            self.assertIn("app.py", popup.render().plain)
            self.assertNotIn("/help", popup.render().plain)

    async def test_empty_at_shows_workspace_file_candidates(self) -> None:
        app = AgentCliApp()
        app._workspace_files_cache = ["app.py", "README.md", "tests/test_app_ui_smoke.py"]

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("@")
            await pilot.pause()
            popup = app.query_one("#slash_popup", SlashCommandPopup)
            self.assertEqual(popup.styles.display, "block")
            rendered = popup.render().plain
            self.assertIn("app.py", rendered)
            self.assertIn("README.md", rendered)

    async def test_tab_autocompletes_file_reference(self) -> None:
        app = AgentCliApp()
        app._workspace_files_cache = ["app.py", "README.md"]

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("@ap")
            await pilot.press("tab")
            await pilot.pause()
            self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "@app.py ")
            self.assertEqual(
                app.query_one("#slash_popup", SlashCommandPopup).styles.display, "none"
            )

    async def test_arrow_keys_select_file_candidate_and_enter_inserts_reference(self) -> None:
        runtime = RecordingRuntime()
        app = AgentCliApp(runtime=runtime)
        app._workspace_files_cache = ["app.py", "apply_patch_notes.md", "README.md"]

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("@ap")
            await pilot.pause()
            popup = app.query_one("#slash_popup", SlashCommandPopup)
            self.assertIn("app.py", popup.render().plain)
            self.assertIn("apply_patch_notes.md", popup.render().plain)
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(
                app.query_one("#prompt_composer", PromptComposer).text, "@apply_patch_notes.md "
            )
            self.assertIsNone(runtime.last_prompt)

    async def test_file_reference_selection_replaces_only_active_token_in_sentence(self) -> None:
        app = AgentCliApp()
        app._workspace_files_cache = ["app.py", "README.md"]

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("read @ap please")
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer._cursor_pos = len("read @ap")
            composer.refresh(repaint=True, layout=False)
            app.on_prompt_composer_changed()
            await pilot.pause()
            await pilot.press("tab")
            await pilot.pause()
            self.assertEqual(
                app.query_one("#prompt_composer", PromptComposer).text, "read @app.py please"
            )

    async def test_escape_dismisses_file_popup(self) -> None:
        app = AgentCliApp()
        app._workspace_files_cache = ["app.py", "README.md"]

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("@ap")
            await pilot.pause()
            popup = app.query_one("#slash_popup", SlashCommandPopup)
            self.assertEqual(popup.styles.display, "block")
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(popup.styles.display, "none")
            self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "@ap")

    async def test_tab_autocompletes_help_command(self) -> None:
        app = AgentCliApp(runtime=SlashPopupRuntime())

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("/he")
            await pilot.press("tab")
            await pilot.pause()
            self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "/help ")

    async def test_local_presentation_commands_appear_in_slash_popup(self) -> None:
        app = AgentCliApp(runtime=RecordingRuntime())
        expected_theme_usage = f"/theme <{'|'.join(builtin_theme_ids())}>"

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("/th")
            await pilot.pause()
            popup = app.query_one("#slash_popup", SlashCommandPopup)
            self.assertEqual(popup.styles.display, "block")
            self.assertIn(expected_theme_usage, popup.render().plain)

            app._set_prompt_text("/la")
            await pilot.pause()
            self.assertIn("/lang <en|zh-CN|ja|fr|auto>", popup.render().plain)

    async def test_slash_argument_popup_shows_lang_candidates(self) -> None:
        app = AgentCliApp(runtime=ParameterPopupRuntime())

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("/lang ")
            await pilot.pause()
            popup = app.query_one("#slash_popup", SlashCommandPopup)
            rendered = popup.render().plain

        self.assertEqual(popup.styles.display, "block")
        self.assertIn("en", rendered)
        self.assertIn("zh-CN", rendered)
        self.assertIn("auto", rendered)

    async def test_tab_autocompletes_selected_lang_argument(self) -> None:
        app = AgentCliApp(runtime=ParameterPopupRuntime())

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("/lang zh")
            await pilot.pause()
            await pilot.press("tab")
            await pilot.pause()
            self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "/lang zh-CN ")

    async def test_single_argument_selection_hides_popup_and_next_enter_submits(self) -> None:
        runtime = ParameterPopupRuntime()
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("/provider ant")
            await pilot.pause()
            popup = app.query_one("#slash_popup", SlashCommandPopup)
            self.assertEqual(popup.styles.display, "block")
            self.assertIn("anthropic", popup.render().plain)

            await pilot.press("tab")
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            popup = app.query_one("#slash_popup", SlashCommandPopup)
            self.assertEqual(composer.text, "/provider anthropic ")
            self.assertEqual(popup.styles.display, "none")

            await pilot.press("enter")
            await pilot.pause()
            self.assertEqual(runtime.last_prompt, "/provider anthropic")
            self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "")

    async def test_model_reasoning_effort_popup_shows_level_candidates(self) -> None:
        app = AgentCliApp(runtime=ParameterPopupRuntime())

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("/model --reasoning-effort ")
            await pilot.pause()
            popup = app.query_one("#slash_popup", SlashCommandPopup)
            rendered = popup.render().plain

        self.assertEqual(popup.styles.display, "block")
        self.assertIn("low", rendered)
        self.assertIn("medium", rendered)
        self.assertIn("xhigh", rendered)

    async def test_provider_popup_enter_submits_selected_provider_action(self) -> None:
        runtime = ParameterPopupRuntime()
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("/provider ant")
            await pilot.pause()
            popup = app.query_one("#slash_popup", SlashCommandPopup)
            self.assertEqual(popup.styles.display, "block")
            self.assertIn("anthropic", popup.render().plain)

            await pilot.press("enter")
            await pilot.pause()

            self.assertEqual(runtime.last_prompt, "/provider anthropic")
            self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "")

    async def test_model_popup_enter_submits_selected_model_action(self) -> None:
        runtime = ParameterPopupRuntime()
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("/model gpt_53")
            await pilot.pause()
            popup = app.query_one("#slash_popup", SlashCommandPopup)
            self.assertEqual(popup.styles.display, "block")
            self.assertIn("gpt_53_reference", popup.render().plain)

            await pilot.press("enter")
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            popup = app.query_one("#slash_popup", SlashCommandPopup)
            self.assertEqual(composer.text, "/model gpt_53_reference ")
            self.assertEqual(popup.styles.display, "block")
            rendered = popup.render().plain
            self.assertIn("low", rendered)
            self.assertIn("medium", rendered)
            self.assertIn("high", rendered)
            self.assertNotIn("reasoning-effort", rendered)
            self.assertNotIn("write", rendered)

            await pilot.press("enter")
            await pilot.pause()

            self.assertEqual(runtime.last_prompt, "/model gpt_53_reference medium")
            self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "")

    async def test_model_popup_shows_availability_before_selection(self) -> None:
        app = AgentCliApp(runtime=ParameterPopupRuntime())

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("/model ")
            await pilot.pause()
            popup = app.query_one("#slash_popup", SlashCommandPopup)
            rendered = popup.render().plain

        self.assertEqual(popup.styles.display, "block")
        self.assertIn("availability: available, avg 180ms", rendered)
        self.assertIn("availability: unavailable, timeout", rendered)
        self.assertNotIn("reasoning-effort", rendered)
        self.assertNotIn("write", rendered)

    async def test_selection_popups_default_to_current_values(self) -> None:
        app = AgentCliApp(
            runtime=ParameterPopupRuntime(),
            language="zh-CN",
            theme_id="harbor_mist",
        )

        async with app.run_test() as pilot:
            await pilot.pause()
            cases = [
                ("/provider ", "openai"),
                ("/model ", "gpt_54"),
                ("/model --reasoning-effort ", "high"),
                ("/lang ", "zh-CN"),
                ("/theme ", "harbor_mist"),
            ]
            for prompt, expected_usage in cases:
                app._set_prompt_text(prompt)
                await pilot.pause()
                popup = app.query_one("#slash_popup", SlashCommandPopup)
                self.assertEqual(popup.styles.display, "block")
                selected = popup._items[popup._selected_index]
                self.assertEqual(selected.get("usage"), expected_usage)

    async def test_submit_lang_command_switches_locale_without_runtime(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace"
            root.mkdir(parents=True, exist_ok=True)
            home = Path(tmpdir) / "home"
            legacy = Path(tmpdir) / "legacy"
            runtime = RecordingRuntime()
            runtime.cwd = root

            with (
                patch("cli.agent_cli.ui.presentation.AGENT_CLI_HOME", home),
                patch("cli.agent_cli.ui.presentation.LEGACY_COMPAT_HOME", legacy),
            ):
                app = AgentCliApp(runtime=runtime, language=None, theme_id=None)

                async with app.run_test() as pilot:
                    await pilot.pause()
                    app._set_prompt_text("/lang zh-CN")
                    await pilot.press("enter")
                    await pilot.pause()

                    composer = app.query_one("#prompt_composer", PromptComposer)
                    footer = app.query_one("#composer_footer", Static)
                    main_log = app.query_one("#main_log")
                    saved_config = tomllib.loads((home / "config.toml").read_text(encoding="utf-8"))

                    self.assertIsNone(runtime.last_prompt)
                    self.assertEqual(app._presentation.locale, "zh-CN")
                    self.assertEqual(saved_config["cli"]["lang"], "zh-CN")
                    self.assertIn(
                        "让 AgentHub 处理任何事情",
                        composer.build_render_text(80, focused=False).plain,
                    )
                    self.assertIn("剩余上下文", self._static_plain(footer))
                    self.assertNotIn("查看快捷键", self._status_line_plain(app))
                    self.assertIn("保存到", main_log.text)
                    self.assertIn(str(home / "config.toml"), main_log.text)

    async def test_submit_theme_command_switches_theme_without_runtime(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace"
            root.mkdir(parents=True, exist_ok=True)
            home = Path(tmpdir) / "home"
            legacy = Path(tmpdir) / "legacy"
            runtime = RecordingRuntime()
            runtime.cwd = root

            with (
                patch("cli.agent_cli.ui.presentation.AGENT_CLI_HOME", home),
                patch("cli.agent_cli.ui.presentation.LEGACY_COMPAT_HOME", legacy),
            ):
                app = AgentCliApp(runtime=runtime, language="en", theme_id=None)

                async with app.run_test() as pilot:
                    await pilot.pause()
                    app._set_prompt_text("/theme harbor_mist")
                    await pilot.press("enter")
                    await pilot.pause()

                    footer = app.query_one("#composer_footer", Static)
                    status_line = app.query_one("#status_line", Static)
                    top_title_row = app.query_one("#top_title_row")
                    tab_bar = app.query_one("#tab_bar")
                    main_log = app.query_one("#main_log")
                    saved_config = tomllib.loads((home / "config.toml").read_text(encoding="utf-8"))
                    scrollbar = scrollbar_palette(app._theme)

                    self.assertIsNone(runtime.last_prompt)
                    self.assertEqual(app._presentation.theme_id, "harbor_mist")
                    self.assertEqual(saved_config["cli"]["theme"]["id"], "harbor_mist")
                    self.assertEqual(
                        footer.styles.background, Color.parse(app._theme.info_surface_bg)
                    )
                    self.assertEqual(
                        status_line.styles.background, Color.parse(app._theme.info_surface_bg)
                    )
                    self.assertEqual(
                        top_title_row.styles.background, Color.parse(app._theme.info_surface_bg)
                    )
                    self.assertEqual(
                        tab_bar.styles.background, Color.parse(app._theme.info_surface_bg)
                    )
                    self.assertEqual(
                        main_log.styles.scrollbar_background, Color.parse(scrollbar["track"])
                    )
                    self.assertEqual(
                        main_log.styles.scrollbar_color, Color.parse(scrollbar["thumb"])
                    )
                    self.assertEqual(
                        main_log.styles.scrollbar_color_hover, Color.parse(scrollbar["thumb_hover"])
                    )
                    self.assertEqual(
                        main_log.styles.scrollbar_color_active,
                        Color.parse(scrollbar["thumb_active"]),
                    )
                    self.assertIn("Saved to", main_log.text)
                    self.assertIn(str(home / "config.toml"), main_log.text)

    async def test_submit_theme_command_persists_user_preference_but_project_override_stays_active(
        self,
    ) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "workspace"
            project_config_dir = root / ".config"
            project_config_dir.mkdir(parents=True, exist_ok=True)
            project_config_path = project_config_dir / "config.toml"
            project_config_path.write_text('[cli.theme]\nid = "light"\n', encoding="utf-8")
            home = Path(tmpdir) / "home"
            legacy = Path(tmpdir) / "legacy"
            runtime = RecordingRuntime()
            runtime.cwd = root

            with (
                patch("cli.agent_cli.ui.presentation.AGENT_CLI_HOME", home),
                patch("cli.agent_cli.ui.presentation.LEGACY_COMPAT_HOME", legacy),
            ):
                app = AgentCliApp(runtime=runtime, language="en", theme_id=None)

                async with app.run_test() as pilot:
                    await pilot.pause()
                    app._set_prompt_text("/theme harbor_mist")
                    await pilot.press("enter")
                    await pilot.pause()

                    main_log = app.query_one("#main_log")
                    saved_config = tomllib.loads((home / "config.toml").read_text(encoding="utf-8"))

                    self.assertEqual(saved_config["cli"]["theme"]["id"], "harbor_mist")
                    self.assertEqual(app._presentation.theme_id, "light")
                    self.assertIn("overridden by", main_log.text)
                    self.assertIn(str(project_config_path), main_log.text)

    async def test_escape_dismisses_slash_popup(self) -> None:
        app = AgentCliApp(runtime=SlashPopupRuntime())

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("/he")
            await pilot.pause()
            popup = app.query_one("#slash_popup", SlashCommandPopup)
            self.assertEqual(popup.styles.display, "block")
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(popup.styles.display, "none")
            self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "/he")

    async def test_slash_space_does_not_open_popup(self) -> None:
        app = AgentCliApp(runtime=SlashPopupRuntime())

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("/ test")
            await pilot.pause()
            popup = app.query_one("#slash_popup", SlashCommandPopup)
            self.assertEqual(popup.styles.display, "none")

    async def test_arrow_keys_select_slash_candidate_and_enter_executes(self) -> None:
        runtime = SlashPopupRuntime()
        app = AgentCliApp(runtime=runtime)
        submitted: list[str] = []
        submit_scheduled = asyncio.Event()

        async def record_submit() -> None:
            submitted.append(app._current_prompt_text())
            app._clear_prompt_text()
            app._refresh_prompt_composer()
            submit_scheduled.set()

        app.action_submit_prompt = record_submit  # type: ignore[method-assign]

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("/p")
            await pilot.pause()
            popup = app.query_one("#slash_popup", SlashCommandPopup)
            self.assertIn("/providers", popup.render().plain)
            self.assertIn("/provider [name]", popup.render().plain)
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("enter")
            await asyncio.wait_for(submit_scheduled.wait(), timeout=1.0)
            await pilot.pause()
            self.assertEqual(submitted, ["/provider"])
            self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "")

    async def test_slash_popup_scrolls_to_keep_selected_item_visible(self) -> None:
        app = AgentCliApp(runtime=SlashPopupRuntime())

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("/")
            await pilot.pause()
            popup = app.query_one("#slash_popup", SlashCommandPopup)
            initial_plain = popup.render().plain
            self.assertIn("/help", initial_plain)
            for _ in range(7):
                await pilot.press("down")
                await pilot.pause()
            scrolled_plain = popup.render().plain
            self.assertNotEqual(initial_plain, scrolled_plain)
            self.assertNotIn("/help", scrolled_plain)

    async def test_composer_stays_single_line_until_wrap(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.resize_terminal(120, 30)
            await pilot.pause()
            app._set_prompt_text("short line")
            app._refresh_prompt_composer()
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer_shell = app.query_one("#composer_shell")
            bottom_dock = app.query_one("#bottom_dock")
            self.assertEqual(int(composer.styles.height.value), 1)
            self.assertEqual(int(composer_shell.styles.height.value), 3)
            self.assertEqual(int(bottom_dock.styles.height.value), 5)

    async def test_composer_expands_when_line_wraps(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.resize_terminal(24, 20)
            await pilot.pause()
            app._set_prompt_text("abcdefghijklmnopqrstuvwxyz")
            app._refresh_prompt_composer()
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer_shell = app.query_one("#composer_shell")
            bottom_dock = app.query_one("#bottom_dock")
            self.assertGreaterEqual(int(composer.styles.height.value), 2)
            self.assertGreaterEqual(int(composer_shell.styles.height.value), 4)
            self.assertGreaterEqual(int(bottom_dock.styles.height.value), 6)
            self.assertIn("\n", composer.render().plain)

    async def test_submit_runs_in_background_and_composer_stays_editable(self) -> None:
        runtime = BlockingQueueRuntime()
        release_first = runtime.block_prompt("first job")
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("first job")
            await app.action_submit_prompt()
            await runtime.wait_started("first job")
            await pilot.pause()

            self.assertTrue(app._busy)
            self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "")

            app._set_prompt_text("draft while busy")
            await pilot.pause()
            self.assertEqual(
                app.query_one("#prompt_composer", PromptComposer).text, "draft while busy"
            )

            release_first.set()
            await app._wait_for_runtime_idle()
            await pilot.pause()

            transcript = app.query_one("#main_log", TranscriptArea).text
            self.assertIn("› first job", transcript)
            self.assertIn("• processed first job", transcript)
            self.assertEqual(
                app.query_one("#prompt_composer", PromptComposer).text, "draft while busy"
            )

    async def test_submit_queues_follow_up_prompt_while_first_run_is_busy(self) -> None:
        runtime = BlockingQueueRuntime()
        release_first = runtime.block_prompt("first job")
        release_second = runtime.block_prompt("second job")
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("first job")
            await app.action_submit_prompt()
            await runtime.wait_started("first job")
            await pilot.pause()

            app._set_prompt_text("second job")
            await app.action_submit_prompt()
            await pilot.pause()

            self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "")
            self.assertEqual(runtime.calls, ["first job"])

            release_first.set()
            await runtime.wait_started("second job")
            await pilot.pause()
            self.assertEqual(runtime.calls, ["first job", "second job"])

            release_second.set()
            await app._wait_for_runtime_idle()
            await pilot.pause()

            transcript = app.query_one("#main_log", TranscriptArea).text
            self.assertIn("› first job", transcript)
            self.assertIn("› second job", transcript)
            self.assertIn("• processed first job", transcript)
            self.assertIn("• processed second job", transcript)
            first_user_idx = transcript.index("› first job")
            first_reply_idx = transcript.index("• processed first job")
            second_user_idx = transcript.index("› second job")
            second_reply_idx = transcript.index("• processed second job")
            self.assertLess(first_user_idx, first_reply_idx)
            self.assertLess(first_reply_idx, second_user_idx)
            self.assertLess(second_user_idx, second_reply_idx)
            self.assertFalse(app._busy)

    async def test_busy_tab_queues_follow_up_prompt_while_first_run_is_busy(self) -> None:
        runtime = BlockingQueueRuntime()
        release_first = runtime.block_prompt("first job")
        release_second = runtime.block_prompt("second job")
        app = AgentCliApp(runtime=runtime)

        try:
            async with app.run_test() as pilot:
                await pilot.pause()
                app._set_prompt_text("first job")
                await app.action_submit_prompt()
                await runtime.wait_started("first job")
                await pilot.pause()

                app._set_prompt_text("second job")
                await pilot.pause()
                await pilot.press("tab")
                await pilot.pause()

                self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "")
                self.assertEqual(runtime.calls, ["first job"])

                release_first.set()
                await runtime.wait_started("second job")
                await pilot.pause()
                self.assertEqual(runtime.calls, ["first job", "second job"])

                release_second.set()
                await app._wait_for_runtime_idle()
                await pilot.pause()

                transcript = app.query_one("#main_log", TranscriptArea).text
                self.assertIn("› first job", transcript)
                self.assertIn("› second job", transcript)
                self.assertIn("• processed first job", transcript)
                self.assertIn("• processed second job", transcript)
                first_user_idx = transcript.index("› first job")
                first_reply_idx = transcript.index("• processed first job")
                second_user_idx = transcript.index("› second job")
                second_reply_idx = transcript.index("• processed second job")
                self.assertLess(first_user_idx, first_reply_idx)
                self.assertLess(first_reply_idx, second_user_idx)
                self.assertLess(second_user_idx, second_reply_idx)
        finally:
            release_first.set()
            release_second.set()

    async def test_transcript_selection_can_be_copied_to_clipboard(self) -> None:
        app = AgentCliApp()
        copied: list[str] = []
        app.copy_to_clipboard = lambda text: copied.append(text)

        async with app.run_test():
            main_log = app.query_one("#main_log", TranscriptArea)
            main_log.load_text("assistant\n  hello world")
            main_log.selection = ((1, 2), (1, 7))

            self.assertTrue(main_log.copy_selection_to_clipboard())
            self.assertEqual(copied, ["hello"])

    async def test_assistant_markdown_normalizes_hidden_prefix_and_orphan_list_marker(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app._write_assistant_reply(
                "\u200b\n如果你说的是刚问的这些地方。\n-\n按气象学：连续5天达标才算入夏。"
            )
            await pilot.pause()
            transcript = app.query_one("#main_log", TranscriptArea).text

        self.assertNotIn("• \u200b", transcript)
        self.assertNotIn("\n  -\n  按气象学", transcript)
        self.assertIn("• 如果你说的是刚问的这些地方。", transcript)
        self.assertIn("  - 按气象学：连续5天达标才算入夏。", transcript)

    async def test_assistant_markdown_heavy_summary_hides_raw_heading_rules(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app._write_assistant_reply(
                "以下是 AgentHub 项目的能力概览：\n\n"
                "---\n\n"
                "## 执行模式\n\n"
                "- TUI：终端交互界面\n"
                "- Headless 模式：无交互执行\n\n"
                "---\n\n"
                "## LLM Provider 支持\n\n"
                "- OpenAI\n"
                "- Anthropic"
            )
            await pilot.pause()
            transcript = app.query_one("#main_log", TranscriptArea).text

        self.assertNotIn("##", transcript)
        self.assertNotIn("---", transcript)
        self.assertNotIn("———", transcript)
        self.assertIn("执行模式：", transcript)
        self.assertIn("LLM Provider 支持：", transcript)
        self.assertIn("  - TUI：终端交互界面", transcript)

    async def test_transcript_left_mouse_up_copies_selection_to_clipboard(self) -> None:
        app = AgentCliApp()
        copied: list[str] = []
        app.copy_to_clipboard = lambda text: copied.append(text)

        async with app.run_test():
            main_log = app.query_one("#main_log", TranscriptArea)
            main_log.load_text("> 你好\n  你好！有什么我可以帮你的吗？")
            main_log.selection = ((1, 2), (1, 8))

            main_log.on_mouse_up(SimpleNamespace(button=1))

            self.assertEqual(copied, ["你好！有什么"])

    async def test_transcript_mouse_drag_creates_selection_and_copies(self) -> None:
        app = AgentCliApp()
        copied: list[str] = []
        app.copy_to_clipboard = lambda text: copied.append(text)

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            main_log = app.query_one("#main_log", TranscriptArea)
            main_log.load_text("alpha beta gamma")

            main_log.on_mouse_down(
                SimpleNamespace(button=1, x=0, y=0, stop=lambda: None, prevent_default=lambda: None)
            )
            main_log.on_mouse_move(
                SimpleNamespace(x=6, y=0, stop=lambda: None, prevent_default=lambda: None)
            )
            main_log.on_mouse_up(
                SimpleNamespace(button=1, stop=lambda: None, prevent_default=lambda: None)
            )
            await pilot.pause()

            self.assertEqual(main_log.selected_text, "alpha")
            self.assertEqual(copied, ["alpha"])
            self.assertIs(app.focused, composer)

    async def test_transcript_double_click_selects_word(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            main_log = app.query_one("#main_log", TranscriptArea)
            main_log.load_text("alpha beta gamma")

            event = SimpleNamespace(
                button=1, x=7, y=0, stop=lambda: None, prevent_default=lambda: None
            )
            main_log.on_mouse_down(event)
            main_log.on_mouse_down(event)
            await pilot.pause()

            self.assertEqual(main_log.selected_text, "beta")

    async def test_transcript_triple_click_selects_logical_line(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            main_log = app.query_one("#main_log", TranscriptArea)
            main_log.load_text("alpha\nbeta\ngamma")

            event = SimpleNamespace(
                button=1, x=1, y=1, stop=lambda: None, prevent_default=lambda: None
            )
            main_log.on_mouse_down(event)
            main_log.on_mouse_down(event)
            main_log.on_mouse_down(event)
            await pilot.pause()

            self.assertEqual(main_log.selected_text, "beta")

    async def test_transcript_mouse_copy_keeps_focus_on_prompt_composer(self) -> None:
        app = AgentCliApp()
        copied: list[str] = []
        app.copy_to_clipboard = lambda text: copied.append(text)

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            main_log = app.query_one("#main_log", TranscriptArea)
            main_log.load_text("> 你好\n  你好！有什么我可以帮你的吗？")
            main_log.selection = ((1, 2), (1, 8))

            main_log.on_mouse_up(SimpleNamespace(button=1))
            await pilot.pause()

            self.assertEqual(copied, ["你好！有什么"])
            self.assertIs(app.focused, composer)

    async def test_transcript_right_click_copy_suppresses_following_native_paste_event(
        self,
    ) -> None:
        app = AgentCliApp()
        copied: list[str] = []
        app.copy_to_clipboard = lambda text: copied.append(text)

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("draft")
            main_log = app.query_one("#main_log", TranscriptArea)
            main_log.load_text("> hello\n• world")
            main_log.selection = ((1, 2), (1, 7))

            right_click = self._MouseEventSpy(button=3, widget=main_log)
            main_log.on_mouse_down(right_click)
            composer.on_paste(Paste("world"))
            await pilot.pause()

            self.assertEqual(copied, ["world"])
            self.assertEqual(composer.text, "draft")
            self.assertEqual(main_log.selected_text, "")
            self.assertTrue(main_log.selection.is_empty)
            self.assertTrue(right_click.stopped)
            self.assertTrue(right_click.prevented)

    async def test_transcript_right_click_copy_clears_selection_without_pasting(self) -> None:
        app = AgentCliApp()
        copied: list[str] = []
        app.copy_to_clipboard = lambda text: copied.append(text)

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("draft")
            main_log = app.query_one("#main_log", TranscriptArea)
            main_log.load_text("> hello\n• world")
            main_log.selection = ((1, 2), (1, 7))

            right_click = self._MouseEventSpy(button=3)
            main_log.on_mouse_down(right_click)
            await pilot.pause()

            self.assertEqual(copied, ["world"])
            self.assertEqual(main_log.selected_text, "")
            self.assertTrue(main_log.selection.is_empty)
            self.assertEqual(composer.text, "draft")
            self.assertTrue(right_click.stopped)
            self.assertTrue(right_click.prevented)

    async def test_global_right_click_copies_transcript_selection_anywhere(self) -> None:
        app = AgentCliApp()
        copied: list[str] = []
        app.copy_to_clipboard = lambda text: copied.append(text)
        app._read_clipboard_text = lambda: (_ for _ in ()).throw(
            AssertionError("clipboard read should not happen while a selection exists")
        )

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("draft")
            main_log = app.query_one("#main_log", TranscriptArea)
            main_log.load_text("> hello\n• world")
            main_log.selection = ((1, 2), (1, 7))
            event = self._MouseEventSpy(button=3, widget=composer)

            app.on_mouse_down(event)
            await pilot.pause()

            self.assertEqual(copied, ["world"])
            self.assertEqual(main_log.selected_text, "")
            self.assertTrue(main_log.selection.is_empty)
            self.assertEqual(composer.text, "draft")
            self.assertTrue(event.stopped)
            self.assertTrue(event.prevented)

    async def test_transcript_right_click_mouse_down_already_suppresses_native_paste_event(
        self,
    ) -> None:
        app = AgentCliApp()
        copied: list[str] = []
        app.copy_to_clipboard = lambda text: copied.append(text)

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("draft")
            main_log = app.query_one("#main_log", TranscriptArea)
            main_log.load_text("> hello\n• world")
            main_log.selection = ((1, 2), (1, 7))

            right_down = self._MouseEventSpy(button=3)
            main_log.on_mouse_down(right_down)
            composer.on_paste(Paste("old clipboard text"))
            right_up = self._MouseEventSpy(button=3)
            main_log.on_mouse_up(right_up)
            await pilot.pause()

            self.assertEqual(copied, ["world"])
            self.assertEqual(composer.text, "draft")
            self.assertEqual(main_log.selected_text, "")
            self.assertTrue(right_down.stopped)
            self.assertTrue(right_down.prevented)
            self.assertFalse(right_up.stopped)
            self.assertFalse(right_up.prevented)

    async def test_transcript_right_click_mouse_down_copies_without_mouse_up(self) -> None:
        app = AgentCliApp()
        copied: list[str] = []
        app.copy_to_clipboard = lambda text: copied.append(text)

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("draft")
            main_log = app.query_one("#main_log", TranscriptArea)
            main_log.load_text("> hello\n• world")
            main_log.selection = ((1, 2), (1, 7))

            right_click = self._MouseEventSpy(button=3, x=3, y=1)
            main_log.on_mouse_down(right_click)
            await pilot.pause()

            self.assertEqual(copied, ["world"])
            self.assertEqual(main_log.selected_text, "")
            self.assertEqual(composer.text, "draft")
            self.assertTrue(right_click.stopped)
            self.assertTrue(right_click.prevented)

    async def test_global_right_click_pastes_after_transcript_selection_copy(self) -> None:
        app = AgentCliApp()
        copied: list[str] = []
        app.copy_to_clipboard = lambda text: copied.append(text)
        app._read_clipboard_text = lambda: "world"

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            main_log = app.query_one("#main_log", TranscriptArea)
            main_log.load_text("> hello\n• world")
            main_log.selection = ((1, 2), (1, 7))
            copy_event = self._MouseEventSpy(button=3, widget=main_log)
            paste_event = self._MouseEventSpy(button=3, widget=main_log)

            main_log.on_mouse_down(copy_event)
            app.on_mouse_down(paste_event)
            await pilot.pause()

            self.assertEqual(copied, ["world"])
            self.assertEqual(composer.text, "world")
            self.assertIs(app.focused, composer)
            self.assertTrue(copy_event.stopped)
            self.assertTrue(copy_event.prevented)
            self.assertTrue(paste_event.stopped)
            self.assertTrue(paste_event.prevented)

    async def test_global_right_click_paste_suppresses_stale_native_paste_event(
        self,
    ) -> None:
        app = AgentCliApp()
        copied: list[str] = []
        app.copy_to_clipboard = lambda text: copied.append(text)
        app._read_clipboard_text = lambda: "world"

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            main_log = app.query_one("#main_log", TranscriptArea)
            main_log.load_text("> hello\n• world")
            main_log.selection = ((1, 2), (1, 7))
            copy_event = self._MouseEventSpy(button=3, widget=main_log)
            paste_event = self._MouseEventSpy(button=3, widget=main_log)

            main_log.on_mouse_down(copy_event)
            app.on_mouse_down(paste_event)
            composer.on_paste(Paste("old clipboard text"))
            await pilot.pause()

            self.assertEqual(copied, ["world"])
            self.assertEqual(composer.text, "world")
            self.assertTrue(copy_event.stopped)
            self.assertTrue(copy_event.prevented)
            self.assertTrue(paste_event.stopped)
            self.assertTrue(paste_event.prevented)

    async def test_transcript_right_click_copy_suppresses_following_printable_paste_burst(
        self,
    ) -> None:
        app = AgentCliApp()
        copied: list[str] = []
        app.copy_to_clipboard = lambda text: copied.append(text)

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("draft")
            main_log = app.query_one("#main_log", TranscriptArea)
            main_log.load_text("> 你好\n• 你好")
            main_log.selection = ((1, 2), (1, 4))

            main_log.on_mouse_down(
                SimpleNamespace(button=3, stop=lambda: None, prevent_default=lambda: None)
            )
            composer.on_key(self._fake_printable_key("你"))
            composer.on_key(self._fake_printable_key("好"))
            await pilot.pause()
            composer.flush_paste_burst()
            await pilot.pause()

            self.assertEqual(copied, ["你好"])
            self.assertEqual(composer.text, "draft")

    async def test_prompt_transcript_keeps_viewport_when_user_scrolled_up(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.resize_terminal(72, 18)
            await pilot.pause()
            for index in range(24):
                app._write_user_prompt(f"prompt {index}")
                app._write_assistant_reply(f"assistant reply {index} " + ("detail " * 8))
            await pilot.pause()

            main_log = app.query_one("#main_log", TranscriptArea)
            self.assertGreater(int(main_log.max_scroll_y), 0)

            main_log.scroll_to(y=0, animate=False, immediate=True, force=True)
            await pilot.pause()
            self.assertEqual(int(main_log.scroll_y), 0)

            app._write_user_prompt("latest prompt")
            app._write_assistant_reply("latest answer")
            await pilot.pause()

            self.assertEqual(int(main_log.scroll_y), 0)

    async def test_prompt_transcript_still_follows_bottom_when_pinned(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.resize_terminal(72, 18)
            await pilot.pause()
            for index in range(24):
                app._write_user_prompt(f"prompt {index}")
                app._write_assistant_reply(f"assistant reply {index} " + ("detail " * 8))
            await pilot.pause()

            main_log = app.query_one("#main_log", TranscriptArea)
            self.assertGreater(int(main_log.max_scroll_y), 0)

            main_log.scroll_end(animate=False, immediate=True, force=True, x_axis=False)
            await pilot.pause()
            self.assertGreaterEqual(int(main_log.scroll_y), max(0, int(main_log.max_scroll_y) - 1))

            app._write_user_prompt("latest prompt")
            app._write_assistant_reply("latest answer")
            await pilot.pause()

            self.assertGreaterEqual(int(main_log.scroll_y), max(0, int(main_log.max_scroll_y) - 1))

    async def test_submit_slash_command_forces_transcript_to_latest(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.resize_terminal(72, 18)
            await pilot.pause()
            for index in range(24):
                app._write_user_prompt(f"prompt {index}")
                app._write_assistant_reply(f"assistant reply {index} " + ("detail " * 8))
            await pilot.pause()

            main_log = app.query_one("#main_log", TranscriptArea)
            self.assertGreater(int(main_log.max_scroll_y), 0)

            main_log.scroll_to(y=0, animate=False, immediate=True, force=True)
            await pilot.pause()
            self.assertEqual(int(main_log.scroll_y), 0)

            app._set_prompt_text("/help")
            await app.action_submit_prompt()
            await app._wait_for_runtime_idle()
            await pilot.pause()

            self.assertIn("› /help", main_log.text)
            self.assertGreaterEqual(int(main_log.scroll_y), max(0, int(main_log.max_scroll_y) - 1))

    async def test_composer_left_mouse_up_copies_selection_to_clipboard(self) -> None:
        app = AgentCliApp()
        copied: list[str] = []
        app.copy_to_clipboard = lambda text: copied.append(text)

        async with app.run_test() as pilot:
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.set_text("alpha\nbeta\ngamma")
            composer.build_render_text(20, focused=True)

            event = SimpleNamespace(
                button=1, x=3, y=1, stop=lambda: None, prevent_default=lambda: None
            )
            composer.on_mouse_down(event)
            composer.on_mouse_down(event)
            composer.on_mouse_down(event)
            composer.on_mouse_up(
                SimpleNamespace(button=1, stop=lambda: None, prevent_default=lambda: None)
            )
            await pilot.pause()

            self.assertEqual(copied, ["beta"])
            self.assertIs(app.focused, composer)

    async def test_transcript_copy_skips_empty_selection(self) -> None:
        app = AgentCliApp()
        copied: list[str] = []
        app.copy_to_clipboard = lambda text: copied.append(text)

        async with app.run_test():
            main_log = app.query_one("#main_log", TranscriptArea)
            main_log.load_text("assistant\n  hello world")
            main_log.selection = ((1, 2), (1, 2))

            self.assertFalse(main_log.copy_selection_to_clipboard())
            self.assertEqual(copied, [])

    async def test_transcript_left_mouse_up_skips_empty_selection(self) -> None:
        app = AgentCliApp()
        copied: list[str] = []
        app.copy_to_clipboard = lambda text: copied.append(text)

        async with app.run_test():
            main_log = app.query_one("#main_log", TranscriptArea)
            main_log.load_text("> hello\n  world")
            main_log.selection = ((1, 2), (1, 2))

            main_log.on_mouse_up(SimpleNamespace(button=1))

            self.assertEqual(copied, [])

    def test_shell_only_response_skips_duplicate_assistant_reply(self) -> None:
        response = PromptResponse(
            user_text="/shell python -V",
            assistant_text="shell output summary",
            tool_events=[ToolEvent(name="shell", ok=True, summary="shell rc=0", payload={})],
            handled_as_command=True,
        )

        self.assertFalse(AgentCliApp._should_render_assistant_reply(response))

    def test_approval_request_fallback_skips_duplicate_assistant_reply(self) -> None:
        response = PromptResponse(
            user_text="run echo hello",
            assistant_text=(
                "已提交命令审批：approval_1\n"
                "/approve approval_1\n"
                "/approve approval_1 mode session\n"
                "/reject approval_1\n"
                "echo hello"
            ),
            tool_events=[
                ToolEvent(
                    name="shell_approval_requested",
                    ok=True,
                    summary="shell approval requested approval_1",
                    payload={"approval_id": "approval_1", "command": "echo hello"},
                )
            ],
        )

        self.assertFalse(AgentCliApp._should_render_assistant_reply(response))

    def test_exit_request_skips_internal_assistant_reply(self) -> None:
        response = PromptResponse(
            user_text="/exit",
            assistant_text="exiting session\nthread_id=thread_exit_123",
            tool_events=[
                ToolEvent(
                    name="app_exit_requested",
                    ok=True,
                    summary="exit requested",
                    payload={
                        "thread_id": "thread_exit_123",
                        "resume_command": "agenthub resume thread_exit_123",
                    },
                )
            ],
            handled_as_command=True,
        )

        self.assertFalse(AgentCliApp._should_render_assistant_reply(response))

    def test_render_transcript_entries_keeps_blank_line_between_layer_transitions(self) -> None:
        tool_entry = activity_entry(
            ActivityEvent(title="Running tool", status="running", kind="tool")
        )
        plan_entry = activity_entry(
            ActivityEvent(
                title="Updated Plan",
                status="info",
                kind="plan",
                detail="1. run tool",
            )
        )

        self.assertIsNotNone(tool_entry)
        self.assertIsNotNone(plan_entry)
        self.assertEqual(tool_entry.layer, "tool")
        self.assertEqual(plan_entry.layer, "commentary")

        lines = render_transcript_entries([tool_entry, blank_entry(), plan_entry])

        self.assertEqual(lines, [*tool_entry.lines, "", *plan_entry.lines])

    def test_render_transcript_entries_inserts_blank_line_when_layers_change_without_spacer(
        self,
    ) -> None:
        tool_entry = activity_entry(
            ActivityEvent(title="Running tool", status="running", kind="tool")
        )
        plan_entry = activity_entry(
            ActivityEvent(
                title="Updated Plan",
                status="info",
                kind="plan",
                detail="1. run tool",
            )
        )

        self.assertIsNotNone(tool_entry)
        self.assertIsNotNone(plan_entry)

        lines = render_transcript_entries([tool_entry, plan_entry])

        self.assertEqual(lines, [*tool_entry.lines, "", *plan_entry.lines])

    async def test_activity_feed_uses_reference_like_summary_and_detail_blocks(self) -> None:
        app = AgentCliApp()

        async with app.run_test():
            app._write_activity_event(
                ActivityEvent(
                    title="Updated Plan",
                    status="info",
                    kind="plan",
                    detail="1. select_conversation\n2. read_recent_messages",
                )
            )
            app._write_activity_event(
                ActivityEvent(title="select_conversation", status="running", kind="tool")
            )
            app._write_activity_event(
                ActivityEvent(
                    title="Selected Enterprise WeChat automation validation",
                    status="success",
                    kind="tool",
                    detail="current Enterprise WeChat automation validation",
                )
            )
            app._write_activity_event(
                ActivityEvent(title="python -V", status="running", kind="command")
            )
            app._write_activity_event(
                ActivityEvent(
                    title="Python 3.11.9",
                    status="info",
                    kind="command_output",
                    detail="stdout",
                )
            )
            app._write_activity_event(
                ActivityEvent(
                    title="Ran python -V",
                    status="success",
                    kind="command",
                    detail="exit 0 | 0.12s",
                )
            )

            transcript = app.query_one("#main_log", TranscriptArea).text

        self.assertIn("□ Todo List", transcript)
        self.assertIn("  └ select_conversation", transcript)
        self.assertIn("    read_recent_messages", transcript)
        self.assertIn("▸ Tool activity (3 updates)", transcript)
        self.assertIn("  └ Running select_conversation", transcript)
        self.assertIn("    +2 more", transcript)
        self.assertNotIn("$ Running python -V", transcript)
        self.assertNotIn("Python 3.11.9", transcript)
        self.assertNotIn("$ Ran python -V", transcript)
        self.assertNotIn("exit 0 | 0.12s", transcript)
        self.assertNotIn("$ python -V", transcript)
        self.assertNotIn("ok  ", transcript)
        self.assertNotIn("[stdout]", transcript)

    async def test_completed_command_activity_replaces_running_command_row(self) -> None:
        app = AgentCliApp()

        async with app.run_test():
            app._write_activity_event(
                ActivityEvent(title="python -V", status="running", kind="command")
            )
            app._write_activity_event(
                ActivityEvent(
                    title="Ran python -V",
                    status="success",
                    kind="command",
                    detail="exit 0 | 0.12s",
                )
            )

            transcript = app.query_one("#main_log", TranscriptArea).text

        self.assertNotIn("$ Running python -V", transcript)
        self.assertIn("$ Ran python -V", transcript)
        self.assertNotIn("exit 0 | 0.12s", transcript)

    async def test_activity_feed_prefixes_stderr_output(self) -> None:
        app = AgentCliApp()

        async with app.run_test():
            app._write_activity_event(
                ActivityEvent(
                    title="first line\nsecond line",
                    status="info",
                    kind="command_output",
                    detail="stderr",
                )
            )
            transcript = app.query_one("#main_log", TranscriptArea).text

        self.assertEqual(transcript, "")

    async def test_failed_command_activity_renders_compact_stderr_in_final_block(self) -> None:
        app = AgentCliApp()

        async with app.run_test():
            app._write_activity_event(
                ActivityEvent(
                    title="Command failed: python broken.py",
                    status="error",
                    kind="command",
                    detail="exit 1 | 0.12s\nstderr: first line\nsecond line",
                )
            )
            transcript = app.query_one("#main_log", TranscriptArea).text

        self.assertIn("✗ Command failed: python broken.py", transcript)
        self.assertIn("  └ exit 1 | 0.12s", transcript)
        self.assertIn("    stderr: first line", transcript)
        self.assertIn("    second line", transcript)

    def test_text_utils_short_compacts_with_ellipsis(self) -> None:
        self.assertEqual(short("Morning follow-up", 7), "Morn...")

    def test_text_utils_crop_one_line_removes_newlines_and_truncates(self) -> None:
        self.assertEqual(crop_one_line("alpha\nbeta\ngamma", 12), "alpha bet...")

    def test_text_utils_flag_label_normalizes_booleans(self) -> None:
        self.assertEqual(flag_label("true"), "yes")
        self.assertEqual(flag_label("false"), "no")
        self.assertEqual(flag_label(""), "-")

    def test_text_utils_tool_label_formats_idle_and_underscores(self) -> None:
        self.assertEqual(tool_label("-"), "idle")
        self.assertEqual(tool_label("shell_approval_requested"), "shell approval requested")

    async def test_narrow_resize_shortens_composer_hint(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.resize_terminal(50, 20)
            await pilot.pause()
            footer = self._footer_plain(app)
            self.assertIn("100% context left", footer)
            self.assertNotIn("? for shortcuts", self._status_line_plain(app))

    async def test_overflow_resize_keeps_right_context_and_truncates_left_shortcuts(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            left = f"  {app._t('footer.shortcuts')}"
            right = app._t("footer.context_left")
            content_width = max(1, cell_len(left) + cell_len(right) - 1)

            await pilot.resize_terminal(content_width + 2, 20)
            await pilot.pause()

            footer = self._footer_plain(app)
            self.assertIn(right, footer)
            self.assertNotIn(left, footer)
            self.assertLessEqual(cell_len(footer), content_width)

    async def test_medium_resize_mentions_file_paths_in_composer_hint(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.resize_terminal(72, 20)
            await pilot.pause()
            footer = self._footer_plain(app)
            self.assertIn("100% context left", footer)
            self.assertNotIn("? for shortcuts", self._status_line_plain(app))

    async def test_wide_resize_mentions_web_toggle_in_composer_hint(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.resize_terminal(120, 24)
            await pilot.pause()
            footer = self._footer_plain(app)
            self.assertIn("100% context left", footer)
            self.assertNotIn("? for shortcuts", self._status_line_plain(app))

    async def test_pending_approval_hint_replaces_default_idle_hint(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.resize_terminal(120, 24)
            await pilot.pause()
            app._update_status(
                {
                    "approval_policy": "on-request",
                    "pending_approvals": "1",
                    "latest_pending_approval_id": "approval_7",
                }
            )
            await pilot.pause()
            self.assertEqual(
                self._status_line_plain(app),
                f"• {app._t('status.pending_approval.one', count=1)}",
            )

    async def test_pending_approval_footer_shows_action_commands(self) -> None:
        app = AgentCliApp()

        class _Ticket:
            approval_id = "approval_7"
            summary = "Approve shell command"
            available_decisions = [
                {"type": "accept"},
                {"type": "accept_for_session"},
                {"type": "accept_with_execpolicy_amendment"},
                {"type": "decline"},
                {"type": "cancel"},
            ]

        app.runtime.list_approval_tickets = lambda limit=20, status="pending": [_Ticket()]  # type: ignore[method-assign]

        async with app.run_test() as pilot:
            await pilot.resize_terminal(160, 24)
            await pilot.pause()
            app._update_status(
                {
                    "approval_policy": "on-request",
                    "pending_approvals": "1",
                    "latest_pending_approval_id": "approval_7",
                }
            )
            await pilot.pause()
            footer = self._footer_plain(app)
            self.assertIn("/approve approval_7", footer)
            self.assertIn("/approve approval_7 mode session", footer)

    async def test_pending_approval_hint_shortens_on_narrow_width(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.resize_terminal(50, 20)
            await pilot.pause()
            app._update_status(
                {
                    "approval_policy": "on-request",
                    "pending_approvals": "2",
                    "latest_pending_approval_id": "approval_9",
                }
            )
            await pilot.pause()
            self.assertEqual(
                self._status_line_plain(app),
                f"• {app._t('status.pending_approval.other', count=2)}",
            )

    async def test_operator_surface_hint_shows_returned_and_adopted_child_states(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.resize_terminal(120, 24)
            await pilot.pause()
            app._update_status(
                {
                    "agent_id": "ag_status",
                    "status": "completed",
                    "workflow_state": "completed",
                    "completion_state": "ready_to_adopt",
                    "adopted": "false",
                    "adoption_expectation": "resume_agent_to_continue",
                    "summary": "child returned result",
                }
            )
            await pilot.pause()
            self.assertEqual(self._status_line_plain(app), "")

            app._update_status(
                {
                    "completion_state": "adopted",
                    "adopted": "true",
                    "adoption_expectation": "-",
                    "summary": "child adopted into parent",
                }
            )
            await pilot.pause()
            self.assertEqual(self._status_line_plain(app), "")

    async def test_f7_toggles_latest_expandable_web_item(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            app._write_activity_event(
                ActivityEvent(
                    title="Searched the web",
                    status="success",
                    kind="web",
                    detail=(
                        "count=3\n"
                        "recommended=openai.com, github.com\n"
                        "1. platform.openai.com | high | OpenAI API docs\n"
                        "2. github.com | high | openai-python\n"
                        "3. example.com | low | Mirror"
                    ),
                )
            )
            await pilot.pause()
            transcript = app.query_one("#main_log", TranscriptArea).text
            self.assertIn("... 1 more result", transcript)
            self.assertNotIn("3. Mirror", transcript)

            app.action_toggle_latest_web_item()
            await pilot.pause()
            transcript = app.query_one("#main_log", TranscriptArea).text
            self.assertIn("3. Mirror", transcript)
            self.assertNotIn("... 1 more result", transcript)
            self.assertIs(app.focused, app.query_one("#prompt_composer", PromptComposer))

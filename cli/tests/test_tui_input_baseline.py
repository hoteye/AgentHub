from __future__ import annotations

import asyncio
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from textual import events
from textual.widgets import Static

from cli.agent_cli.app import AgentCliApp, PromptComposer, SlashCommandPopup, TranscriptArea
from cli.agent_cli.models import PromptAttachment, PromptResponse


class _RecordingRuntime:
    class _Agent:
        @staticmethod
        def provider_status() -> dict[str, str]:
            return {
                "provider_name": "test",
                "provider_model": "test-model",
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
            assistant_text=f"processed {text}",
            attachments=list(attachments or []),
            status=self.agent.provider_status(),
            handled_as_command=False,
        )

    def interrupt_active_run(self) -> dict[str, object]:
        return {"ok": False, "interrupted": False}


class _SlashPopupRuntime(_RecordingRuntime):
    def __init__(self) -> None:
        super().__init__()
        self._commands = [
            {"name": "help", "usage": "/help", "description": "show available slash commands"},
            {"name": "chat", "usage": "/chat", "description": "switch to chat tools"},
        ]

    def slash_command_matches(self, query: str) -> list[dict[str, str]]:
        prefix = str(query or "").strip().lower().lstrip("/")
        if not prefix:
            return [dict(item) for item in self._commands]
        return [
            dict(item)
            for item in self._commands
            if str(item.get("name") or "").strip().lower().startswith(prefix)
        ]

    def slash_command_completion(self, query: str) -> str | None:
        matches = self.slash_command_matches(query)
        if len(matches) == 1:
            return f"/{matches[0]['name']} "
        return None


class _BlockingQueueRuntime(_RecordingRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []
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
        return PromptResponse(
            user_text=text,
            assistant_text=f"processed {text}",
            attachments=list(attachments or []),
            status=self.agent.provider_status(),
            handled_as_command=False,
        )


class _InterruptRuntime(_RecordingRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.interrupt_calls = 0

    def interrupt_active_run(self) -> dict[str, object]:
        self.interrupt_calls += 1
        return {"ok": True, "interrupted": True}


class TuiInputBaselineTest(unittest.IsolatedAsyncioTestCase):
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

    async def _post_composer_key(
        self,
        app: AgentCliApp,
        pilot,
        key: str,
        character: str | None = None,
    ) -> None:
        composer = app.query_one("#prompt_composer", PromptComposer)
        composer.post_message(events.Key(key, character))
        await pilot.pause()

    async def test_enter_submits_prompt_end_to_end(self) -> None:
        runtime = _RecordingRuntime()
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("baseline submit")
            await pilot.press("enter")
            await app._wait_for_runtime_idle()
            await pilot.pause()

            composer = app.query_one("#prompt_composer", PromptComposer)
            transcript = app.query_one("#main_log", TranscriptArea).text
            self.assertEqual(runtime.last_prompt, "baseline submit")
            self.assertEqual(composer.text, "")
            self.assertIn("› baseline submit", transcript)
            self.assertIn("• processed baseline submit", transcript)

    async def test_enter_ignores_blank_prompt(self) -> None:
        runtime = _RecordingRuntime()
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("   ")
            await pilot.press("enter")
            await pilot.pause()

            composer = app.query_one("#prompt_composer", PromptComposer)
            transcript = app.query_one("#main_log", TranscriptArea).text
            self.assertEqual(composer.text, "")
            self.assertEqual(app.prompt_count, 0)
            self.assertIsNone(runtime.last_prompt)
            self.assertEqual(transcript.strip(), "")

    async def test_printable_typing_routes_into_composer(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("h", "i")
            app._flush_prompt_composer_burst()
            await pilot.pause()

            composer = app.query_one("#prompt_composer", PromptComposer)
            self.assertEqual(composer.text, "hi")

    async def test_shift_enter_inserts_newline_without_submitting(self) -> None:
        runtime = _RecordingRuntime()
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("line1")
            await self._post_composer_key(app, pilot, "shift+enter")

            composer = app.query_one("#prompt_composer", PromptComposer)
            transcript = app.query_one("#main_log", TranscriptArea).text
            self.assertEqual(composer.text, "line1\n")
            self.assertIsNone(runtime.last_prompt)
            self.assertEqual(transcript.strip(), "")

    async def test_alt_enter_inserts_newline_without_submitting(self) -> None:
        runtime = _RecordingRuntime()
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("line1")
            await self._post_composer_key(app, pilot, "alt+enter")

            composer = app.query_one("#prompt_composer", PromptComposer)
            transcript = app.query_one("#main_log", TranscriptArea).text
            self.assertEqual(composer.text, "line1\n")
            self.assertIsNone(runtime.last_prompt)
            self.assertEqual(transcript.strip(), "")

    async def test_ctrl_j_inserts_newline_without_submitting(self) -> None:
        runtime = _RecordingRuntime()
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("line1")
            await pilot.press("ctrl+j")
            await pilot.pause()

            composer = app.query_one("#prompt_composer", PromptComposer)
            transcript = app.query_one("#main_log", TranscriptArea).text
            self.assertEqual(composer.text, "line1\n")
            self.assertIsNone(runtime.last_prompt)
            self.assertEqual(transcript.strip(), "")

    async def test_escape_then_enter_fallback_inserts_newline_without_submitting(self) -> None:
        runtime = _RecordingRuntime()
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("line1")
            await pilot.pause()

            composer = app.query_one("#prompt_composer", PromptComposer)
            composer.post_message(events.Key("escape", None))
            composer.post_message(events.Key("enter", None))
            await pilot.pause()

            transcript = app.query_one("#main_log", TranscriptArea).text
            self.assertEqual(composer.text, "line1\n")
            self.assertIsNone(runtime.last_prompt)
            self.assertEqual(transcript.strip(), "")

    async def test_ctrl_v_pastes_clipboard_text_into_composer(self) -> None:
        app = AgentCliApp()
        app._read_clipboard_text = lambda: "clipboard baseline"

        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+v")
            await pilot.pause()

            composer = app.query_one("#prompt_composer", PromptComposer)
            self.assertEqual(composer.text, "clipboard baseline")

    async def test_question_mark_toggle_contract(self) -> None:
        app = AgentCliApp()

        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("?")
            await pilot.pause()
            self.assertIn(app._t("footer.shortcuts_overlay_line1"), self._status_line_plain(app))
            self.assertIn(app._t("footer.shortcuts_overlay_line2"), self._footer_plain(app))

            await pilot.press("?")
            await pilot.pause()
            self.assertIn(app._t("footer.context_left"), self._footer_plain(app))

            await pilot.press("h")
            app._flush_prompt_composer_burst()
            await pilot.pause()
            await pilot.press("?")
            app._flush_prompt_composer_burst()
            await pilot.pause()
            self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "h?")
            self.assertNotIn(app._t("footer.shortcuts_overlay_line1"), self._status_line_plain(app))

    async def test_busy_tab_queues_follow_up_prompt(self) -> None:
        runtime = _BlockingQueueRuntime()
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
            await pilot.pause()
            await pilot.press("tab")
            await pilot.pause()

            self.assertEqual(runtime.calls, ["first job"])
            self.assertEqual(app.query_one("#prompt_composer", PromptComposer).text, "")

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

    async def test_tab_autocompletes_slash_command(self) -> None:
        app = AgentCliApp(runtime=_SlashPopupRuntime())

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("/he")
            await pilot.pause()
            await pilot.press("tab")
            await pilot.pause()

            composer = app.query_one("#prompt_composer", PromptComposer)
            popup = app.query_one("#slash_popup", SlashCommandPopup)
            self.assertEqual(composer.text, "/help ")
            self.assertEqual(popup.styles.display, "none")

    async def test_tab_autocompletes_workspace_file_reference(self) -> None:
        app = AgentCliApp()
        app._workspace_files_cache = ["app.py", "README.md"]

        async with app.run_test() as pilot:
            await pilot.pause()
            app._set_prompt_text("@ap")
            await pilot.pause()
            await pilot.press("tab")
            await pilot.pause()

            composer = app.query_one("#prompt_composer", PromptComposer)
            popup = app.query_one("#slash_popup", SlashCommandPopup)
            self.assertEqual(composer.text, "@app.py ")
            self.assertEqual(popup.styles.display, "none")

    async def test_escape_semantics_cover_busy_and_popups(self) -> None:
        interrupt_runtime = _InterruptRuntime()
        interrupt_app = AgentCliApp(runtime=interrupt_runtime)

        async with interrupt_app.run_test() as pilot:
            await pilot.pause()
            interrupt_app._set_busy(True)
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(interrupt_runtime.interrupt_calls, 1)
            self.assertTrue(interrupt_app._live_turn_interrupt_requested)

        slash_app = AgentCliApp(runtime=_SlashPopupRuntime())
        async with slash_app.run_test() as pilot:
            await pilot.pause()
            slash_app._set_prompt_text("/he")
            await pilot.pause()
            popup = slash_app.query_one("#slash_popup", SlashCommandPopup)
            self.assertEqual(popup.styles.display, "block")
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(popup.styles.display, "none")
            self.assertEqual(slash_app.query_one("#prompt_composer", PromptComposer).text, "/he")

        file_app = AgentCliApp()
        file_app._workspace_files_cache = ["app.py", "README.md"]
        async with file_app.run_test() as pilot:
            await pilot.pause()
            file_app._set_prompt_text("@ap")
            await pilot.pause()
            popup = file_app.query_one("#slash_popup", SlashCommandPopup)
            self.assertEqual(popup.styles.display, "block")
            await pilot.press("escape")
            await pilot.pause()
            self.assertEqual(popup.styles.display, "none")
            self.assertEqual(file_app.query_one("#prompt_composer", PromptComposer).text, "@ap")

    async def test_ctrl_p_and_ctrl_n_navigate_history(self) -> None:
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

    async def test_slash_history_navigation_does_not_open_completion_popup(self) -> None:
        with TemporaryDirectory() as tmpdir:
            history_home = Path(tmpdir)
            seed_app = AgentCliApp(runtime=_SlashPopupRuntime(), prompt_history_home=history_home)
            seed_app._record_prompt_history("first command")
            seed_app._record_prompt_history("/help")
            seed_app._record_prompt_history("second command")
            app = AgentCliApp(runtime=_SlashPopupRuntime(), prompt_history_home=history_home)

            async with app.run_test() as pilot:
                await pilot.pause()
                composer = app.query_one("#prompt_composer", PromptComposer)
                popup = app.query_one("#slash_popup", SlashCommandPopup)

                await pilot.press("up")
                await pilot.pause()
                self.assertEqual(composer.text, "second command")

                await pilot.press("up")
                await pilot.pause()
                self.assertEqual(composer.text, "/help")
                self.assertEqual(popup.styles.display, "none")
                self.assertFalse(app.has_active_completion_popup())

                await pilot.press("up")
                await pilot.pause()
                self.assertEqual(composer.text, "first command")

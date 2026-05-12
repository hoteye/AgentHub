from __future__ import annotations

import unittest

from textual.widgets import Static

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.models import PromptResponse


class _TaskHintRuntime:
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
        self.turn_event_callback = None

    def slash_command_matches(self, query: str) -> list[dict[str, str]]:
        _ = query
        return []

    def slash_command_completion(self, query: str) -> str | None:
        _ = query
        return None

    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        return PromptResponse(
            user_text=text,
            assistant_text="processed",
            attachments=list(attachments or []),
            status=self.agent.provider_status(),
            handled_as_command=False,
        )

    def interrupt_active_run(self) -> dict[str, object]:
        return {"ok": False, "interrupted": False}


class _ThreadNameRuntime(_TaskHintRuntime):
    class _ThreadStore:
        def __init__(self, name: str) -> None:
            self.name = name

        def get_thread(self, thread_id: str) -> dict[str, str] | None:
            if not thread_id:
                return None
            return {"name": self.name}

    def __init__(self, *, thread_name: str) -> None:
        super().__init__()
        self.thread_name = thread_name
        self.thread_id = "thread-1"
        self.thread_store = self._ThreadStore(thread_name)


class TuiTranscriptTaskHintTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _static_plain(widget: Static) -> str:
        renderable = getattr(widget, "renderable", None)
        if renderable is not None:
            return getattr(renderable, "plain", str(renderable))
        rendered = widget.render()
        return getattr(rendered, "plain", str(rendered))

    async def test_transcript_task_hint_is_hidden_in_prompt_mode_and_shown_in_transcript_mode(self) -> None:
        app = AgentCliApp(runtime=_ThreadNameRuntime(thread_name="排查登录超时根因"))

        async with app.run_test() as pilot:
            await pilot.pause()
            hint = app.query_one("#transcript_task_hint", Static)
            self.assertEqual(hint.styles.display, "none")

            await pilot.press("ctrl+o")
            await pilot.pause()

            self.assertEqual(hint.styles.display, "block")
            self.assertEqual(self._static_plain(hint), "排查登录超时根因")

            await pilot.press("escape")
            await pilot.pause()

            self.assertEqual(hint.styles.display, "none")

    async def test_transcript_task_hint_falls_back_to_top_title_when_thread_name_is_placeholder(self) -> None:
        app = AgentCliApp(runtime=_ThreadNameRuntime(thread_name="Thread 2026-04-10 10:00:00"))

        async with app.run_test() as pilot:
            await pilot.pause()

            app._set_prompt_text("请帮我定位登录超时根因并补回归测试。")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await app._wait_for_runtime_idle()

            await pilot.press("ctrl+o")
            await pilot.pause()

            hint = app.query_one("#transcript_task_hint", Static)
            self.assertEqual(self._static_plain(hint), "定位登录超时根因并补回归测试")

    async def test_transcript_task_hint_uses_base_title_when_no_meaningful_source_exists(self) -> None:
        app = AgentCliApp(runtime=_TaskHintRuntime())

        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("ctrl+o")
            await pilot.pause()

            hint = app.query_one("#transcript_task_hint", Static)
            self.assertEqual(self._static_plain(hint), "AgentHub")

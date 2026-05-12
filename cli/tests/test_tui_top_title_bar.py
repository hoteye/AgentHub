from __future__ import annotations

import unittest

from textual.widgets import Static

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.models import PromptResponse
from cli.agent_cli.ui.tab_bar import TabBar


class _TopTitleRuntime:
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


class _ThreadNameRuntime(_TopTitleRuntime):
    class _ThreadStore:
        def __init__(self, name: str) -> None:
            self.name = name

        def get_thread(self, thread_id: str) -> dict[str, str] | None:
            if not thread_id:
                return None
            return {"name": self.name}

    def __init__(
        self,
        *,
        thread_name: str,
        persisted_name: str | None = None,
        name_after_prompt: str | None = None,
    ) -> None:
        super().__init__()
        self.thread_name = thread_name
        self.thread_id = "thread-1"
        self.thread_store = self._ThreadStore(
            persisted_name if persisted_name is not None else thread_name
        )
        self._name_after_prompt = str(name_after_prompt or "").strip()

    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        response = super().handle_prompt(text, attachments=attachments)
        if self._name_after_prompt:
            self.thread_store.name = self._name_after_prompt
        return response


class TuiTopTitleBarTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _tab_bar_plain(app: AgentCliApp) -> str:
        tab_bar = app.query_one("#tab_bar", TabBar)
        return tab_bar.render().plain

    @staticmethod
    def _top_title_plain(app: AgentCliApp) -> str:
        top_title = app.query_one("#top_title_bar", Static)
        renderable = getattr(top_title, "renderable", "")
        return str(getattr(renderable, "plain", renderable))

    async def test_top_title_bar_defaults_to_agenthub(self) -> None:
        app = AgentCliApp(runtime=_TopTitleRuntime())

        async with app.run_test() as pilot:
            await pilot.pause()
            plain = self._top_title_plain(app)
            self.assertIn("AgentHub", plain)
            self.assertIn("1", self._tab_bar_plain(app))
            self.assertEqual(self._top_title_plain(app).strip(), "AgentHub")
            self.assertEqual(
                app.query_one("#top_title_icon", Static).renderable,
                app._top_title_leading_symbol,
            )
            self.assertEqual(app.query_one("#top_title_icon", Static).styles.width.value, 2)
            self.assertEqual(app.query_one("#top_title_bar", Static).styles.text_align, "center")

    async def test_top_title_bar_updates_for_prompt_and_ignores_slash_command(
        self,
    ) -> None:
        app = AgentCliApp(runtime=_TopTitleRuntime())

        async with app.run_test() as pilot:
            await pilot.pause()

            app._set_prompt_text("请帮我排查登录超时并补回归测试。")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await app._wait_for_runtime_idle()

            plain = self._top_title_plain(app)
            self.assertIn("排查登录超时并补回归测试", plain)

            app._set_prompt_text("/provider")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await app._wait_for_runtime_idle()

            self.assertEqual(self._top_title_plain(app), plain)

    async def test_top_title_bar_uses_meaningful_thread_name_on_start(self) -> None:
        app = AgentCliApp(runtime=_ThreadNameRuntime(thread_name="排查登录超时并补回归测试"))

        async with app.run_test() as pilot:
            await pilot.pause()
            plain = self._top_title_plain(app)
            self.assertIn("排查登录超时并补回归测试", plain)

    async def test_top_title_bar_ignores_default_thread_placeholder_name(self) -> None:
        app = AgentCliApp(runtime=_ThreadNameRuntime(thread_name="Thread 2026-04-10 10:00:00"))

        async with app.run_test() as pilot:
            await pilot.pause()
            plain = self._top_title_plain(app)
            self.assertIn("AgentHub", plain)

    async def test_top_title_bar_syncs_from_persisted_thread_name_after_first_prompt(
        self,
    ) -> None:
        runtime = _ThreadNameRuntime(
            thread_name="Thread 2026-04-10 10:00:00",
            persisted_name="Thread 2026-04-10 10:00:00",
            name_after_prompt="定位登录超时根因",
        )
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            plain = self._top_title_plain(app)
            self.assertIn("AgentHub", plain)

            app._set_prompt_text("请帮我定位登录超时并补回归测试。")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await app._wait_for_runtime_idle()

            self.assertIn("定位登录超时根因", self._top_title_plain(app))

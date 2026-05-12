from __future__ import annotations

import unittest
from unittest.mock import patch

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.models import PromptResponse, ToolEvent
from cli.agent_cli.ui import request_user_input_modal


class _BaseRuntime:
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

    @staticmethod
    def slash_command_matches(query: str) -> list[dict[str, str]]:
        del query
        return []

    @staticmethod
    def slash_command_completion(query: str) -> str | None:
        del query
        return None

    @staticmethod
    def interrupt_active_run() -> dict[str, object]:
        return {"ok": False, "interrupted": False}


class _RequestNoticeRuntime(_BaseRuntime):
    def __init__(self, *, question_count: int) -> None:
        super().__init__()
        self.question_count = max(1, int(question_count))

    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del text, attachments
        questions = [
            {
                "id": f"q_{index}",
                "header": f"Q{index}",
                "question": f"Question {index}?",
                "options": [
                    {"label": "Yes (Recommended)", "description": "Continue."},
                    {"label": "No", "description": "Stop."},
                ],
            }
            for index in range(1, self.question_count + 1)
        ]
        handler = getattr(self, "request_user_input_handler", None)
        response = handler({"questions": questions}) if callable(handler) else None
        event = ToolEvent(
            name="request_user_input",
            ok=bool(isinstance(response, dict)),
            summary="request_user_input completed" if isinstance(response, dict) else "request_user_input cancelled",
            payload={"questions": questions, "response": dict(response or {}) if isinstance(response, dict) else {}},
        )
        return PromptResponse(
            user_text="trigger request notice counts",
            assistant_text="request completed" if isinstance(response, dict) else "request cancelled",
            tool_events=[event],
            status=self.agent.provider_status(),
            handled_as_command=True,
        )


class RequestUserInputStartNoticeCountsTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _transcript_text(app: AgentCliApp) -> str:
        return app.query_one("#main_log").text

    async def _run_and_capture_transcript(self, *, question_count: int, language: str | None = None) -> str:
        runtime = _RequestNoticeRuntime(question_count=question_count)
        app = AgentCliApp(runtime=runtime, language=language)

        def _presenter(*, payload, on_submit, on_cancel) -> bool:
            del payload, on_submit, on_cancel
            return False

        app._request_user_input_modal_presenter = _presenter
        app._request_user_input_test_responder = None

        with patch.object(request_user_input_modal, "present_request_user_input", return_value=False):
            async with app.run_test() as pilot:
                await pilot.pause()
                await app._enqueue_runtime_request("trigger request notice counts", [])
                await app._wait_for_runtime_idle()
                await pilot.pause()
                self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")
                return self._transcript_text(app)

    async def test_default_behavior_uses_legacy_english_singular_notice_for_one_question(self) -> None:
        transcript = await self._run_and_capture_transcript(question_count=1, language=None)
        self.assertIn("1 question", transcript)
        self.assertIn("Model requested user input", transcript)

    async def test_explicit_zh_cn_locale_uses_localized_plural_notice_with_count(self) -> None:
        transcript = await self._run_and_capture_transcript(question_count=3, language="zh-CN")
        self.assertIn("3", transcript)
        self.assertIn("模型请求用户输入", transcript)
        self.assertIn("个问题", transcript)

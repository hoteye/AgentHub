from __future__ import annotations

import unittest

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.models import PromptResponse, ToolEvent


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


class _TranscriptSummaryRuntime(_BaseRuntime):
    def __init__(self, *, question_id: str, answer: str) -> None:
        super().__init__()
        self._question_id = str(question_id)
        self._answer = str(answer)

    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del text, attachments
        return PromptResponse(
            user_text="trigger summary",
            assistant_text="done",
            tool_events=[
                ToolEvent(
                    name="request_user_input",
                    ok=True,
                    summary="request_user_input completed",
                    payload={
                        "response": {
                            "answers": {
                                self._question_id: {"answers": [self._answer]},
                            }
                        }
                    },
                )
            ],
            status=self.agent.provider_status(),
            handled_as_command=True,
        )


class RequestUserInputTranscriptLocalizationTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _transcript_text(app: AgentCliApp) -> str:
        lines: list[str] = []
        for line in app._transcript_lines:
            if isinstance(line, str):
                lines.append(line)
                continue
            plain = getattr(line, "plain", None)
            if isinstance(plain, str):
                lines.append(plain)
                continue
            lines.append(str(line))
        return "\n".join(lines)

    async def test_explicit_zh_cn_summary_localizes_prefix_and_preserves_chinese_fragments(self) -> None:
        runtime = _TranscriptSummaryRuntime(question_id="确认路径", answer="继续")
        app = AgentCliApp(runtime=runtime, language="zh-CN")

        async with app.run_test() as pilot:
            await pilot.pause()
            await app._enqueue_runtime_request("trigger zh-cn summary", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

        transcript = self._transcript_text(app)
        self.assertIn("用户输入", transcript)
        self.assertIn("确认路径", transcript)
        self.assertIn("继续", transcript)
        self.assertIn("用户输入 确认路径 -> 继续", transcript)

    async def test_default_language_preserves_legacy_english_summary_contract(self) -> None:
        runtime = _TranscriptSummaryRuntime(
            question_id="confirm_path",
            answer="Yes (Recommended)",
        )
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            await app._enqueue_runtime_request("trigger default summary", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

        transcript = self._transcript_text(app)
        self.assertIn("User input confirm_path -> Yes (Recommended)", transcript)
        self.assertNotIn("确认路径", transcript)


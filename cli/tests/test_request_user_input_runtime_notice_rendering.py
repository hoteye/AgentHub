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


class _RequestUserInputRuntime(_BaseRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.last_response: dict[str, object] | None = None

    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        payload = {
            "questions": [
                {
                    "id": "confirm_path",
                    "header": "Confirm",
                    "question": "Proceed?",
                    "options": [
                        {"label": "Yes (Recommended)", "description": "Continue."},
                        {"label": "No", "description": "Stop."},
                    ],
                }
            ]
        }
        handler = getattr(self, "request_user_input_handler", None)
        response = handler(payload) if callable(handler) else None
        self.last_response = dict(response) if isinstance(response, dict) else None
        event = ToolEvent(
            name="request_user_input",
            ok=bool(isinstance(response, dict)),
            summary="request_user_input completed" if isinstance(response, dict) else "request_user_input cancelled",
            payload={
                "questions": payload["questions"],
                "response": dict(response or {}) if isinstance(response, dict) else {},
            },
        )
        return PromptResponse(
            user_text=text,
            assistant_text="request completed" if isinstance(response, dict) else "request cancelled",
            tool_events=[event],
            status=self.agent.provider_status(),
            handled_as_command=True,
        )


class RequestUserInputRuntimeNoticeRenderingTest(unittest.IsolatedAsyncioTestCase):
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

    @staticmethod
    def _assert_runtime_notice_rendered(text: str) -> None:
        rendered = str(text or "").strip()
        assert rendered
        lowered = rendered.lower()
        assert "rui." not in lowered
        assert "status." not in lowered
        assert "system." not in lowered

    @staticmethod
    async def _wait_until_pending_request_registered(app: AgentCliApp, pilot, *, attempts: int = 80) -> None:
        for _ in range(attempts):
            await pilot.pause()
            with app._request_user_input_pending_lock:
                if app._request_user_input_pending is not None:
                    return
        raise AssertionError("request_user_input pending request was not registered in time")

    async def test_runtime_waiting_and_escape_cancel_notices_render_in_zh_cn(self) -> None:
        runtime = _RequestUserInputRuntime()
        app = AgentCliApp(runtime=runtime, language="zh-CN")
        app._request_user_input_modal_presenter = (
            lambda *, payload, on_submit, on_cancel: bool(payload or on_submit or on_cancel)
        )

        async with app.run_test() as pilot:
            await pilot.pause()
            await app._enqueue_runtime_request("trigger zh-cn waiting", [])
            await self._wait_until_pending_request_registered(app, pilot)

            with app._request_user_input_pending_lock:
                self.assertIsNotNone(app._request_user_input_pending)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "true")

            status_line = app.query_one("#status_line").renderable.plain
            self._assert_runtime_notice_rendered(status_line)

            self.assertTrue(app._cancel_request_user_input_on_escape())
            await app._wait_for_runtime_idle()
            await pilot.pause()

            transcript = self._transcript_text(app)
            requested_notice = app._t("system.request_user_input.requested.one")
            cancelled_notice = app._t("system.request_user_input.cancelled.user")
            self.assertIn(requested_notice, transcript)
            self.assertIn(cancelled_notice, transcript)
            self._assert_runtime_notice_rendered(requested_notice)
            self._assert_runtime_notice_rendered(cancelled_notice)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")

    async def test_runtime_fallback_cancel_notice_and_waiting_state_reset_in_zh_cn(self) -> None:
        runtime = _RequestUserInputRuntime()
        app = AgentCliApp(runtime=runtime, language="zh-CN")

        def _presenter(*, payload, on_submit, on_cancel) -> bool:
            del payload, on_submit, on_cancel
            return False

        app._request_user_input_modal_presenter = _presenter
        app._request_user_input_test_responder = None

        with patch.object(request_user_input_modal, "present_request_user_input", return_value=False):
            async with app.run_test() as pilot:
                await pilot.pause()
                await app._enqueue_runtime_request("trigger zh-cn fallback", [])
                await app._wait_for_runtime_idle()
                await pilot.pause()

        transcript = self._transcript_text(app)
        fallback_notice = app._t("system.request_user_input.cancelled.interactive_unavailable")
        summary_notice = app._t("transcript.request_user_input.cancelled")

        self.assertIn(fallback_notice, transcript)
        self.assertIn(summary_notice, transcript)
        self._assert_runtime_notice_rendered(fallback_notice)
        self._assert_runtime_notice_rendered(summary_notice)
        self.assertIsNone(runtime.last_response)
        self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")

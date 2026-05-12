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


class RequestUserInputAppIntegrationTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _transcript_text(app: AgentCliApp) -> str:
        return app.query_one("#main_log").text

    async def test_injected_presenter_submit_round_trip_normalizes_payload(self) -> None:
        runtime = _RequestUserInputRuntime()
        app = AgentCliApp(runtime=runtime)

        def _presenter(*, payload, on_submit, on_cancel) -> bool:
            del payload, on_cancel
            on_submit({"answers": {"confirm_path": "Yes (Recommended)"}})
            return True

        app._request_user_input_modal_presenter = _presenter

        async with app.run_test() as pilot:
            await pilot.pause()
            await app._enqueue_runtime_request("trigger submit", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

        self.assertIsNotNone(runtime.last_response)
        assert runtime.last_response is not None
        self.assertEqual(
            runtime.last_response["answers"]["confirm_path"]["answers"],
            ["Yes (Recommended)"],
        )
        self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")

    async def test_injected_presenter_cancel_round_trip_returns_none(self) -> None:
        runtime = _RequestUserInputRuntime()
        app = AgentCliApp(runtime=runtime)

        def _presenter(*, payload, on_submit, on_cancel) -> bool:
            del payload, on_submit
            on_cancel()
            return True

        app._request_user_input_modal_presenter = _presenter

        async with app.run_test() as pilot:
            await pilot.pause()
            await app._enqueue_runtime_request("trigger cancel", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

        self.assertIsNone(runtime.last_response)
        self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")

    async def test_presenter_unavailable_falls_back_to_conservative_cancel(self) -> None:
        runtime = _RequestUserInputRuntime()
        app = AgentCliApp(runtime=runtime)
        app._request_user_input_modal_presenter = None
        app._request_user_input_test_responder = None

        with patch.object(request_user_input_modal, "present_request_user_input", return_value=False):
            async with app.run_test() as pilot:
                await pilot.pause()
                await app._enqueue_runtime_request("trigger fallback cancel", [])
                await app._wait_for_runtime_idle()
                await pilot.pause()
                transcript = self._transcript_text(app)
                self.assertIn("request_user_input cancelled: interactive UI unavailable.", transcript)

        self.assertIsNone(runtime.last_response)
        self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")

    async def test_presenter_declines_request_and_triggers_conservative_cancel(self) -> None:
        runtime = _RequestUserInputRuntime()
        app = AgentCliApp(runtime=runtime)

        def _presenter(*, payload, on_submit, on_cancel) -> bool:
            del payload, on_submit, on_cancel
            return False

        app._request_user_input_modal_presenter = _presenter

        with patch.object(request_user_input_modal, "present_request_user_input", return_value=False):
            async with app.run_test() as pilot:
                await pilot.pause()
                await app._enqueue_runtime_request("trigger presenter decline", [])
                await app._wait_for_runtime_idle()
                await pilot.pause()
                transcript = self._transcript_text(app)
                self.assertIn("request_user_input cancelled: interactive UI unavailable.", transcript)

        self.assertIsNone(runtime.last_response)
        self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")

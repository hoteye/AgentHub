from __future__ import annotations

import threading
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


class _RequestUserInputRuntime(_BaseRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.last_response: dict[str, object] | None = None

    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        payload = _payload()
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


def _payload() -> dict[str, object]:
    return {
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


class RequestUserInputEscapeHatchRegressionTest(unittest.IsolatedAsyncioTestCase):
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

    async def test_escape_cancels_stalled_pending_request_user_input(self) -> None:
        runtime = _RequestUserInputRuntime()
        app = AgentCliApp(runtime=runtime)
        app._request_user_input_modal_presenter = (
            lambda *, payload, on_submit, on_cancel: bool(payload or on_submit or on_cancel)
        )

        async with app.run_test() as pilot:
            await pilot.pause()
            await app._enqueue_runtime_request("trigger escape hatch", [])

            for _ in range(50):
                await pilot.pause()
                with app._request_user_input_pending_lock:
                    if app._request_user_input_pending is not None:
                        break

            with app._request_user_input_pending_lock:
                self.assertIsNotNone(app._request_user_input_pending)

            await pilot.press("escape")
            await app._wait_for_runtime_idle()
            await pilot.pause()

            self.assertIsNone(runtime.last_response)
            with app._request_user_input_pending_lock:
                self.assertIsNone(app._request_user_input_pending)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")
            self.assertIn("User cancelled input request.", self._transcript_text(app))

    async def test_begin_shutdown_cancels_stalled_pending_request_user_input(self) -> None:
        runtime = _RequestUserInputRuntime()
        app = AgentCliApp(runtime=runtime)
        app._request_user_input_modal_presenter = (
            lambda *, payload, on_submit, on_cancel: bool(payload or on_submit or on_cancel)
        )
        thread_result: dict[str, object] = {}

        def _invoke_handler() -> None:
            thread_result["response"] = app._handle_request_user_input_from_runtime(_payload())

        async with app.run_test() as pilot:
            await pilot.pause()
            worker = threading.Thread(target=_invoke_handler)
            worker.start()

            for _ in range(50):
                await pilot.pause()
                with app._request_user_input_pending_lock:
                    if app._request_user_input_pending is not None:
                        break

            with app._request_user_input_pending_lock:
                self.assertIsNotNone(app._request_user_input_pending)

            app._begin_shutdown()
            worker.join(timeout=2)
            self.assertFalse(worker.is_alive())
            self.assertIsNone(thread_result.get("response"))
            with app._request_user_input_pending_lock:
                self.assertIsNone(app._request_user_input_pending)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")
            self.assertIsNone(getattr(runtime, "request_user_input_handler", None))
            self.assertIn("request_user_input cancelled: shutdown.", self._transcript_text(app))

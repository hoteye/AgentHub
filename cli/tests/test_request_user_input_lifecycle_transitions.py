from __future__ import annotations

import asyncio
import unittest

from cli.agent_cli.app import AgentCliApp, PromptComposer
from cli.agent_cli.models import PromptResponse


class _LifecycleRuntime:
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
        self.request_user_input_handler = None
        self.last_user_input_response: dict[str, object] | None = None
        self.prompt_count = 0
        self.last_prompt: str | None = None

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

    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        self.prompt_count += 1
        self.last_prompt = text
        if text.strip().lower() == "ping":
            return PromptResponse(
                user_text=text,
                assistant_text="pong",
                status=self.agent.provider_status(),
                handled_as_command=True,
            )
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
                    "is_other": True,
                }
            ]
        }
        handler = getattr(self, "request_user_input_handler", None)
        response = handler(payload) if callable(handler) else None
        self.last_user_input_response = dict(response) if isinstance(response, dict) else None
        return PromptResponse(
            user_text=text,
            assistant_text="request completed" if isinstance(response, dict) else "request cancelled",
            status=self.agent.provider_status(),
            handled_as_command=True,
        )


class RequestUserInputLifecycleTransitionsTest(unittest.IsolatedAsyncioTestCase):
    async def _wait_until_pending(self, app: AgentCliApp, pilot, *, timeout: float = 8.0) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            with app._request_user_input_pending_lock:
                if app._request_user_input_pending is not None:
                    return
            if asyncio.get_running_loop().time() >= deadline:
                self.fail("request_user_input pending state not observed in time")
            await pilot.pause()

    async def _assert_focus_is_composer(self, app: AgentCliApp, pilot, *, timeout: float = 8.0) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            composer = app.query_one("#prompt_composer", PromptComposer)
            if app.focused is composer:
                return
            if asyncio.get_running_loop().time() >= deadline:
                self.fail("prompt composer focus was not restored in time")
            await pilot.pause()

    async def test_shutdown_cleans_pending_state_and_waiting_marker(self) -> None:
        runtime = _LifecycleRuntime()
        app = AgentCliApp(runtime=runtime)

        def _presenter(*, payload, on_submit, on_cancel) -> bool:
            del payload, on_submit, on_cancel
            return True

        app._request_user_input_modal_presenter = _presenter

        async with app.run_test() as pilot:
            await pilot.pause()
            await app._enqueue_runtime_request("trigger pending request", [])
            await self._wait_until_pending(app, pilot)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "true")
            app._begin_shutdown()
            await app._wait_for_runtime_idle()
            await pilot.pause()

            with app._request_user_input_pending_lock:
                self.assertIsNone(app._request_user_input_pending)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")
            self.assertIsNone(getattr(runtime, "request_user_input_handler", None))

    async def test_focus_restores_after_submit_and_cancel_and_allows_followup_prompt(self) -> None:
        runtime = _LifecycleRuntime()
        app = AgentCliApp(runtime=runtime)

        def _submit_presenter(*, payload, on_submit, on_cancel) -> bool:
            del payload, on_cancel
            on_submit({"answers": {"confirm_path": {"answers": ["Yes (Recommended)"]}}})
            return True

        app._request_user_input_modal_presenter = _submit_presenter

        async with app.run_test() as pilot:
            await pilot.pause()
            await app._enqueue_runtime_request("submit flow", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

            self.assertIsNotNone(runtime.last_user_input_response)
            await self._assert_focus_is_composer(app, pilot)

            def _pending_presenter(*, payload, on_submit, on_cancel) -> bool:
                del payload, on_submit, on_cancel
                return True

            app._request_user_input_modal_presenter = _pending_presenter
            await app._enqueue_runtime_request("cancel flow", [])
            await self._wait_until_pending(app, pilot)
            await pilot.press("escape")
            await app._wait_for_runtime_idle()
            await pilot.pause()

            await self._assert_focus_is_composer(app, pilot)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")

            await app._enqueue_runtime_request("ping", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

            self.assertEqual(runtime.last_prompt, "ping")
            self.assertGreaterEqual(runtime.prompt_count, 3)


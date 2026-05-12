from __future__ import annotations

import asyncio
import unittest

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.models import PromptResponse, ToolEvent


class _ReentrancyRuntime:
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
        self.handled_prompts: list[str] = []
        self.responses_by_prompt: dict[str, dict[str, object] | None] = {}

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
        self.handled_prompts.append(text)
        payload = {
            "questions": [
                {
                    "id": "confirm_path",
                    "header": "Confirm",
                    "question": f"Proceed for {text}?",
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
        normalized = dict(response) if isinstance(response, dict) else None
        self.responses_by_prompt[text] = normalized
        return PromptResponse(
            user_text=text,
            assistant_text="request completed" if isinstance(normalized, dict) else "request cancelled",
            tool_events=[
                ToolEvent(
                    name="request_user_input",
                    ok=bool(isinstance(normalized, dict)),
                    summary=(
                        "request_user_input completed"
                        if isinstance(normalized, dict)
                        else "request_user_input cancelled"
                    ),
                    payload={
                        "response": dict(normalized or {}) if isinstance(normalized, dict) else {},
                    },
                )
            ],
            status=self.agent.provider_status(),
            handled_as_command=True,
        )


class RequestUserInputReentrancyGuardTest(unittest.IsolatedAsyncioTestCase):
    async def _wait_until_pending(self, app: AgentCliApp, pilot, *, timeout: float = 8.0):
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            with app._request_user_input_pending_lock:
                pending = app._request_user_input_pending
            if pending is not None:
                return pending
            if asyncio.get_running_loop().time() >= deadline:
                self.fail("request_user_input pending state not observed in time")
            await pilot.pause()

    async def _wait_until_prompt_count(
        self,
        runtime: _ReentrancyRuntime,
        expected: int,
        pilot,
        *,
        timeout: float = 8.0,
    ) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            if len(runtime.handled_prompts) >= expected:
                return
            if asyncio.get_running_loop().time() >= deadline:
                self.fail(f"runtime did not handle {expected} prompts in time")
            await pilot.pause()

    async def test_second_request_does_not_overwrite_existing_pending_before_first_resolves(self) -> None:
        runtime = _ReentrancyRuntime()
        app = AgentCliApp(runtime=runtime)
        app._request_user_input_modal_presenter = (
            lambda *, payload, on_submit, on_cancel: bool(payload or on_submit or on_cancel)
        )

        async with app.run_test() as pilot:
            await pilot.pause()
            await app._enqueue_runtime_request("req-1", [])
            first_pending = await self._wait_until_pending(app, pilot)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "true")
            await self._wait_until_prompt_count(runtime, 1, pilot)

            await app._enqueue_runtime_request("req-2", [])
            for _ in range(10):
                await pilot.pause()
            with app._request_user_input_pending_lock:
                self.assertIs(app._request_user_input_pending, first_pending)
            self.assertEqual(len(runtime.handled_prompts), 1)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "true")

            app._on_request_user_input_cancel()
            await self._wait_until_prompt_count(runtime, 2, pilot)
            second_pending = await self._wait_until_pending(app, pilot)
            self.assertIsNot(second_pending, first_pending)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "true")

            app._on_request_user_input_cancel()
            await app._wait_for_runtime_idle()
            await pilot.pause()

        with app._request_user_input_pending_lock:
            self.assertIsNone(app._request_user_input_pending)
        self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")
        self.assertEqual(runtime.handled_prompts, ["req-1", "req-2"])
        self.assertIsNone(runtime.responses_by_prompt.get("req-1"))
        self.assertIsNone(runtime.responses_by_prompt.get("req-2"))

    async def test_second_request_processes_normally_after_first_cancelled(self) -> None:
        runtime = _ReentrancyRuntime()
        app = AgentCliApp(runtime=runtime)
        presenter_calls = {"count": 0}

        def _presenter(*, payload, on_submit, on_cancel) -> bool:
            del payload
            presenter_calls["count"] += 1
            if presenter_calls["count"] == 1:
                return True
            on_submit({"answers": {"confirm_path": "Yes (Recommended)"}})
            return True

        app._request_user_input_modal_presenter = _presenter

        async with app.run_test() as pilot:
            await pilot.pause()
            await app._enqueue_runtime_request("req-1", [])
            await self._wait_until_pending(app, pilot)
            await self._wait_until_prompt_count(runtime, 1, pilot)

            await app._enqueue_runtime_request("req-2", [])
            app._on_request_user_input_cancel()
            await app._wait_for_runtime_idle()
            await pilot.pause()

        self.assertEqual(runtime.handled_prompts, ["req-1", "req-2"])
        self.assertIsNone(runtime.responses_by_prompt.get("req-1"))
        second_response = runtime.responses_by_prompt.get("req-2")
        self.assertIsInstance(second_response, dict)
        assert isinstance(second_response, dict)
        self.assertEqual(
            second_response.get("answers", {}).get("confirm_path", {}).get("answers"),
            ["Yes (Recommended)"],
        )
        with app._request_user_input_pending_lock:
            self.assertIsNone(app._request_user_input_pending)
        self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")
        self.assertEqual(presenter_calls["count"], 2)

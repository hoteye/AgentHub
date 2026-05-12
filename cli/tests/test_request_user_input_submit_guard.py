from __future__ import annotations

import asyncio
import threading
import unittest

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.models import PromptAttachment, PromptResponse
from cli.agent_cli.runtime_core.request_user_input_contract_runtime import (
    normalize_request_user_input_questions,
)
from cli.agent_cli.ui.request_user_input_modal import RequestUserInputOverlay
from cli.agent_cli.ui.request_user_input_state_runtime import PHASE_QUESTIONS, PHASE_REVIEW


def _presenter_available() -> bool:
    try:
        from cli.agent_cli.ui.request_user_input_modal import present_request_user_input
    except Exception:
        return False
    return callable(present_request_user_input)


class _SubmitGuardRuntime:
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

        self.request_started = threading.Event()
        self.request_finished = threading.Event()
        self.last_response: dict[str, object] | None = None

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

    def handle_prompt(self, text: str, *, attachments: list[PromptAttachment] | None = None) -> PromptResponse:
        del text, attachments
        payload = {
            "questions": normalize_request_user_input_questions(
                [
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
            )
        }
        handler = getattr(self, "request_user_input_handler", None)
        response = None
        if callable(handler):
            self.request_started.set()
            response = handler(payload)
            self.request_finished.set()
        self.last_response = dict(response) if isinstance(response, dict) else None
        assistant_text = "request_user_input cancelled"
        if isinstance(self.last_response, dict):
            assistant_text = "submit guard smoke"
        return PromptResponse(
            user_text="submit guard smoke",
            assistant_text=assistant_text,
            status=self.agent.provider_status(),
            handled_as_command=False,
        )


class RequestUserInputSubmitGuardTest(unittest.IsolatedAsyncioTestCase):
    async def _wait_event(self, event: threading.Event, *, timeout: float = 5.0) -> None:
        await asyncio.wait_for(asyncio.to_thread(event.wait, timeout), timeout=timeout + 0.2)

    async def _wait_overlay_phase(self, app: AgentCliApp, pilot, *, phase: str, timeout: float = 5.0) -> RequestUserInputOverlay:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            try:
                overlay = app.query_one(f"#{RequestUserInputOverlay.ROOT_ID}", RequestUserInputOverlay)
            except Exception:
                overlay = None
            state = getattr(overlay, "_state", None) if overlay is not None else None
            if isinstance(overlay, RequestUserInputOverlay) and overlay.is_active and getattr(state, "phase", None) == phase:
                return overlay
            if asyncio.get_running_loop().time() >= deadline:
                self.fail(f"request_user_input overlay did not enter phase={phase}")
            await pilot.pause()

    async def _submit_prompt(self, app: AgentCliApp, pilot, text: str) -> None:
        app._set_prompt_text(text)
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

    async def test_cannot_submit_successfully_without_any_selection(self) -> None:
        if not _presenter_available():
            self.skipTest("request_user_input presenter not available")

        runtime = _SubmitGuardRuntime()
        app = AgentCliApp(runtime=runtime)
        app._request_user_input_modal_presenter = None

        async with app.run_test() as pilot:
            await pilot.pause()
            await self._submit_prompt(app, pilot, "submit guard empty selection")
            await self._wait_event(runtime.request_started)

            overlay = await self._wait_overlay_phase(app, pilot, phase=PHASE_QUESTIONS)
            overlay.focus()
            await pilot.pause()

            await pilot.press("tab")
            await pilot.pause()
            overlay = await self._wait_overlay_phase(app, pilot, phase=PHASE_REVIEW)

            await pilot.press("enter")
            await pilot.pause()
            overlay = await self._wait_overlay_phase(app, pilot, phase=PHASE_REVIEW)
            state = getattr(overlay, "_state", None)
            self.assertIsNotNone(state)
            self.assertTrue(bool(getattr(state, "notice", "")))
            self.assertFalse(runtime.request_finished.is_set())

            await pilot.press("escape")
            await pilot.pause()
            await self._wait_event(runtime.request_finished)
            await app._wait_for_runtime_idle()

        self.assertIsNone(runtime.last_response)
        self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")

    async def test_other_requires_non_empty_text_before_successful_submit(self) -> None:
        if not _presenter_available():
            self.skipTest("request_user_input presenter not available")

        runtime = _SubmitGuardRuntime()
        app = AgentCliApp(runtime=runtime)
        app._request_user_input_modal_presenter = None

        async with app.run_test() as pilot:
            await pilot.pause()
            await self._submit_prompt(app, pilot, "submit guard other text required")
            await self._wait_event(runtime.request_started)

            overlay = await self._wait_overlay_phase(app, pilot, phase=PHASE_QUESTIONS)
            overlay.focus()
            await pilot.pause()

            await pilot.press("down")
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            await pilot.press("tab")
            await pilot.pause()
            await self._wait_overlay_phase(app, pilot, phase=PHASE_REVIEW)
            await pilot.press("enter")
            await pilot.pause()
            overlay = await self._wait_overlay_phase(app, pilot, phase=PHASE_REVIEW)
            state = getattr(overlay, "_state", None)
            self.assertIsNotNone(state)
            self.assertTrue(bool(getattr(state, "notice", "")))
            self.assertFalse(runtime.request_finished.is_set())

            await pilot.press("down")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await self._wait_overlay_phase(app, pilot, phase=PHASE_QUESTIONS)

            for char in "custom delivery":
                await pilot.press(char)
            await pilot.pause()
            await pilot.press("tab")
            await pilot.pause()
            await self._wait_overlay_phase(app, pilot, phase=PHASE_REVIEW)
            await pilot.press("enter")
            await pilot.pause()
            await self._wait_event(runtime.request_finished)
            await app._wait_for_runtime_idle()

        self.assertIsInstance(runtime.last_response, dict)
        assert runtime.last_response is not None
        answers = dict(runtime.last_response.get("answers") or {})
        self.assertEqual(answers["confirm_path"]["answers"], ["custom delivery"])
        self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")

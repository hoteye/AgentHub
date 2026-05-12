from __future__ import annotations

import asyncio
import threading
import unittest

from cli.agent_cli.app import AgentCliApp, PromptComposer
from cli.agent_cli.models import PromptAttachment, PromptResponse
from cli.agent_cli.runtime_core.request_user_input_contract_runtime import (
    normalize_request_user_input_questions,
)
from cli.agent_cli.ui.request_user_input_modal import RequestUserInputOverlay


def _presenter_available() -> bool:
    try:
        from cli.agent_cli.ui.request_user_input_modal import present_request_user_input
    except Exception:
        return False
    return callable(present_request_user_input)


class _MultiQuestionRuntime:
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
        questions = [
            {
                "id": "confirm_path",
                "header": "Confirm",
                "question": "Proceed?",
                "options": [
                    {"label": "Yes (Recommended)", "description": "Continue."},
                    {"label": "No", "description": "Stop."},
                ],
            },
            {
                "id": "delivery",
                "header": "Deliver",
                "question": "Deliverable?",
                "options": [
                    {"label": "Patch", "description": "Patch only."},
                    {"label": "Patch + notes", "description": "Patch and short notes."},
                ],
            },
        ]
        payload = {"questions": normalize_request_user_input_questions(questions)}
        handler = getattr(self, "request_user_input_handler", None)
        response = None
        if callable(handler):
            self.request_started.set()
            response = handler(payload)
            self.request_finished.set()
        self.last_response = dict(response) if isinstance(response, dict) else None
        assistant_text = "request_user_input cancelled"
        if isinstance(self.last_response, dict):
            assistant_text = "multi-question ui smoke"
        return PromptResponse(
            user_text="multi-question ui smoke",
            assistant_text=assistant_text,
            status=self.agent.provider_status(),
            handled_as_command=False,
        )


class RequestUserInputMultiQuestionUiSmokeTest(unittest.IsolatedAsyncioTestCase):
    async def _wait_event(self, event: threading.Event, *, timeout: float = 2.0) -> None:
        await asyncio.wait_for(asyncio.to_thread(event.wait, timeout), timeout=timeout + 0.2)

    async def _wait_overlay_active(self, app: AgentCliApp, pilot, *, timeout: float = 2.0) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            try:
                overlay = app.query_one(f"#{RequestUserInputOverlay.ROOT_ID}", RequestUserInputOverlay)
            except Exception:
                overlay = None
            if isinstance(overlay, RequestUserInputOverlay) and overlay.is_active:
                return
            if asyncio.get_running_loop().time() >= deadline:
                self.fail("request_user_input overlay did not become active in time")
            await pilot.pause()

    @staticmethod
    def _overlay(app: AgentCliApp) -> RequestUserInputOverlay:
        return app.query_one(f"#{RequestUserInputOverlay.ROOT_ID}", RequestUserInputOverlay)

    async def _submit_prompt(self, app: AgentCliApp, pilot, text: str) -> None:
        app._set_prompt_text(text)
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

    async def test_two_questions_submit_with_second_other_text_round_trip(self) -> None:
        if not _presenter_available():
            self.skipTest("request_user_input presenter not available")

        runtime = _MultiQuestionRuntime()
        app = AgentCliApp(runtime=runtime)
        app._request_user_input_modal_presenter = None
        composer_focused = False

        async with app.run_test() as pilot:
            await pilot.pause()
            await self._submit_prompt(app, pilot, "ui smoke multi question")
            await self._wait_event(runtime.request_started)
            await self._wait_overlay_active(app, pilot)
            self._overlay(app).focus()
            await pilot.pause()

            await pilot.press("enter")
            await pilot.pause()

            await pilot.press("down")
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            for char in "custom delivery":
                if char == " ":
                    await pilot.press("space")
                else:
                    await pilot.press(char)
            await pilot.pause()

            await pilot.press("tab")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await self._wait_event(runtime.request_finished)
            await pilot.pause()
            composer = app.query_one("#prompt_composer", PromptComposer)
            composer_focused = app.focused is composer

        self.assertIsInstance(runtime.last_response, dict)
        assert runtime.last_response is not None
        answers = dict(runtime.last_response.get("answers") or {})
        self.assertEqual(
            answers["confirm_path"]["answers"],
            ["Yes (Recommended)"],
        )
        self.assertIn("delivery", answers)
        self.assertEqual(answers["delivery"]["answers"], ["custom delivery"])
        self.assertTrue(composer_focused)

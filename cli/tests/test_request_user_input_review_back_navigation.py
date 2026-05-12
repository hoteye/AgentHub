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


class _ReviewBackRuntime:
    class _Agent:
        @staticmethod
        def provider_status() -> dict[str, str]:
            return {
                "provider_name": "test",
                "provider_model": "test-model",
                "provider_ready": "true",
            }

    def __init__(self, *, include_second_question: bool = True) -> None:
        self.agent = self._Agent()
        self.activity_callback = None
        self.turn_event_callback = None
        self.request_user_input_handler = None
        self.include_second_question = bool(include_second_question)

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
            }
        ]
        if self.include_second_question:
            questions.append(
                {
                    "id": "delivery",
                    "header": "Deliver",
                    "question": "Deliverable?",
                    "options": [
                        {"label": "Patch", "description": "Patch only."},
                        {"label": "Patch + notes", "description": "Patch and short notes."},
                    ],
                }
            )
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
            assistant_text = "review-back smoke"
        return PromptResponse(
            user_text="review-back smoke",
            assistant_text=assistant_text,
            status=self.agent.provider_status(),
            handled_as_command=False,
        )


class RequestUserInputReviewBackNavigationTest(unittest.IsolatedAsyncioTestCase):
    async def _wait_event(self, event: threading.Event, *, timeout: float = 5.0) -> None:
        await asyncio.wait_for(asyncio.to_thread(event.wait, timeout), timeout=timeout + 0.2)

    async def _wait_overlay_active(self, app: AgentCliApp, pilot, *, timeout: float = 5.0) -> None:
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

    async def _wait_overlay_phase(self, app: AgentCliApp, pilot, *, phase: str, timeout: float = 5.0) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            overlay = self._overlay(app)
            state = getattr(overlay, "_state", None)
            if isinstance(overlay, RequestUserInputOverlay) and overlay.is_active and getattr(state, "phase", None) == phase:
                return
            if asyncio.get_running_loop().time() >= deadline:
                self.fail(f"request_user_input overlay did not enter phase={phase}")
            await pilot.pause()

    async def _submit_prompt(self, app: AgentCliApp, pilot, text: str) -> None:
        app._set_prompt_text(text)
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

    async def test_review_edit_then_resubmit_uses_latest_selection(self) -> None:
        if not _presenter_available():
            self.skipTest("request_user_input presenter not available")

        runtime = _ReviewBackRuntime(include_second_question=True)
        app = AgentCliApp(runtime=runtime)
        app._request_user_input_modal_presenter = None

        async with app.run_test() as pilot:
            await pilot.pause()
            await self._submit_prompt(app, pilot, "review back two-question")
            await self._wait_event(runtime.request_started)
            await self._wait_overlay_active(app, pilot)
            self._overlay(app).focus()
            await pilot.pause()

            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await self._wait_overlay_phase(app, pilot, phase=PHASE_REVIEW)

            await pilot.press("down")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await self._wait_overlay_phase(app, pilot, phase=PHASE_QUESTIONS)

            await pilot.press("down")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await self._wait_overlay_phase(app, pilot, phase=PHASE_REVIEW)

            await pilot.press("enter")
            await pilot.pause()
            await self._wait_event(runtime.request_finished)
            await pilot.pause()

        self.assertIsInstance(runtime.last_response, dict)
        assert runtime.last_response is not None
        answers = dict(runtime.last_response.get("answers") or {})
        self.assertEqual(answers["confirm_path"]["answers"], ["No"])
        self.assertEqual(answers["delivery"]["answers"], ["Patch"])

    async def test_other_value_not_leaking_after_review_edit_to_non_other(self) -> None:
        if not _presenter_available():
            self.skipTest("request_user_input presenter not available")

        runtime = _ReviewBackRuntime(include_second_question=False)
        app = AgentCliApp(runtime=runtime)
        app._request_user_input_modal_presenter = None

        async with app.run_test() as pilot:
            await pilot.pause()
            await self._submit_prompt(app, pilot, "review back other override")
            await self._wait_event(runtime.request_started)
            await self._wait_overlay_active(app, pilot)
            self._overlay(app).focus()
            await pilot.pause()

            await pilot.press("down")
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            for char in "legacy":
                await pilot.press(char)
            await pilot.pause()
            await pilot.press("tab")
            await pilot.pause()
            await self._wait_overlay_phase(app, pilot, phase=PHASE_REVIEW)

            await pilot.press("down")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await self._wait_overlay_phase(app, pilot, phase=PHASE_QUESTIONS)

            await pilot.press("up")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await self._wait_overlay_phase(app, pilot, phase=PHASE_REVIEW)

            await pilot.press("enter")
            await pilot.pause()
            await self._wait_event(runtime.request_finished)
            await pilot.pause()

        self.assertIsInstance(runtime.last_response, dict)
        assert runtime.last_response is not None
        answers = dict(runtime.last_response.get("answers") or {})
        self.assertEqual(answers["confirm_path"]["answers"], ["No"])
        flattened = " ".join(str(item) for item in answers["confirm_path"]["answers"]).lower()
        self.assertNotIn("legacy", flattened)


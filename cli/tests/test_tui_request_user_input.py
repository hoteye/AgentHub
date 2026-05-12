from __future__ import annotations

import asyncio
import json
import threading
import unittest

from cli.agent_cli.app import AgentCliApp, PromptComposer
from cli.agent_cli.models import PromptAttachment, PromptResponse
from cli.agent_cli.runtime_core.request_user_input_contract_runtime import (
    normalize_request_user_input_questions,
)
from cli.agent_cli.ui.request_user_input_modal import RequestUserInputOverlay
from cli.agent_cli.ui.request_user_input_state_runtime import OTHER_OPTION_VALUE, PHASE_REVIEW


class _RequestUserInputRuntime:
    class _Agent:
        @staticmethod
        def provider_status() -> dict[str, str]:
            return {
                "provider_name": "test",
                "provider_model": "test-model",
                "provider_ready": "true",
            }

    def __init__(self, *, include_second_question: bool = False) -> None:
        self.agent = self._Agent()
        self.activity_callback = None
        self.turn_event_callback = None
        self.request_user_input_handler = None
        self.include_second_question = bool(include_second_question)

        self.last_prompt: str | None = None
        self.last_attachments: list[PromptAttachment] = []
        self.last_user_input_payload: dict[str, object] | None = None
        self.last_user_input_response: dict[str, object] | None = None

        self.handler_callable_seen = threading.Event()
        self.request_started = threading.Event()
        self.request_finished = threading.Event()

    def slash_command_matches(self, query: str) -> list[dict[str, str]]:
        _ = query
        return []

    def slash_command_completion(self, query: str) -> str | None:
        _ = query
        return None

    def handle_prompt(self, text: str, *, attachments: list[PromptAttachment] | None = None) -> PromptResponse:
        self.last_prompt = text
        self.last_attachments = list(attachments or [])
        handler = getattr(self, "request_user_input_handler", None)
        if not callable(handler):
            return PromptResponse(
                user_text=text,
                assistant_text="request_user_input handler missing",
                attachments=list(attachments or []),
                status=self.agent.provider_status(),
                handled_as_command=False,
            )
        self.handler_callable_seen.set()
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
        self.last_user_input_payload = payload
        self.request_started.set()
        response = handler(payload)
        self.last_user_input_response = dict(response) if isinstance(response, dict) else None
        self.request_finished.set()
        assistant_text = json.dumps(self.last_user_input_response, ensure_ascii=False)
        if self.last_user_input_response is None:
            assistant_text = "request_user_input cancelled"
        return PromptResponse(
            user_text=text,
            assistant_text=assistant_text,
            attachments=list(attachments or []),
            status=self.agent.provider_status(),
            handled_as_command=False,
        )

    def interrupt_active_run(self) -> dict[str, object]:
        return {"ok": False, "interrupted": False}


class TuiRequestUserInputSmokeTest(unittest.IsolatedAsyncioTestCase):
    EVENT_TIMEOUT_SECONDS = 8.0
    OVERLAY_TIMEOUT_SECONDS = 8.0

    async def _wait_event(
        self,
        event: threading.Event,
        *,
        timeout: float | None = None,
        label: str = "event",
    ) -> None:
        wait_timeout = timeout if timeout is not None else self.EVENT_TIMEOUT_SECONDS
        deadline = asyncio.get_running_loop().time() + wait_timeout
        while True:
            if event.is_set():
                return
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                self.fail(f"{label} not observed within {wait_timeout:.1f}s")
            await asyncio.to_thread(event.wait, min(0.2, max(remaining, 0.01)))

    def _find_overlay(self, app: AgentCliApp) -> RequestUserInputOverlay | None:
        mounted = getattr(app, "_request_user_input_overlay", None)
        if isinstance(mounted, RequestUserInputOverlay):
            return mounted
        try:
            queried = app.query_one(f"#{RequestUserInputOverlay.ROOT_ID}", RequestUserInputOverlay)
            if isinstance(queried, RequestUserInputOverlay):
                return queried
        except Exception:
            pass
        try:
            overlays = list(app.query(RequestUserInputOverlay))
            if overlays:
                return overlays[0]
        except Exception:
            pass
        return None

    async def _wait_overlay_active(
        self,
        app: AgentCliApp,
        pilot,
        *,
        timeout: float | None = None,
    ) -> RequestUserInputOverlay:
        wait_timeout = timeout if timeout is not None else self.OVERLAY_TIMEOUT_SECONDS
        deadline = asyncio.get_running_loop().time() + wait_timeout
        while True:
            overlay = self._find_overlay(app)
            if isinstance(overlay, RequestUserInputOverlay) and overlay.is_active:
                overlay.focus()
                await pilot.pause()
                return overlay
            if asyncio.get_running_loop().time() >= deadline:
                self.fail("request_user_input overlay did not become active in time")
            await pilot.pause()

    async def _wait_overlay_phase_review(self, app: AgentCliApp, pilot, *, timeout: float = 8.0) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            overlay = self._find_overlay(app)
            state = getattr(overlay, "_state", None) if overlay is not None else None
            if overlay is not None and overlay.is_active and getattr(state, "phase", None) == PHASE_REVIEW:
                return
            if asyncio.get_running_loop().time() >= deadline:
                self.fail("request_user_input overlay did not enter review phase in time")
            await pilot.pause()

    async def _move_cursor_to_other_option(self, app: AgentCliApp, pilot, *, timeout: float = 4.0) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        fallback_steps = 2
        while True:
            overlay = self._find_overlay(app)
            state = getattr(overlay, "_state", None) if overlay is not None else None
            if overlay is not None and overlay.is_active and state is not None:
                question = state.spec.questions[state.question_index]
                options = question.options
                target_index = None
                for index, option in enumerate(options):
                    if option.value == OTHER_OPTION_VALUE or str(option.label).strip().lower() == "other":
                        target_index = index
                        break
                if target_index is None and options:
                    target_index = len(options) - 1
                if target_index is not None and state.cursor_index == target_index:
                    return
                if target_index is not None and options:
                    steps = (target_index - state.cursor_index) % len(options)
                    if steps == 0:
                        return
                    await pilot.press("down")
                    await pilot.pause()
                    continue
            if asyncio.get_running_loop().time() >= deadline:
                for _ in range(fallback_steps):
                    await pilot.press("down")
                    await pilot.pause()
                return
            await pilot.press("down")
            await pilot.pause()

    async def _submit_prompt(self, app: AgentCliApp, pilot, text: str) -> None:
        app._set_prompt_text(text)
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

    async def test_request_user_input_single_choice_round_trip(self) -> None:
        runtime = _RequestUserInputRuntime()
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            await self._submit_prompt(app, pilot, "exercise request_user_input")
            await self._wait_event(runtime.request_started, label="request_started")
            await self._wait_overlay_active(app, pilot)
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await self._wait_event(runtime.request_finished, label="request_finished")
            await app._wait_for_runtime_idle()

            response = runtime.last_user_input_response
            self.assertIsInstance(response, dict, "request_user_input should return a structured response")
            answers = dict((response or {}).get("answers") or {})
            self.assertTrue(answers, "answers should not be empty after submit")
            self.assertEqual(set(answers.keys()), {"confirm_path"})
            self.assertIsInstance(answers["confirm_path"], dict)
            self.assertIsInstance(answers["confirm_path"].get("answers"), list)
            composer = app.query_one("#prompt_composer", PromptComposer)
            self.assertIs(app.focused, composer)

    async def test_request_user_input_cancel_round_trip(self) -> None:
        runtime = _RequestUserInputRuntime()
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            await self._submit_prompt(app, pilot, "exercise request_user_input cancel")
            await self._wait_event(runtime.request_started, label="request_started")
            await self._wait_overlay_active(app, pilot)
            await pilot.press("escape")
            await pilot.pause()
            await self._wait_event(runtime.request_finished, label="request_finished")
            await app._wait_for_runtime_idle()

            self.assertIsNone(runtime.last_user_input_response)
            transcript = app.query_one("#main_log").text.lower()
            self.assertIn("request_user_input", transcript)

    async def test_request_user_input_other_text_round_trip(self) -> None:
        runtime = _RequestUserInputRuntime(include_second_question=True)
        app = AgentCliApp(runtime=runtime)

        async with app.run_test() as pilot:
            await pilot.pause()
            await self._submit_prompt(app, pilot, "exercise request_user_input other")
            await self._wait_event(runtime.request_started, label="request_started")
            await self._wait_overlay_active(app, pilot)
            await self._move_cursor_to_other_option(app, pilot)
            await pilot.press("enter")
            await pilot.pause()
            for key in "custom path":
                if key == " ":
                    await pilot.press("space")
                else:
                    await pilot.press(key)
            await pilot.pause()
            await pilot.press("tab")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await self._wait_overlay_phase_review(app, pilot)
            await pilot.press("enter")
            await pilot.pause()
            await self._wait_event(runtime.request_finished, label="request_finished")
            await app._wait_for_runtime_idle()

            response = runtime.last_user_input_response
            self.assertIsInstance(response, dict, "request_user_input should return structured answers")
            answers = dict((response or {}).get("answers") or {})
            self.assertIn("confirm_path", answers)
            self.assertIsInstance(answers["confirm_path"], dict)
            self.assertIsInstance(answers["confirm_path"].get("answers"), list)
            serialized = json.dumps(answers["confirm_path"]["answers"], ensure_ascii=False).lower()
            self.assertIn("custom", serialized)

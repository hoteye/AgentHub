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


def _presenter_available() -> bool:
    try:
        from cli.agent_cli.ui.request_user_input_modal import present_request_user_input
    except Exception:
        return False
    return callable(present_request_user_input)


class _OverlayFocusGuardRuntime:
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
        self.prompts: list[str] = []
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
        del attachments
        self.prompts.append(text)
        if len(self.prompts) > 1:
            return PromptResponse(
                user_text=text,
                assistant_text=f"echo:{text}",
                status=self.agent.provider_status(),
                handled_as_command=False,
            )

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
        payload = {"questions": normalize_request_user_input_questions(questions)}
        handler = getattr(self, "request_user_input_handler", None)
        response = None
        if callable(handler):
            self.request_started.set()
            response = handler(payload)
            self.request_finished.set()
        self.last_response = dict(response) if isinstance(response, dict) else None
        assistant_text = json.dumps(self.last_response, ensure_ascii=False)
        if self.last_response is None:
            assistant_text = "request_user_input cancelled"
        return PromptResponse(
            user_text=text,
            assistant_text=assistant_text,
            status=self.agent.provider_status(),
            handled_as_command=False,
        )


class RequestUserInputOverlayFocusGuardTest(unittest.IsolatedAsyncioTestCase):
    async def _wait_event(self, event: threading.Event, *, timeout: float = 5.0) -> None:
        await asyncio.wait_for(asyncio.to_thread(event.wait, timeout), timeout=timeout + 0.2)

    async def _wait_overlay_active(self, app: AgentCliApp, pilot, *, timeout: float = 5.0) -> RequestUserInputOverlay:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            try:
                overlay = app.query_one(f"#{RequestUserInputOverlay.ROOT_ID}", RequestUserInputOverlay)
            except Exception:
                overlay = None
            if isinstance(overlay, RequestUserInputOverlay) and overlay.is_active:
                return overlay
            if asyncio.get_running_loop().time() >= deadline:
                self.fail("request_user_input overlay did not become active in time")
            await pilot.pause()

    async def _submit_prompt(self, app: AgentCliApp, pilot, text: str) -> None:
        app._set_prompt_text(text)
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

    async def test_overlay_active_keeps_focus_and_prevents_composer_input(self) -> None:
        if not _presenter_available():
            self.skipTest("request_user_input presenter not available")

        runtime = _OverlayFocusGuardRuntime()
        app = AgentCliApp(runtime=runtime)
        app._request_user_input_modal_presenter = None

        async with app.run_test() as pilot:
            await pilot.pause()
            await self._submit_prompt(app, pilot, "focus guard cancel path")
            await self._wait_event(runtime.request_started)
            overlay = await self._wait_overlay_active(app, pilot)
            composer = app.query_one("#prompt_composer", PromptComposer)
            overlay.focus()
            await pilot.pause()

            self.assertIs(app.focused, overlay)
            self.assertIsNot(app.focused, composer)
            original_text = composer.text

            await pilot.press("a")
            await pilot.press("b")
            await pilot.press("c")
            await pilot.pause()

            self.assertIs(app.focused, overlay)
            self.assertEqual(composer.text, original_text)

            await pilot.press("escape")
            await pilot.pause()
            await self._wait_event(runtime.request_finished)
            await asyncio.wait_for(app._wait_for_runtime_idle(), timeout=5.0)

            self.assertIs(app.focused, composer)
            self.assertIsNone(runtime.last_response)

            await self._submit_prompt(app, pilot, "after cancel still works")
            await asyncio.wait_for(app._wait_for_runtime_idle(), timeout=5.0)

        self.assertGreaterEqual(len(runtime.prompts), 2)
        self.assertEqual(runtime.prompts[-1], "after cancel still works")

    async def test_overlay_submit_then_focus_returns_to_composer(self) -> None:
        if not _presenter_available():
            self.skipTest("request_user_input presenter not available")

        runtime = _OverlayFocusGuardRuntime()
        app = AgentCliApp(runtime=runtime)
        app._request_user_input_modal_presenter = None

        async with app.run_test() as pilot:
            await pilot.pause()
            await self._submit_prompt(app, pilot, "focus guard submit path")
            await self._wait_event(runtime.request_started)
            overlay = await self._wait_overlay_active(app, pilot)
            composer = app.query_one("#prompt_composer", PromptComposer)
            overlay.focus()
            await pilot.pause()

            self.assertIs(app.focused, overlay)
            self.assertIsNot(app.focused, composer)

            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await self._wait_event(runtime.request_finished)
            await asyncio.wait_for(app._wait_for_runtime_idle(), timeout=5.0)

            self.assertIs(app.focused, composer)
            self.assertIsInstance(runtime.last_response, dict)
            assert runtime.last_response is not None
            self.assertEqual(runtime.last_response["answers"]["confirm_path"]["answers"], ["Yes (Recommended)"])

            await self._submit_prompt(app, pilot, "after submit still works")
            await asyncio.wait_for(app._wait_for_runtime_idle(), timeout=5.0)

        self.assertGreaterEqual(len(runtime.prompts), 2)
        self.assertEqual(runtime.prompts[-1], "after submit still works")

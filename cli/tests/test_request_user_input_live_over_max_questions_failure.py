from __future__ import annotations

import asyncio
import threading
import unittest
from unittest.mock import patch

from cli.agent_cli.app import AgentCliApp, PromptComposer
from cli.agent_cli.models import PromptAttachment, PromptResponse
from cli.agent_cli.runtime_core.request_user_input_contract_runtime import (
    normalize_request_user_input_questions,
)
from cli.agent_cli.ui.request_user_input_modal import RequestUserInputOverlay


def _question(index: int) -> dict[str, object]:
    suffix = str(index + 1)
    return {
        "id": f"q{suffix}",
        "header": f"Question {suffix}",
        "question": f"Choose for q{suffix}",
        "options": [
            {"label": f"Opt{suffix}A", "description": "Path A"},
            {"label": f"Opt{suffix}B", "description": "Path B"},
        ],
    }


def _payload(question_count: int) -> dict[str, object]:
    return {
        "questions": normalize_request_user_input_questions(
            [_question(i) for i in range(question_count)]
        )
    }


class _RuntimeWithPayloadQueue:
    class _Agent:
        @staticmethod
        def provider_status() -> dict[str, str]:
            return {
                "provider_name": "test",
                "provider_model": "test-model",
                "provider_ready": "true",
            }

    def __init__(self, payloads: list[dict[str, object]]) -> None:
        self.agent = self._Agent()
        self.activity_callback = None
        self.turn_event_callback = None
        self.request_user_input_handler = None
        self._payloads = list(payloads)
        self.responses: list[dict[str, object] | None] = []
        self.prompts: list[str] = []
        self.request_started = threading.Event()
        self.request_finished = threading.Event()

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
        if not self._payloads:
            return PromptResponse(
                user_text=text,
                assistant_text=f"echo:{text}",
                status=self.agent.provider_status(),
                handled_as_command=False,
            )

        payload = dict(self._payloads.pop(0))
        handler = getattr(self, "request_user_input_handler", None)
        response = None
        if callable(handler):
            self.request_started.set()
            response = handler(payload)
            self.request_finished.set()
        normalized = dict(response) if isinstance(response, dict) else None
        self.responses.append(normalized)
        assistant_text = "request_user_input completed" if normalized is not None else "request_user_input cancelled"
        return PromptResponse(
            user_text=text,
            assistant_text=assistant_text,
            status=self.agent.provider_status(),
            handled_as_command=False,
        )


class RequestUserInputLiveOverMaxQuestionsFailureTest(unittest.IsolatedAsyncioTestCase):
    async def _submit_prompt(self, app: AgentCliApp, pilot, text: str) -> None:
        app._set_prompt_text(text)
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

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

    async def test_live_module_presenter_over_max_questions_cleans_pending_and_waiting(self) -> None:
        runtime = _RuntimeWithPayloadQueue([_payload(4)])
        app = AgentCliApp(runtime=runtime)
        app._request_user_input_modal_presenter = None
        app._request_user_input_test_responder = None

        observed_pending_during_overlay_activate: list[bool] = []
        from cli.agent_cli.ui import request_user_input_modal
        original_parse = request_user_input_modal.parse_request_user_input_spec

        def _parse_with_pending_probe(payload: dict[str, object]) -> object:
            with app._request_user_input_pending_lock:
                observed_pending_during_overlay_activate.append(app._request_user_input_pending is not None)
            return original_parse(payload)

        async with app.run_test() as pilot:
            await pilot.pause()
            with patch.object(
                request_user_input_modal,
                "parse_request_user_input_spec",
                autospec=True,
                side_effect=_parse_with_pending_probe,
            ):
                await self._submit_prompt(app, pilot, "round 1 over max questions")
                await asyncio.wait_for(app._wait_for_runtime_idle(), timeout=5.0)
                await pilot.pause()

            with app._request_user_input_pending_lock:
                self.assertIsNone(app._request_user_input_pending)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")
            self.assertIs(app.focused, app.query_one("#prompt_composer", PromptComposer))

        self.assertEqual(len(runtime.responses), 1)
        self.assertIsNone(runtime.responses[0])
        self.assertTrue(observed_pending_during_overlay_activate)
        self.assertIn(True, observed_pending_during_overlay_activate)

    async def test_valid_request_still_works_after_over_max_questions_failure(self) -> None:
        runtime = _RuntimeWithPayloadQueue([_payload(4), _payload(1)])
        app = AgentCliApp(runtime=runtime)
        app._request_user_input_modal_presenter = None
        app._request_user_input_test_responder = None

        async with app.run_test() as pilot:
            await pilot.pause()

            await self._submit_prompt(app, pilot, "round 1 over max questions")
            await asyncio.wait_for(app._wait_for_runtime_idle(), timeout=5.0)
            await pilot.pause()
            with app._request_user_input_pending_lock:
                self.assertIsNone(app._request_user_input_pending)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")

            await self._submit_prompt(app, pilot, "round 2 valid request")
            overlay = await self._wait_overlay_active(app, pilot)
            overlay.focus()
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await asyncio.wait_for(app._wait_for_runtime_idle(), timeout=5.0)

            with app._request_user_input_pending_lock:
                self.assertIsNone(app._request_user_input_pending)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")
            self.assertIs(app.focused, app.query_one("#prompt_composer", PromptComposer))

        self.assertEqual(len(runtime.responses), 2)
        self.assertIsNone(runtime.responses[0])
        self.assertIsInstance(runtime.responses[1], dict)
        assert runtime.responses[1] is not None
        self.assertEqual(runtime.responses[1]["answers"]["q1"]["answers"], ["Opt1A"])


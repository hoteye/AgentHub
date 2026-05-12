from __future__ import annotations

import unittest

from cli.agent_cli.app import AgentCliApp, PromptComposer
from cli.agent_cli.models import PromptResponse, ToolEvent


def _valid_payload() -> dict[str, object]:
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


def _invalid_payload_missing_options() -> dict[str, object]:
    return {
        "questions": [
            {
                "id": "confirm_path",
                "header": "Confirm",
                "question": "Proceed?",
            }
        ]
    }


def _invalid_payload_empty_options() -> dict[str, object]:
    return {
        "questions": [
            {
                "id": "confirm_path",
                "header": "Confirm",
                "question": "Proceed?",
                "options": [],
            }
        ]
    }


class _SequencedRequestUserInputRuntime:
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
        self._payloads = [dict(item) for item in payloads]
        self._call_index = 0
        self.successful_responses: list[dict[str, object]] = []

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
        if not self._payloads:
            raise RuntimeError("test runtime requires at least one payload")
        payload = self._payloads[min(self._call_index, len(self._payloads) - 1)]
        self._call_index += 1
        handler = getattr(self, "request_user_input_handler", None)
        response = handler(dict(payload)) if callable(handler) else None
        normalized = dict(response) if isinstance(response, dict) else None
        if normalized is not None:
            self.successful_responses.append(normalized)
        event = ToolEvent(
            name="request_user_input",
            ok=isinstance(response, dict),
            summary="request_user_input completed" if isinstance(response, dict) else "request_user_input cancelled",
            payload={"questions": list(payload.get("questions") or []), "response": dict(response or {})},
        )
        return PromptResponse(
            user_text=text,
            assistant_text="request completed" if isinstance(response, dict) else "request cancelled",
            tool_events=[event],
            status=self.agent.provider_status(),
            handled_as_command=True,
        )


class RequestUserInputInvalidPayloadRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def _run_single_invalid_payload_case(self, payload: dict[str, object]) -> None:
        runtime = _SequencedRequestUserInputRuntime([payload])
        app = AgentCliApp(runtime=runtime)

        def _presenter(*, payload, on_submit, on_cancel) -> bool:
            del payload, on_cancel
            on_submit({"answers": {"confirm_path": "Yes (Recommended)"}})
            return True

        app._request_user_input_modal_presenter = _presenter

        async with app.run_test() as pilot:
            await pilot.pause()
            await app._enqueue_runtime_request("trigger invalid request_user_input", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

            with app._request_user_input_pending_lock:
                self.assertIsNone(app._request_user_input_pending)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")
            self.assertIs(app.focused, app.query_one("#prompt_composer", PromptComposer))
            transcript = app.query_one("#main_log").text
            self.assertIn("Execution failed:", transcript)
            self.assertTrue(
                (
                    "request_user_input requires non-empty options" in transcript
                    or "invalid question payload" in transcript
                ),
                "transcript should carry malformed payload diagnostics",
            )

        self.assertEqual(runtime.successful_responses, [])

    async def test_malformed_payload_rejected_without_leaking_pending_or_waiting_state(self) -> None:
        for payload in (_invalid_payload_missing_options(), _invalid_payload_empty_options()):
            with self.subTest(payload=payload):
                await self._run_single_invalid_payload_case(payload)

    async def test_valid_request_still_works_after_invalid_request(self) -> None:
        runtime = _SequencedRequestUserInputRuntime(
            [_invalid_payload_missing_options(), _valid_payload()],
        )
        app = AgentCliApp(runtime=runtime)

        def _presenter(*, payload, on_submit, on_cancel) -> bool:
            del payload, on_cancel
            on_submit({"answers": {"confirm_path": "Yes (Recommended)"}})
            return True

        app._request_user_input_modal_presenter = _presenter

        async with app.run_test() as pilot:
            await pilot.pause()

            await app._enqueue_runtime_request("round 1 invalid request_user_input", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()
            with app._request_user_input_pending_lock:
                self.assertIsNone(app._request_user_input_pending)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")

            await app._enqueue_runtime_request("round 2 valid request_user_input", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()
            with app._request_user_input_pending_lock:
                self.assertIsNone(app._request_user_input_pending)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")
            self.assertIs(app.focused, app.query_one("#prompt_composer", PromptComposer))

        self.assertEqual(len(runtime.successful_responses), 1)
        self.assertEqual(
            runtime.successful_responses[0]["answers"]["confirm_path"]["answers"],
            ["Yes (Recommended)"],
        )

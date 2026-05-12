from __future__ import annotations

import unittest

from cli.agent_cli.app import AgentCliApp, PromptComposer
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
        self.round_index = 0
        self.responses: list[dict[str, object] | None] = []

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

    def _payload_for_round(self, round_index: int) -> dict[str, object]:
        if round_index == 1:
            return {
                "questions": [
                    {
                        "id": "delivery",
                        "header": "Deliver",
                        "question": "Choose output mode",
                        "options": [
                            {"label": "Patch", "description": "Patch only."},
                            {"label": "Patch + notes", "description": "Patch with notes."},
                            {"label": "Custom output mode", "description": "Custom output mode."},
                        ],
                    }
                ]
            }
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

    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        payload = self._payload_for_round(self.round_index)
        self.round_index += 1
        handler = getattr(self, "request_user_input_handler", None)
        response = handler(payload) if callable(handler) else None
        normalized = dict(response) if isinstance(response, dict) else None
        self.responses.append(normalized)
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


class RequestUserInputSequentialRoundTripTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _assert_round_clean(app: AgentCliApp) -> None:
        with app._request_user_input_pending_lock:
            assert app._request_user_input_pending is None
        assert app.status_data.get("request_user_input_waiting") == "false"
        composer = app.query_one("#prompt_composer", PromptComposer)
        assert app.focused is composer

    async def test_cancel_then_submit_round_trips_are_isolated(self) -> None:
        runtime = _BaseRuntime()
        app = AgentCliApp(runtime=runtime)
        presenter_calls: list[str] = []

        def _presenter(*, payload, on_submit, on_cancel) -> bool:
            del payload
            call_idx = len(presenter_calls)
            presenter_calls.append(f"round-{call_idx + 1}")
            if call_idx == 0:
                on_cancel()
            else:
                on_submit({"answers": {"delivery": "Patch"}})
            return True

        app._request_user_input_modal_presenter = _presenter

        async with app.run_test() as pilot:
            await pilot.pause()
            await app._enqueue_runtime_request("round1 cancel", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()
            self._assert_round_clean(app)

            await app._enqueue_runtime_request("round2 submit", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()
            self._assert_round_clean(app)

        self.assertEqual(presenter_calls, ["round-1", "round-2"])
        self.assertEqual(len(runtime.responses), 2)
        self.assertIsNone(runtime.responses[0])
        self.assertIsNotNone(runtime.responses[1])
        assert runtime.responses[1] is not None
        self.assertEqual(runtime.responses[1]["answers"]["delivery"]["answers"], ["Patch"])

    async def test_submit_then_other_submit_keeps_second_round_independent(self) -> None:
        runtime = _BaseRuntime()
        app = AgentCliApp(runtime=runtime)
        presenter_calls: list[str] = []

        def _presenter(*, payload, on_submit, on_cancel) -> bool:
            del payload, on_cancel
            call_idx = len(presenter_calls)
            presenter_calls.append(f"round-{call_idx + 1}")
            if call_idx == 0:
                on_submit({"answers": {"confirm_path": "No"}})
            else:
                on_submit({"answers": {"delivery": "custom delivery"}})
            return True

        app._request_user_input_modal_presenter = _presenter

        async with app.run_test() as pilot:
            await pilot.pause()
            await app._enqueue_runtime_request("round1 submit", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()
            self._assert_round_clean(app)

            await app._enqueue_runtime_request("round2 other", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()
            self._assert_round_clean(app)

        self.assertEqual(presenter_calls, ["round-1", "round-2"])
        self.assertEqual(len(runtime.responses), 2)
        self.assertIsNotNone(runtime.responses[0])
        self.assertIsNotNone(runtime.responses[1])
        assert runtime.responses[0] is not None
        assert runtime.responses[1] is not None
        self.assertEqual(runtime.responses[0]["answers"]["confirm_path"]["answers"], ["No"])
        self.assertEqual(runtime.responses[1]["answers"]["delivery"]["answers"], ["custom delivery"])

from __future__ import annotations

import unittest

from cli.agent_cli.app import AgentCliApp, PromptComposer
from cli.agent_cli.models import PromptResponse, ToolEvent
from cli.agent_cli.ui.request_user_input_state_runtime import parse_request_user_input_spec


def _question(index: int) -> dict[str, object]:
    suffix = str(index + 1)
    return {
        "id": f"q{suffix}",
        "header": f"Question {suffix}",
        "question": f"Pick option for q{suffix}",
        "options": [
            {"label": f"Opt{suffix}A", "description": "A path"},
            {"label": f"Opt{suffix}B", "description": "B path"},
        ],
    }


class _RuntimeWithFixedPayload:
    class _Agent:
        @staticmethod
        def provider_status() -> dict[str, str]:
            return {
                "provider_name": "test",
                "provider_model": "test-model",
                "provider_ready": "true",
            }

    def __init__(self, payload: dict[str, object]) -> None:
        self.agent = self._Agent()
        self.activity_callback = None
        self.turn_event_callback = None
        self.payload = dict(payload)
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

    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        handler = getattr(self, "request_user_input_handler", None)
        response = handler(dict(self.payload)) if callable(handler) else None
        normalized = dict(response) if isinstance(response, dict) else None
        self.responses.append(normalized)
        event = ToolEvent(
            name="request_user_input",
            ok=bool(isinstance(response, dict)),
            summary="request_user_input completed" if isinstance(response, dict) else "request_user_input cancelled",
            payload={
                "questions": list(self.payload.get("questions") or []),
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


class RequestUserInputMaxQuestionsGuardTest(unittest.IsolatedAsyncioTestCase):
    def test_parse_spec_rejects_payload_over_tui_max_questions(self) -> None:
        payload = {"questions": [_question(0), _question(1), _question(2), _question(3)]}
        with self.assertRaisesRegex(ValueError, "at most 3 questions"):
            parse_request_user_input_spec(payload)

    async def test_three_question_boundary_round_trip_still_submits(self) -> None:
        payload = {"questions": [_question(0), _question(1), _question(2)]}
        runtime = _RuntimeWithFixedPayload(payload)
        app = AgentCliApp(runtime=runtime)

        def _presenter(*, payload, on_submit, on_cancel) -> bool:
            del payload, on_cancel
            on_submit(
                {
                    "answers": {
                        "q1": "Opt1A",
                        "q2": "Opt2B",
                        "q3": "Opt3A",
                    }
                }
            )
            return True

        app._request_user_input_modal_presenter = _presenter

        async with app.run_test() as pilot:
            await pilot.pause()
            await app._enqueue_runtime_request("exercise request_user_input with 3 questions", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()
            with app._request_user_input_pending_lock:
                self.assertIsNone(app._request_user_input_pending)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")
            self.assertIs(app.focused, app.query_one("#prompt_composer", PromptComposer))

        self.assertEqual(len(runtime.responses), 1)
        self.assertIsNotNone(runtime.responses[0])
        assert runtime.responses[0] is not None
        self.assertEqual(runtime.responses[0]["answers"]["q1"]["answers"], ["Opt1A"])
        self.assertEqual(runtime.responses[0]["answers"]["q2"]["answers"], ["Opt2B"])
        self.assertEqual(runtime.responses[0]["answers"]["q3"]["answers"], ["Opt3A"])


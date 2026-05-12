from __future__ import annotations

import unittest

from cli.agent_cli.app import AgentCliApp, PromptComposer
from cli.agent_cli.models import PromptResponse, ToolEvent
from cli.agent_cli.runtime_core.request_user_input_contract_runtime import (
    normalize_request_user_input_questions,
)
from cli.agent_cli.ui.request_user_input_state_runtime import parse_request_user_input_spec


def _payload_with_non_string_fields() -> dict[str, object]:
    return {
        "questions": [
            {
                "id": 123,
                "header": True,
                "question": [1, 2, 3],
                "options": [
                    {
                        "label": 7,
                        "description": 8,
                        "value": {"should": "be ignored"},
                    }
                ],
            }
        ]
    }


def _invalid_payload_with_non_string_label() -> dict[str, object]:
    return {
        "questions": [
            {
                "id": 456,
                "header": "Confirm",
                "question": "Proceed?",
                "options": [
                    {
                        "label": 0,
                        "description": "Number label is falsy and should be rejected.",
                    }
                ],
            }
        ]
    }


def _valid_payload_for_recovery() -> dict[str, object]:
    return {
        "questions": [
            {
                "id": 456,
                "header": "Confirm",
                "question": "Proceed?",
                "options": [
                    {"label": "Yes", "description": "Continue."},
                    {"label": "No", "description": "Stop."},
                ],
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


def test_normalize_questions_stringifies_non_string_fields_and_ignores_option_value_field() -> None:
    normalized = normalize_request_user_input_questions(_payload_with_non_string_fields()["questions"])
    assert len(normalized) == 1
    question = normalized[0]
    assert question["id"] == "123"
    assert question["header"] == "True"
    assert question["question"] == "[1, 2, 3]"
    assert question["is_other"] is True
    assert question["options"] == [{"label": "7", "description": "8"}]
    assert "value" not in question["options"][0]


def test_parse_spec_uses_normalized_label_as_option_value_with_non_string_input() -> None:
    spec = parse_request_user_input_spec(_payload_with_non_string_fields())
    assert len(spec.questions) == 1
    question = spec.questions[0]
    assert question.question_id == "123"
    assert question.options[0].label == "7"
    assert question.options[0].value == "7"
    assert question.options[0].description == "8"
    assert question.options[-1].is_other is True


class RequestUserInputNonStringFieldRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_non_string_option_field_rejected_and_next_valid_request_recovers(self) -> None:
        runtime = _SequencedRequestUserInputRuntime(
            [
                _invalid_payload_with_non_string_label(),
                _valid_payload_for_recovery(),
            ]
        )
        app = AgentCliApp(runtime=runtime)

        def _presenter(*, payload, on_submit, on_cancel) -> bool:
            del payload, on_cancel
            on_submit({"answers": {"456": "Yes"}})
            return True

        app._request_user_input_modal_presenter = _presenter

        async with app.run_test() as pilot:
            await pilot.pause()

            await app._enqueue_runtime_request("round 1 invalid non-string request_user_input", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()
            with app._request_user_input_pending_lock:
                self.assertIsNone(app._request_user_input_pending)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")
            self.assertIs(app.focused, app.query_one("#prompt_composer", PromptComposer))
            transcript = app.query_one("#main_log").text
            self.assertIn("Execution failed:", transcript)
            self.assertIn("request_user_input requires non-empty options", transcript)

            await app._enqueue_runtime_request("round 2 valid request_user_input", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()
            with app._request_user_input_pending_lock:
                self.assertIsNone(app._request_user_input_pending)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")
            self.assertIs(app.focused, app.query_one("#prompt_composer", PromptComposer))

        self.assertEqual(len(runtime.successful_responses), 1)
        self.assertEqual(runtime.successful_responses[0]["answers"]["456"]["answers"], ["Yes"])

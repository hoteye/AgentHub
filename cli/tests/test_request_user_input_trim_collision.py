from __future__ import annotations

import unittest

from cli.agent_cli.app import AgentCliApp, PromptComposer
from cli.agent_cli.models import PromptResponse, ToolEvent
from cli.agent_cli.ui.request_user_input_state_runtime import (
    OTHER_OPTION_VALUE,
    option_index_for_value,
    parse_request_user_input_spec,
    request_user_input_initial_state,
    response_payload,
    with_cursor_delta,
    with_move_previous,
    with_selected_current_option,
)


def _trimmed_duplicate_id_payload() -> dict[str, object]:
    return {
        "questions": [
            {
                "id": "deploy",
                "header": "Plan",
                "question": "How should we proceed?",
                "options": [
                    {"label": "Yes", "description": "Proceed."},
                    {"label": "No", "description": "Stop."},
                ],
            },
            {
                "id": "  deploy  ",
                "header": "Execution",
                "question": "What action should be taken?",
                "options": [
                    {"label": "Patch", "description": "Patch only."},
                    {"label": "Rollback", "description": "Rollback changes."},
                ],
            },
        ]
    }


def _trimmed_duplicate_value_payload() -> dict[str, object]:
    return {
        "questions": [
            {
                "id": "strategy",
                "header": "Strategy",
                "question": "Select rollout strategy",
                "options": [
                    {"label": "Fast", "description": "Immediate rollout."},
                    {"label": "  Fast  ", "description": "Immediate rollout with diagnostics."},
                    {"label": "Safe", "description": "Phased rollout."},
                ],
            }
        ]
    }


def _valid_payload_for_followup() -> dict[str, object]:
    return {
        "questions": [
            {
                "id": "confirm_path",
                "header": "Confirm",
                "question": "Proceed?",
                "options": [
                    {"label": "Yes", "description": "Continue."},
                    {"label": "No", "description": "Stop."},
                ],
            }
        ]
    }


class _SequencedTrimCollisionRuntime:
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
        payload = self._payloads[min(self._call_index, len(self._payloads) - 1)]
        self._call_index += 1
        handler = getattr(self, "request_user_input_handler", None)
        response = handler(dict(payload)) if callable(handler) else None
        normalized = dict(response) if isinstance(response, dict) else None
        self.responses.append(normalized)
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


class RequestUserInputTrimCollisionTest(unittest.IsolatedAsyncioTestCase):
    def test_trimmed_question_id_collision_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate question id"):
            parse_request_user_input_spec(_trimmed_duplicate_id_payload())

    def test_trimmed_option_label_collision_keeps_duplicate_values_and_backfill_picks_first_match(self) -> None:
        spec = parse_request_user_input_spec(_trimmed_duplicate_value_payload())
        question = spec.questions[0]
        self.assertEqual(
            [option.value for option in question.options],
            ["Fast", "Fast", "Safe", OTHER_OPTION_VALUE],
        )

        state = request_user_input_initial_state(spec)
        state = with_cursor_delta(state, 1)
        state = with_selected_current_option(state)
        self.assertEqual(
            response_payload(state),
            {"answers": {"strategy": {"answers": ["Fast"]}}},
        )

        back_to_questions = with_move_previous(state)
        self.assertEqual(option_index_for_value(question, "Fast"), 0)
        self.assertEqual(back_to_questions.cursor_index, 0)

    async def test_live_runtime_with_trimmed_id_collision_fails_fast_and_followup_request_still_works(self) -> None:
        runtime = _SequencedTrimCollisionRuntime([_trimmed_duplicate_id_payload(), _valid_payload_for_followup()])
        app = AgentCliApp(runtime=runtime)
        submitted_answers = [{"confirm_path": "No"}]

        def _presenter(*, payload, on_submit, on_cancel) -> bool:
            del payload, on_cancel
            on_submit({"answers": submitted_answers.pop(0)})
            return True

        app._request_user_input_modal_presenter = _presenter

        async with app.run_test() as pilot:
            await pilot.pause()

            await app._enqueue_runtime_request("round 1 trim-collision", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()
            with app._request_user_input_pending_lock:
                self.assertIsNone(app._request_user_input_pending)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")
            self.assertIn("duplicate question id", app.query_one("#main_log").text)

            await app._enqueue_runtime_request("round 2 valid followup", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()
            with app._request_user_input_pending_lock:
                self.assertIsNone(app._request_user_input_pending)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")
            self.assertIs(app.focused, app.query_one("#prompt_composer", PromptComposer))

        self.assertEqual(len(runtime.responses), 1)
        assert runtime.responses[0] is not None
        self.assertEqual(runtime.responses[0]["answers"]["confirm_path"]["answers"], ["No"])

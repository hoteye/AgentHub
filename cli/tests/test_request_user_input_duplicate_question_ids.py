from __future__ import annotations

import unittest

from cli.agent_cli.app import AgentCliApp, PromptComposer
from cli.agent_cli.models import PromptResponse, ToolEvent
from cli.agent_cli.ui.request_user_input_state_runtime import (
    parse_request_user_input_spec,
)


def _duplicate_id_payload() -> dict[str, object]:
    return {
        "questions": [
            {
                "id": "dup",
                "header": "Confirm",
                "question": "First answer?",
                "options": [
                    {"label": "Yes", "description": "Proceed."},
                    {"label": "No", "description": "Stop."},
                ],
            },
            {
                "id": "dup",
                "header": "Delivery",
                "question": "Second answer?",
                "options": [
                    {"label": "Patch", "description": "Patch only."},
                    {"label": "Patch + notes", "description": "Patch with notes."},
                ],
            },
        ]
    }


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


class _SequencedDuplicateIdRuntime:
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
        if not self._payloads:
            raise RuntimeError("test runtime requires at least one payload")
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


class RequestUserInputDuplicateQuestionIdsTest(unittest.IsolatedAsyncioTestCase):
    def test_state_parser_rejects_duplicate_ids_after_normalization(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate question id"):
            parse_request_user_input_spec(_duplicate_id_payload())

    async def test_live_runtime_duplicate_ids_fail_fast_and_follow_up_request_still_works(self) -> None:
        runtime = _SequencedDuplicateIdRuntime([_duplicate_id_payload(), _valid_payload()])
        app = AgentCliApp(runtime=runtime)
        submitted_answers = [{"confirm_path": "No"}]

        def _presenter(*, payload, on_submit, on_cancel) -> bool:
            del payload, on_cancel
            on_submit({"answers": submitted_answers.pop(0)})
            return True

        app._request_user_input_modal_presenter = _presenter

        async with app.run_test() as pilot:
            await pilot.pause()

            await app._enqueue_runtime_request("round 1 duplicate ids", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()
            with app._request_user_input_pending_lock:
                self.assertIsNone(app._request_user_input_pending)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")
            self.assertIn("duplicate question id", app.query_one("#main_log").text)

            await app._enqueue_runtime_request("round 2 valid", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()
            with app._request_user_input_pending_lock:
                self.assertIsNone(app._request_user_input_pending)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")
            self.assertIs(app.focused, app.query_one("#prompt_composer", PromptComposer))

        self.assertEqual(len(runtime.responses), 1)
        self.assertIsNotNone(runtime.responses[0])
        assert runtime.responses[0] is not None
        self.assertEqual(
            runtime.responses[0]["answers"]["confirm_path"]["answers"],
            ["No"],
        )

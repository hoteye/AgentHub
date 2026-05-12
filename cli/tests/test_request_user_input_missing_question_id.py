from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from cli.agent_cli.app import AgentCliApp, PromptComposer
from cli.agent_cli.models import PromptResponse, ToolEvent
from cli.agent_cli.runtime_core.command_handlers_structured_runtime import (
    handle_request_user_input_command,
)
from cli.agent_cli.runtime_core.request_user_input_contract_runtime import (
    normalize_request_user_input_questions,
)
from cli.agent_cli.ui.request_user_input_state_runtime import parse_request_user_input_spec


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


def _missing_id_payload() -> dict[str, object]:
    return {
        "questions": [
            {
                "header": "Confirm",
                "question": "Proceed?",
                "options": [
                    {"label": "Yes (Recommended)", "description": "Continue."},
                    {"label": "No", "description": "Stop."},
                ],
            }
        ]
    }


def _blank_id_payload() -> dict[str, object]:
    return {
        "questions": [
            {
                "id": "   ",
                "header": "Confirm",
                "question": "Proceed?",
                "options": [
                    {"label": "Yes (Recommended)", "description": "Continue."},
                    {"label": "No", "description": "Stop."},
                ],
            }
        ]
    }


class _SequencedRuntime:
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


class RequestUserInputMissingQuestionIdTest(unittest.IsolatedAsyncioTestCase):
    def test_normalization_and_state_parser_reject_missing_or_blank_id(self) -> None:
        for payload in (_missing_id_payload(), _blank_id_payload()):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ValueError, "invalid question payload"):
                    normalize_request_user_input_questions(payload["questions"])
                with self.assertRaisesRegex(ValueError, "invalid question payload"):
                    parse_request_user_input_spec(payload)

    async def test_live_runtime_invalid_id_does_not_leak_pending_and_valid_followup_still_works(self) -> None:
        runtime = _SequencedRuntime([_missing_id_payload(), _valid_payload()])
        app = AgentCliApp(runtime=runtime)

        def _presenter(*, payload, on_submit, on_cancel) -> bool:
            del payload, on_cancel
            on_submit({"answers": {"confirm_path": "Yes (Recommended)"}})
            return True

        app._request_user_input_modal_presenter = _presenter

        async with app.run_test() as pilot:
            await pilot.pause()

            await app._enqueue_runtime_request("round 1 invalid question id", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()
            with app._request_user_input_pending_lock:
                self.assertIsNone(app._request_user_input_pending)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")
            self.assertIs(app.focused, app.query_one("#prompt_composer", PromptComposer))
            self.assertIn("invalid question payload", app.query_one("#main_log").text)

            await app._enqueue_runtime_request("round 2 valid question id", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()
            with app._request_user_input_pending_lock:
                self.assertIsNone(app._request_user_input_pending)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")

        self.assertEqual(len(runtime.successful_responses), 1)
        self.assertEqual(
            runtime.successful_responses[0]["answers"]["confirm_path"]["answers"],
            ["Yes (Recommended)"],
        )

    def test_command_path_numeric_id_is_stringified_and_response_keys_filtered(self) -> None:
        runtime = SimpleNamespace(
            collaboration_mode="default",
            default_mode_request_user_input=True,
            request_user_input_handler=lambda _payload: {
                "answers": {101: "yes", "unknown_key": "no"},
            },
        )

        result = handle_request_user_input_command(
            runtime,
            arg_text=(
                '{"questions":[{"id":101,"header":"Confirm","question":"Proceed?",'
                '"options":[{"label":"Yes","description":"Continue."}]}]}'
            ),
        )

        response = json.loads(result.assistant_text)
        self.assertEqual(response["answers"], {"101": {"answers": ["yes"]}})
        self.assertEqual(
            result.tool_events[0].payload["response"]["answers"],
            {"101": {"answers": ["yes"]}},
        )

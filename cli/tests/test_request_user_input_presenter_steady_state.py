from __future__ import annotations

import unittest

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.models import PromptResponse, ToolEvent
from cli.agent_cli.ui import request_user_input_modal


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


class _RequestUserInputRuntime(_BaseRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.responses: list[dict[str, object] | None] = []

    def handle_prompt(self, text: str, *, attachments=None) -> PromptResponse:
        del attachments
        payload = {
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
        handler = getattr(self, "request_user_input_handler", None)
        response = handler(payload) if callable(handler) else None
        self.responses.append(dict(response) if isinstance(response, dict) else None)
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


def _payload() -> dict[str, object]:
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


class RequestUserInputPresenterSteadyStateTest(unittest.IsolatedAsyncioTestCase):
    async def test_injected_false_falls_through_to_module_presenter_and_completes(self) -> None:
        runtime = _RequestUserInputRuntime()
        app = AgentCliApp(runtime=runtime)
        injected_calls: list[dict[str, object]] = []
        module_calls: list[dict[str, object]] = []
        original = getattr(request_user_input_modal, "present_request_user_input", None)

        def _injected_presenter(*, payload, on_submit, on_cancel) -> bool:
            injected_calls.append(
                {
                    "payload": payload,
                    "on_submit": on_submit,
                    "on_cancel": on_cancel,
                }
            )
            return False

        def _module_presenter(*, app, payload, on_submit, on_cancel) -> bool:
            del app, payload, on_cancel
            module_calls.append({"submitted": True})
            on_submit({"answers": {"confirm_path": "Yes (Recommended)"}})
            return True

        app._request_user_input_modal_presenter = _injected_presenter
        setattr(request_user_input_modal, "present_request_user_input", _module_presenter)
        try:
            async with app.run_test() as pilot:
                await pilot.pause()
                await app._enqueue_runtime_request("trigger module fallback", [])
                await app._wait_for_runtime_idle()
                await pilot.pause()
        finally:
            if original is None:
                delattr(request_user_input_modal, "present_request_user_input")
            else:
                setattr(request_user_input_modal, "present_request_user_input", original)

        self.assertEqual(len(injected_calls), 1)
        self.assertEqual(len(module_calls), 1)
        self.assertEqual(len(runtime.responses), 1)
        self.assertIsNotNone(runtime.responses[0])
        assert runtime.responses[0] is not None
        self.assertEqual(runtime.responses[0]["answers"]["confirm_path"]["answers"], ["Yes (Recommended)"])
        with app._request_user_input_pending_lock:
            self.assertIsNone(app._request_user_input_pending)
        self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")

    async def test_cancelled_round_does_not_leak_pending_or_callbacks_into_next_round(self) -> None:
        runtime = _RequestUserInputRuntime()
        app = AgentCliApp(runtime=runtime)
        presenter_calls: list[str] = []

        def _stateful_presenter(*, payload, on_submit, on_cancel) -> bool:
            del payload
            call_index = len(presenter_calls)
            presenter_calls.append(f"call-{call_index + 1}")
            if call_index == 0:
                on_cancel()
            else:
                on_submit({"answers": {"confirm_path": "No"}})
            return True

        app._request_user_input_modal_presenter = _stateful_presenter

        async with app.run_test() as pilot:
            await pilot.pause()
            await app._enqueue_runtime_request("first round cancel", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()
            with app._request_user_input_pending_lock:
                self.assertIsNone(app._request_user_input_pending)
            self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")

            await app._enqueue_runtime_request("second round submit", [])
            await app._wait_for_runtime_idle()
            await pilot.pause()

        self.assertEqual(presenter_calls, ["call-1", "call-2"])
        self.assertEqual(len(runtime.responses), 2)
        self.assertIsNone(runtime.responses[0])
        self.assertIsNotNone(runtime.responses[1])
        assert runtime.responses[1] is not None
        self.assertEqual(runtime.responses[1]["answers"]["confirm_path"]["answers"], ["No"])
        with app._request_user_input_pending_lock:
            self.assertIsNone(app._request_user_input_pending)
        self.assertEqual(app.status_data.get("request_user_input_waiting"), "false")

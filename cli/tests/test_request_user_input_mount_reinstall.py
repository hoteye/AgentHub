from __future__ import annotations

import unittest

from cli.agent_cli.app import AgentCliApp
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


class _RequestUserInputRuntime(_BaseRuntime):
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
                    "is_other": True,
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


class RequestUserInputMountReinstallTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _assert_runtime_handler_bound_to_app(runtime: _RequestUserInputRuntime, app: AgentCliApp) -> None:
        handler = getattr(runtime, "request_user_input_handler", None)
        assert callable(handler)
        assert hasattr(handler, "__self__")
        assert hasattr(handler, "__func__")
        assert hasattr(app._handle_request_user_input_from_runtime, "__func__")
        assert hasattr(app._handle_request_user_input_from_runtime, "__self__")
        unittest.TestCase().assertIs(handler.__self__, app)
        unittest.TestCase().assertIs(handler.__func__, app._handle_request_user_input_from_runtime.__func__)

    async def test_handler_reinstalled_after_cleanup_on_next_mount(self) -> None:
        runtime = _RequestUserInputRuntime()
        app_first = AgentCliApp(runtime=runtime)

        def _cancel_presenter(*, payload, on_submit, on_cancel) -> bool:
            del payload, on_submit
            on_cancel()
            return True

        app_first._request_user_input_modal_presenter = _cancel_presenter

        async with app_first.run_test() as pilot:
            await pilot.pause()
            self._assert_runtime_handler_bound_to_app(runtime, app_first)
            await app_first._enqueue_runtime_request("first mount request", [])
            await app_first._wait_for_runtime_idle()
            await pilot.pause()

        self.assertIsNone(getattr(runtime, "request_user_input_handler", None))

        app_second = AgentCliApp(runtime=runtime)
        app_second._request_user_input_modal_presenter = _cancel_presenter

        async with app_second.run_test() as pilot:
            await pilot.pause()
            self._assert_runtime_handler_bound_to_app(runtime, app_second)
            await app_second._enqueue_runtime_request("second mount request", [])
            await app_second._wait_for_runtime_idle()
            await pilot.pause()
            self.assertEqual(app_second.status_data.get("request_user_input_waiting"), "false")

        self.assertIsNone(getattr(runtime, "request_user_input_handler", None))

    async def test_second_mount_round_trip_works_after_first_mount_submit(self) -> None:
        runtime = _RequestUserInputRuntime()
        app_first = AgentCliApp(runtime=runtime)

        def _submit_presenter(*, payload, on_submit, on_cancel) -> bool:
            del payload, on_cancel
            on_submit({"answers": {"confirm_path": "Yes (Recommended)"}})
            return True

        app_first._request_user_input_modal_presenter = _submit_presenter

        async with app_first.run_test() as pilot:
            await pilot.pause()
            await app_first._enqueue_runtime_request("first mount submit", [])
            await app_first._wait_for_runtime_idle()
            await pilot.pause()
            self.assertIsInstance(runtime.responses[-1], dict)
            assert isinstance(runtime.responses[-1], dict)
            self.assertEqual(
                runtime.responses[-1]["answers"]["confirm_path"]["answers"],
                ["Yes (Recommended)"],
            )
            self.assertEqual(app_first.status_data.get("request_user_input_waiting"), "false")

        self.assertIsNone(getattr(runtime, "request_user_input_handler", None))

        app_second = AgentCliApp(runtime=runtime)

        def _cancel_presenter(*, payload, on_submit, on_cancel) -> bool:
            del payload, on_submit
            on_cancel()
            return True

        app_second._request_user_input_modal_presenter = _cancel_presenter

        async with app_second.run_test() as pilot:
            await pilot.pause()
            await app_second._enqueue_runtime_request("second mount cancel", [])
            await app_second._wait_for_runtime_idle()
            await pilot.pause()
            self._assert_runtime_handler_bound_to_app(runtime, app_second)
            self.assertEqual(app_second.status_data.get("request_user_input_waiting"), "false")

        self.assertEqual(len(runtime.responses), 2)
        self.assertIsInstance(runtime.responses[0], dict)
        self.assertIsNone(runtime.responses[1])

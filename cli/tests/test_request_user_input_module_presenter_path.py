from __future__ import annotations

import unittest
from unittest.mock import patch

from cli.agent_cli.app import AgentCliApp, _PendingRequestUserInput
from cli.agent_cli.ui import request_user_input_modal


class _ModulePresenterRuntime:
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


class _FakeOverlay:
    def __init__(self) -> None:
        self.activated_payloads: list[dict[str, object]] = []

    def activate(self, payload: dict[str, object]) -> None:
        self.activated_payloads.append(dict(payload))


class RequestUserInputModulePresenterPathTest(unittest.TestCase):
    def test_real_module_level_presenter_path_is_used_without_injected_presenter(self) -> None:
        app = AgentCliApp(runtime=_ModulePresenterRuntime())
        app._request_user_input_modal_presenter = None
        overlay = _FakeOverlay()

        with patch.object(
            request_user_input_modal,
            "_resolve_request_user_input_overlay",
            autospec=True,
            return_value=overlay,
        ) as resolve_overlay:
            accepted = app._present_request_user_input_modal(_payload())

        self.assertTrue(accepted)
        resolve_overlay.assert_called_once()
        self.assertEqual(len(overlay.activated_payloads), 1)
        self.assertIn("questions", overlay.activated_payloads[0])

    def test_injected_presenter_false_falls_through_to_real_module_presenter(self) -> None:
        app = AgentCliApp(runtime=_ModulePresenterRuntime())
        calls: list[str] = []
        overlay = _FakeOverlay()

        def _injected_presenter(*, payload, on_submit, on_cancel) -> bool:
            del payload, on_submit, on_cancel
            calls.append("injected")
            return False

        app._request_user_input_modal_presenter = _injected_presenter

        with patch.object(
            request_user_input_modal,
            "_resolve_request_user_input_overlay",
            autospec=True,
            return_value=overlay,
        ):
            accepted = app._present_request_user_input_modal(_payload())

        self.assertTrue(accepted)
        self.assertEqual(calls, ["injected"])
        self.assertEqual(len(overlay.activated_payloads), 1)

    def test_module_level_presenter_false_triggers_app_fallback_path(self) -> None:
        app = AgentCliApp(runtime=_ModulePresenterRuntime())
        notices: list[str] = []
        cancel_calls: list[str] = []
        app._request_user_input_modal_presenter = None
        app._request_user_input_test_responder = None
        app._write_system_notice = lambda message: notices.append(message)
        app._on_request_user_input_cancel = lambda: cancel_calls.append("cancel")

        pending = _PendingRequestUserInput(
            payload=dict(_payload()),
            question_ids=("confirm_path",),
        )

        with patch.object(
            request_user_input_modal,
            "present_request_user_input",
            autospec=True,
            return_value=False,
        ) as present:
            app._dispatch_request_user_input_prompt(pending)

        present.assert_called_once()
        self.assertEqual(cancel_calls, ["cancel"])
        self.assertIn("request_user_input cancelled: interactive UI unavailable.", notices)

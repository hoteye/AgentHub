from __future__ import annotations

import unittest

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.ui import request_user_input_modal


class _PresenterPrecedenceRuntime:
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


class RequestUserInputPresenterPrecedenceTest(unittest.TestCase):
    def test_injected_presenter_takes_precedence_over_module_presenter(self) -> None:
        app = AgentCliApp(runtime=_PresenterPrecedenceRuntime())
        original = getattr(request_user_input_modal, "present_request_user_input", None)
        injected_calls: list[dict[str, object]] = []
        module_calls: list[dict[str, object]] = []

        def _injected_presenter(*, payload, on_submit, on_cancel) -> bool:
            injected_calls.append(
                {
                    "payload": payload,
                    "on_submit": on_submit,
                    "on_cancel": on_cancel,
                }
            )
            return True

        def _module_presenter(*, app, payload, on_submit, on_cancel) -> bool:
            module_calls.append(
                {
                    "app": app,
                    "payload": payload,
                    "on_submit": on_submit,
                    "on_cancel": on_cancel,
                }
            )
            return True

        app._request_user_input_modal_presenter = _injected_presenter
        setattr(request_user_input_modal, "present_request_user_input", _module_presenter)
        try:
            accepted = app._present_request_user_input_modal(_payload())
        finally:
            if original is None:
                delattr(request_user_input_modal, "present_request_user_input")
            else:
                setattr(request_user_input_modal, "present_request_user_input", original)

        self.assertTrue(accepted)
        self.assertEqual(len(injected_calls), 1)
        self.assertEqual(len(module_calls), 0)
        self.assertTrue(callable(injected_calls[0]["on_submit"]))
        self.assertTrue(callable(injected_calls[0]["on_cancel"]))

    def test_module_presenter_is_used_when_injected_presenter_returns_false(self) -> None:
        app = AgentCliApp(runtime=_PresenterPrecedenceRuntime())
        original = getattr(request_user_input_modal, "present_request_user_input", None)
        injected_calls: list[dict[str, object]] = []
        module_calls: list[dict[str, object]] = []

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
            module_calls.append(
                {
                    "app": app,
                    "payload": payload,
                    "on_submit": on_submit,
                    "on_cancel": on_cancel,
                }
            )
            return True

        app._request_user_input_modal_presenter = _injected_presenter
        setattr(request_user_input_modal, "present_request_user_input", _module_presenter)
        try:
            accepted = app._present_request_user_input_modal(_payload())
        finally:
            if original is None:
                delattr(request_user_input_modal, "present_request_user_input")
            else:
                setattr(request_user_input_modal, "present_request_user_input", original)

        self.assertTrue(accepted)
        self.assertEqual(len(injected_calls), 1)
        self.assertEqual(len(module_calls), 1)
        self.assertIs(module_calls[0]["app"], app)
        self.assertTrue(callable(module_calls[0]["on_submit"]))
        self.assertTrue(callable(module_calls[0]["on_cancel"]))

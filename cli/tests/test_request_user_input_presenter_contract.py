from __future__ import annotations

import unittest

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.ui import request_user_input_modal


class _PresenterContractRuntime:
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


class RequestUserInputPresenterContractTest(unittest.TestCase):
    def test_injected_presenter_receives_payload_and_callbacks(self) -> None:
        app = AgentCliApp(runtime=_PresenterContractRuntime())
        seen: dict[str, object] = {}

        def _presenter(*, payload, on_submit, on_cancel) -> bool:
            seen["payload"] = payload
            seen["on_submit"] = on_submit
            seen["on_cancel"] = on_cancel
            return True

        app._request_user_input_modal_presenter = _presenter

        accepted = app._present_request_user_input_modal(_payload())
        self.assertTrue(accepted)
        self.assertIsInstance(seen.get("payload"), dict)
        self.assertIn("questions", dict(seen.get("payload") or {}))
        self.assertTrue(callable(seen.get("on_submit")))
        self.assertTrue(callable(seen.get("on_cancel")))

    def test_module_level_presenter_is_used_when_exported(self) -> None:
        app = AgentCliApp(runtime=_PresenterContractRuntime())
        original = getattr(request_user_input_modal, "present_request_user_input", None)
        calls: list[dict[str, object]] = []

        def _module_presenter(*, app, payload, on_submit, on_cancel) -> bool:
            calls.append(
                {
                    "app": app,
                    "payload": payload,
                    "on_submit": on_submit,
                    "on_cancel": on_cancel,
                }
            )
            return True

        setattr(request_user_input_modal, "present_request_user_input", _module_presenter)
        try:
            accepted = app._present_request_user_input_modal(_payload())
        finally:
            if original is None:
                delattr(request_user_input_modal, "present_request_user_input")
            else:
                setattr(request_user_input_modal, "present_request_user_input", original)

        self.assertTrue(accepted)
        self.assertEqual(len(calls), 1)
        self.assertIs(calls[0]["app"], app)
        self.assertIsInstance(calls[0]["payload"], dict)
        self.assertTrue(callable(calls[0]["on_submit"]))
        self.assertTrue(callable(calls[0]["on_cancel"]))

    def test_missing_module_level_presenter_returns_false(self) -> None:
        app = AgentCliApp(runtime=_PresenterContractRuntime())
        app._request_user_input_modal_presenter = None
        original = getattr(request_user_input_modal, "present_request_user_input", None)
        if hasattr(request_user_input_modal, "present_request_user_input"):
            delattr(request_user_input_modal, "present_request_user_input")
        try:
            accepted = app._present_request_user_input_modal(_payload())
        finally:
            if original is not None:
                setattr(request_user_input_modal, "present_request_user_input", original)
        self.assertFalse(accepted)

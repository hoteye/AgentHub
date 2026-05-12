from __future__ import annotations

import unittest
from typing import Any

from textual.app import App, ComposeResult

from cli.agent_cli.ui.request_user_input_modal import RequestUserInputOverlay


def _single_question_payload() -> dict[str, object]:
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


class _OverlayHarnessApp(App[None]):
    def __init__(self) -> None:
        super().__init__()
        self.submissions: list[dict[str, Any]] = []
        self.cancellations = 0
        self.overlay = RequestUserInputOverlay(
            on_submit=self._on_submit,
            on_cancel=self._on_cancel,
        )

    def compose(self) -> ComposeResult:
        yield self.overlay

    def _on_submit(self, payload: dict[str, Any]) -> None:
        self.submissions.append(dict(payload or {}))

    def _on_cancel(self) -> None:
        self.cancellations += 1


class RequestUserInputModalTest(unittest.IsolatedAsyncioTestCase):
    async def test_submit_flow_enters_review_and_returns_canonical_payload(self) -> None:
        app = _OverlayHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.overlay.activate(_single_question_payload())
            await pilot.pause()

            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            self.assertFalse(app.overlay.is_active)
            self.assertEqual(app.cancellations, 0)
            self.assertEqual(
                app.submissions,
                [
                    {
                        "answers": {
                            "confirm_path": {
                                "answers": ["Yes (Recommended)"],
                            }
                        }
                    }
                ],
            )

    async def test_escape_cancels_active_overlay(self) -> None:
        app = _OverlayHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.overlay.activate(_single_question_payload())
            await pilot.pause()

            await pilot.press("escape")
            await pilot.pause()

            self.assertFalse(app.overlay.is_active)
            self.assertEqual(app.cancellations, 1)
            self.assertEqual(app.submissions, [])

    async def test_other_text_keyboard_editing_is_used_for_submit(self) -> None:
        app = _OverlayHarnessApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            app.overlay.activate(_single_question_payload())
            await pilot.pause()

            await pilot.press("down")
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            await pilot.press("a")
            await pilot.press("b")
            await pilot.pause()
            await pilot.press("backspace")
            await pilot.pause()

            await pilot.press("tab")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            self.assertEqual(
                app.submissions,
                [
                    {
                        "answers": {
                            "confirm_path": {
                                "answers": ["a"],
                            }
                        }
                    }
                ],
            )
            self.assertEqual(app.cancellations, 0)
            self.assertFalse(app.overlay.is_active)


from __future__ import annotations

from types import SimpleNamespace
import unittest

from cli.agent_cli.ui import composer_submission


class _FakeKeyEvent:
    def __init__(self, key: str) -> None:
        self.key = key
        self.stopped = False
        self.prevented = False

    def stop(self) -> None:
        self.stopped = True

    def prevent_default(self) -> None:
        self.prevented = True


class ComposerSubmissionTest(unittest.TestCase):
    def test_ctrl_p_moves_active_slash_selection(self) -> None:
        moves: list[int] = []
        browsed: list[int] = []
        composer = SimpleNamespace(
            app=SimpleNamespace(
                move_slash_selection=lambda offset: moves.append(offset) or True,
                browse_prompt_history=lambda direction: browsed.append(direction) or False,
            )
        )
        event = _FakeKeyEvent("ctrl+p")

        handled = composer_submission.handle_submission_action_key(composer, event)

        self.assertTrue(handled)
        self.assertEqual(moves, [-1])
        self.assertEqual(browsed, [])
        self.assertTrue(event.stopped)
        self.assertTrue(event.prevented)

    def test_ctrl_p_browses_prompt_history_when_popup_is_inactive(self) -> None:
        moves: list[int] = []
        browsed: list[int] = []
        composer = SimpleNamespace(
            app=SimpleNamespace(
                move_slash_selection=lambda offset: moves.append(offset) or False,
                browse_prompt_history=lambda direction: browsed.append(direction) or True,
            )
        )
        event = _FakeKeyEvent("ctrl+p")

        handled = composer_submission.handle_submission_action_key(composer, event)

        self.assertTrue(handled)
        self.assertEqual(moves, [-1])
        self.assertEqual(browsed, [-1])
        self.assertTrue(event.stopped)
        self.assertTrue(event.prevented)

    def test_ctrl_n_browses_prompt_history_forward(self) -> None:
        moves: list[int] = []
        browsed: list[int] = []
        composer = SimpleNamespace(
            app=SimpleNamespace(
                move_slash_selection=lambda offset: moves.append(offset) or False,
                browse_prompt_history=lambda direction: browsed.append(direction) or True,
            )
        )
        event = _FakeKeyEvent("ctrl+n")

        handled = composer_submission.handle_submission_action_key(composer, event)

        self.assertTrue(handled)
        self.assertEqual(moves, [1])
        self.assertEqual(browsed, [1])
        self.assertTrue(event.stopped)
        self.assertTrue(event.prevented)

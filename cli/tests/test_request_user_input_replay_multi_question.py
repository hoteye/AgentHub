from __future__ import annotations

import unittest

from cli.agent_cli import thread_store_helpers_runtime as thread_helpers
from cli.agent_cli.models import PromptResponse, ThreadHistoryTurn, ToolEvent
from cli.agent_cli.runtime_services import prompt_turn_projection_runtime as projection
from cli.agent_cli.ui.request_user_input_state_runtime import OTHER_OPTION_VALUE
from cli.agent_cli.ui.transcript_controller import TranscriptControllerMixin


class _TranscriptProbe(TranscriptControllerMixin):
    def __init__(self) -> None:
        self.notices: list[str] = []

    def _write_system_notice(self, content: str) -> None:  # type: ignore[override]
        self.notices.append(str(content))


def _replayed_response(answer_map: dict[str, object]) -> PromptResponse:
    original_turn = ThreadHistoryTurn(
        turn_id="turn_replay_1",
        timestamp="2026-04-06T00:00:00+00:00",
        user_text="trigger replay",
        assistant_text="done",
        tool_events=[
            ToolEvent(
                name="request_user_input",
                ok=True,
                summary="request_user_input completed",
                payload={
                    "response": {
                        "answers": answer_map,
                        "metadata": {"source": "local_tui"},
                    }
                },
            )
        ],
        turn_events=[
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "normalized final answer"},
            }
        ],
    )
    persisted = original_turn.to_dict()
    restored_turn = ThreadHistoryTurn.from_dict(persisted)

    # request_user_input turns must keep structured tool output during replay.
    assert thread_helpers.turn_replay_requires_structured_tool_output(restored_turn)
    assert projection.turn_replay_requires_structured_tool_output(
        [event.to_dict() for event in restored_turn.tool_events]
    )

    return PromptResponse(
        user_text=restored_turn.user_text,
        assistant_text=restored_turn.assistant_text,
        tool_events=list(restored_turn.tool_events or []),
        turn_events=list(restored_turn.turn_events or []),
    )


class RequestUserInputReplayMultiQuestionTests(unittest.TestCase):
    def test_replay_projection_preserves_multi_question_answers_in_summary(self) -> None:
        response = _replayed_response(
            {
                "confirm_path": {"answers": ["Yes (Recommended)"]},
                "delivery": {"answers": ["Patch + notes"]},
            }
        )
        probe = _TranscriptProbe()

        probe._write_request_user_input_summary(response)

        self.assertEqual(len(probe.notices), 2)
        self.assertTrue(
            any("confirm_path" in line and "Yes (Recommended)" in line for line in probe.notices)
        )
        self.assertTrue(any("delivery" in line and "Patch + notes" in line for line in probe.notices))

    def test_replay_projection_keeps_other_custom_answer_text(self) -> None:
        response = _replayed_response(
            {
                "confirm_path": {"answers": ["Yes (Recommended)"]},
                "delivery": {"answers": ["custom delivery"]},
            }
        )
        probe = _TranscriptProbe()

        probe._write_request_user_input_summary(response)

        delivery_lines = [line for line in probe.notices if "delivery" in line]
        self.assertEqual(len(delivery_lines), 1)
        self.assertIn("custom delivery", delivery_lines[0])
        self.assertNotIn(OTHER_OPTION_VALUE, delivery_lines[0])
        self.assertNotEqual(delivery_lines[0].strip(), "User input delivery ->")


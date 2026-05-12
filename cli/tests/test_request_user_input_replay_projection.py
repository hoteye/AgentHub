from __future__ import annotations

import unittest

from cli.agent_cli import thread_store_helpers_runtime as thread_helpers
from cli.agent_cli.models import ThreadHistoryTurn, ToolEvent
from cli.agent_cli.runtime_services import prompt_turn_projection_runtime as projection


class RequestUserInputReplayProjectionTests(unittest.TestCase):
    def test_thread_store_turn_replay_requires_structured_output_for_request_user_input(self) -> None:
        turn = ThreadHistoryTurn(
            turn_id="turn_1",
            timestamp="2026-04-06T00:00:00+00:00",
            tool_events=[ToolEvent(name="request_user_input", ok=True, summary="request_user_input completed")],
        )

        self.assertTrue(thread_helpers.turn_replay_requires_structured_tool_output(turn))

    def test_projection_turn_replay_requires_structured_output_for_cancelled_request_user_input(self) -> None:
        events = [
            {
                "name": "request_user_input",
                "ok": False,
                "summary": "request_user_input cancelled",
                "payload": {"error": "request_user_input was cancelled before receiving a response"},
            }
        ]

        self.assertTrue(projection.turn_replay_requires_structured_tool_output(events))

    def test_response_items_with_canonical_final_message_replaces_existing_assistant_text(self) -> None:
        response_items = [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "draft answer"}],
            }
        ]
        turn_events = [
            {
                "type": "item.completed",
                "item": {
                    "type": "agent_message",
                    "text": "normalized final answer after request_user_input",
                },
            }
        ]

        updated = projection.response_items_with_canonical_final_message(
            response_items,
            turn_events,
            assistant_text_from_turn_events_fn=projection.assistant_text_from_turn_events,
        )

        content = updated[0]["content"]
        self.assertEqual(content[-1]["text"], "normalized final answer after request_user_input")

    def test_response_items_with_canonical_final_message_appends_when_missing_assistant_message(self) -> None:
        response_items = [
            {
                "type": "reasoning",
                "content": [{"type": "reasoning", "text": "thinking"}],
            }
        ]
        turn_events = [
            {
                "type": "item.completed",
                "item": {"type": "agent_message", "text": "final from replay projection"},
            }
        ]

        updated = projection.response_items_with_canonical_final_message(
            response_items,
            turn_events,
            assistant_text_from_turn_events_fn=projection.assistant_text_from_turn_events,
        )

        self.assertEqual(len(updated), 2)
        self.assertEqual(updated[-1]["type"], "message")
        self.assertEqual(updated[-1]["role"], "assistant")
        self.assertEqual(updated[-1]["content"][-1]["text"], "final from replay projection")

    def test_projection_turn_used_provider_false_when_protocol_disables_and_no_structured_items(self) -> None:
        turn = {
            "protocol_diagnostics": {"protocol_path": {"provider_used": False}},
            "tool_events": [],
            "turn_events": [],
        }

        self.assertFalse(
            projection.turn_used_provider(
                turn,
                turn_events_have_structured_tool_items_fn=projection.turn_events_have_structured_tool_items,
            )
        )

    def test_projection_turn_used_provider_true_for_request_user_input_tool_event_even_when_provider_false(self) -> None:
        turn = {
            "protocol_diagnostics": {"protocol_path": {"provider_used": False}},
            "tool_events": [
                {
                    "name": "request_user_input",
                    "ok": True,
                    "summary": "request_user_input completed",
                }
            ],
            "turn_events": [],
        }

        self.assertTrue(
            projection.turn_used_provider(
                turn,
                turn_events_have_structured_tool_items_fn=projection.turn_events_have_structured_tool_items,
            )
        )


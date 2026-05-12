from __future__ import annotations

import unittest

from cli.agent_cli.models import (
    PromptResponse,
    ReferenceContextItem,
    ResponseInputItem,
    ThreadHistoryTurn,
    ToolEvent,
)
from cli.agent_cli.thread_store import ThreadRecord
from cli.agent_cli import thread_store_helpers_runtime as helpers

class ThreadStoreHelpersRuntimeTests(unittest.TestCase):
    def test_assistant_history_text_prefers_visible_output_and_unique_tool_summaries(self) -> None:
        response = PromptResponse(
            user_text="read file",
            assistant_text="final answer",
            response_items=[
                ResponseInputItem.from_dict(
                    {
                        "type": "reasoning",
                        "content": [{"type": "reasoning", "text": "internal reasoning"}],
                    }
                ),
                ResponseInputItem.from_dict(
                    {
                        "type": "message",
                        "role": "assistant",
                        "phase": "final_answer",
                        "content": [{"type": "output_text", "text": "final answer"}],
                    }
                ),
            ],
            tool_events=[
                ToolEvent(name="read_file", ok=True, summary="opened file"),
                ToolEvent(name="read_file", ok=True, summary="opened file"),
                ToolEvent(name="read_file", ok=True, summary="final answer"),
            ],
        )

        self.assertEqual(
            helpers.assistant_history_text(response),
            "final answer\n\nopened file",
        )

    def test_row_to_record_maps_storage_fields(self) -> None:
        row = {
            "thread_id": "thread-1",
            "name": "name",
            "created_at": "2026-04-05T00:00:00+00:00",
            "updated_at": "2026-04-05T00:00:01+00:00",
            "rollout_path": "/tmp/thread-1.jsonl",
            "cwd": "/repo",
            "turn_count": 3,
            "archived": 1,
            "last_user_text": "hi",
            "last_assistant_text": "hello",
        }

        record = helpers.row_to_record(row, record_cls=ThreadRecord)

        self.assertEqual(record.thread_id, "thread-1")
        self.assertTrue(record.archived)
        self.assertEqual(record.turn_count, 3)

    def test_context_items_from_turns_clones_and_dedupes(self) -> None:
        item = ReferenceContextItem(item_type="file", path="/repo/a.txt", label="a.txt")
        turns = [
            ThreadHistoryTurn(turn_id="t1", timestamp="1", reference_context_items=[item]),
            ThreadHistoryTurn(turn_id="t2", timestamp="2", reference_context_items=[item]),
        ]

        items = helpers.context_items_from_turns(
            turns,
            dedupe_reference_context_items_fn=lambda values: values[:1],
        )

        self.assertEqual(len(items), 1)
        self.assertIsNot(items[0], item)
        self.assertEqual(items[0].path, "/repo/a.txt")

    def test_turn_used_provider_respects_protocol_override(self) -> None:
        turn = ThreadHistoryTurn(
            turn_id="t1",
            timestamp="1",
            protocol_diagnostics={"protocol_path": {"provider_used": False}},
        )

        self.assertFalse(
            helpers.turn_used_provider(
                turn,
                turn_has_structured_tool_items_fn=lambda _: False,
            )
        )
        self.assertTrue(
            helpers.turn_used_provider(
                ThreadHistoryTurn(
                    turn_id="t2",
                    timestamp="2",
                    protocol_diagnostics={"protocol_path": {"provider_used": False}},
                    tool_events=[ToolEvent(name="exec_command", ok=True, summary="ran command")],
                ),
                turn_has_structured_tool_items_fn=lambda _: False,
            )
        )

    def test_drop_last_n_user_turns_trims_from_last_user_boundary(self) -> None:
        turns = [
            ThreadHistoryTurn(turn_id="t1", timestamp="1", user_text="first"),
            ThreadHistoryTurn(turn_id="t2", timestamp="2", user_text=""),
            ThreadHistoryTurn(turn_id="t3", timestamp="3", user_text="second"),
        ]

        trimmed = helpers.drop_last_n_user_turns(turns, 1)

        self.assertEqual([turn.turn_id for turn in trimmed], ["t1", "t2"])

    def test_iso_to_unix_seconds_handles_z_suffix_and_invalid_values(self) -> None:
        self.assertEqual(helpers.iso_to_unix_seconds("1970-01-01T00:00:01Z"), 1)
        self.assertEqual(helpers.iso_to_unix_seconds("invalid"), 0)

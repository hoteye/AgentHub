from __future__ import annotations

import unittest
from contextlib import contextmanager

from cli.agent_cli import (  # noqa: E402
    headless_event_runtime,
    headless_jsonl_runtime,
    headless_snapshot_runtime,
    headless_stream_runtime,
)
from cli.agent_cli.models import PromptResponse, ToolEvent, default_response_items  # noqa: E402


class HeadlessStreamRuntimeSeamsTest(unittest.TestCase):
    def test_shell_item_events_from_payload_prefers_history_entries(self) -> None:
        payload = {
            "_event_history": [
                {"phase": "started", "command": "pwd", "call_id": "call_1"},
                {"phase": "output", "command": "pwd", "call_id": "call_1", "text": "/repo\n"},
                {
                    "phase": "completed",
                    "command": "pwd",
                    "call_id": "call_1",
                    "ok": True,
                    "stdout": "/repo\n",
                },
            ]
        }

        events = headless_event_runtime.shell_item_events_from_payload(payload)

        self.assertEqual(
            [event["type"] for event in events], ["item.started", "item.updated", "item.completed"]
        )
        self.assertEqual(events[1]["updated"]["phase"], "output")
        self.assertEqual(events[2]["result"]["stdout"], "/repo\n")

    def test_canonical_turn_events_wrapper_keeps_injected_shell_fn(self) -> None:
        response = PromptResponse(
            user_text="shell",
            assistant_text="done",
            tool_events=[
                ToolEvent(name="shell", ok=True, summary="ok", payload={"phase": "completed"})
            ],
        )
        sentinel = [
            {
                "type": "item.completed",
                "item": {"id": "x", "type": "agent_message", "text": "shell"},
            }
        ]

        events = headless_stream_runtime.canonical_turn_events(
            response,
            shell_turn_events_from_tool_events_fn=lambda tool_events: (
                sentinel if tool_events else []
            ),
        )

        self.assertEqual(events, sentinel)

    def test_snapshot_signature_ignores_ids_recursively(self) -> None:
        first = {
            "type": "item.completed",
            "item": {
                "id": "item_1",
                "type": "agent_message",
                "parts": [{"id": "part_1", "text": "done"}],
            },
        }
        second = {
            "type": "item.completed",
            "item": {
                "id": "item_9",
                "type": "agent_message",
                "parts": [{"id": "part_9", "text": "done"}],
            },
        }

        self.assertEqual(
            headless_snapshot_runtime.turn_event_backfill_signature(first),
            headless_stream_runtime.turn_event_backfill_signature(
                second,
                normalized_turn_event_value_fn=headless_stream_runtime.normalized_turn_event_value,
            ),
        )

    def test_canonical_turn_events_renders_response_items_when_no_turn_history(self) -> None:
        response = PromptResponse(
            user_text="prompt",
            commentary_text="Thinking.",
            assistant_text="Done.",
            response_items=default_response_items(
                commentary_text="Thinking.", assistant_text="Done."
            ),
        )

        events = headless_snapshot_runtime.canonical_turn_events(response)

        self.assertEqual(events[0]["type"], "turn.started")
        self.assertEqual(events[1]["item"]["type"], "agent_message")
        self.assertIn("Thinking.", events[1]["item"]["text"])
        self.assertIn("Done.", events[1]["item"]["text"])
        self.assertEqual(events[-1]["type"], "turn.completed")

    def test_jsonl_stream_helper_skips_semantically_duplicate_backfill_events(self) -> None:
        live_event = {
            "type": "item.completed",
            "item": {"id": "item_live", "type": "agent_message", "text": "done"},
        }
        response = PromptResponse(
            user_text="prompt",
            assistant_text="done",
            turn_events=[
                {
                    "type": "item.completed",
                    "item": {
                        "id": "item_backfill",
                        "type": "agent_message",
                        "text": "done",
                        "phase": "final_answer",
                    },
                },
                {"type": "turn.completed"},
            ],
        )

        class _Runner:
            turn_event_callback = None

            def handle_prompt(self, prompt: str) -> PromptResponse:
                self.turn_event_callback(live_event)
                return response

        emitted: list[dict[str, object]] = []

        def emit(_: object, payload: dict[str, object], *, request_id: str | None = None) -> None:
            line = dict(payload)
            if request_id is not None:
                line["id"] = request_id
            emitted.append(line)

        @contextmanager
        def temporary_turn_event_callback(runner: object, callback: object):
            previous = getattr(runner, "turn_event_callback", None)
            runner.turn_event_callback = callback
            try:
                yield
            finally:
                runner.turn_event_callback = previous

        streamed = headless_jsonl_runtime.stream_prompt_jsonl(
            _Runner(),
            "prompt",
            output_stream=None,
            thread_id="thread_1",
            request_id="req_1",
            emit_reference_jsonl_event_fn=emit,
            turn_event_signature_fn=headless_stream_runtime.turn_event_signature,
            turn_event_backfill_signature_fn=lambda event: headless_stream_runtime.turn_event_backfill_signature(
                event,
                normalized_turn_event_value_fn=headless_stream_runtime.normalized_turn_event_value,
            ),
            temporary_turn_event_callback_fn=temporary_turn_event_callback,
            canonical_turn_events_fn=lambda _: list(response.turn_events or []),
        )

        self.assertIs(streamed, response)
        self.assertEqual(
            emitted,
            [
                {"type": "thread.started", "thread_id": "thread_1", "id": "req_1"},
                {"type": "item.completed", "item": live_event["item"], "id": "req_1"},
                {"type": "turn.completed", "id": "req_1"},
            ],
        )

    def test_jsonl_stream_helper_emits_nonduplicate_backfill_events(self) -> None:
        live_event = {
            "type": "item.started",
            "item": {"id": "call_1", "type": "function_call", "name": "shell"},
        }
        completed_event = {
            "type": "item.completed",
            "item": {"id": "call_1", "type": "function_call", "name": "shell"},
        }
        response = PromptResponse(
            user_text="prompt",
            assistant_text="done",
            turn_events=[live_event, completed_event, {"type": "turn.completed"}],
        )

        class _Runner:
            turn_event_callback = None

            def handle_prompt(self, prompt: str) -> PromptResponse:
                self.turn_event_callback(live_event)
                return response

        emitted: list[dict[str, object]] = []

        def emit(_: object, payload: dict[str, object], *, request_id: str | None = None) -> None:
            line = dict(payload)
            if request_id is not None:
                line["id"] = request_id
            emitted.append(line)

        @contextmanager
        def temporary_turn_event_callback(runner: object, callback: object):
            previous = getattr(runner, "turn_event_callback", None)
            runner.turn_event_callback = callback
            try:
                yield
            finally:
                runner.turn_event_callback = previous

        headless_jsonl_runtime.stream_prompt_jsonl(
            _Runner(),
            "prompt",
            output_stream=None,
            thread_id="thread_2",
            emit_reference_jsonl_event_fn=emit,
            turn_event_signature_fn=headless_stream_runtime.turn_event_signature,
            turn_event_backfill_signature_fn=lambda event: headless_stream_runtime.turn_event_backfill_signature(
                event,
                normalized_turn_event_value_fn=headless_stream_runtime.normalized_turn_event_value,
            ),
            temporary_turn_event_callback_fn=temporary_turn_event_callback,
            canonical_turn_events_fn=lambda _: list(response.turn_events or []),
        )

        self.assertEqual(
            emitted,
            [
                {"type": "thread.started", "thread_id": "thread_2"},
                live_event,
                completed_event,
                {"type": "turn.completed"},
            ],
        )

    def test_emit_reference_jsonl_event_adds_stable_event_type_classification(self) -> None:
        lines: list[dict[str, object]] = []

        def emit_json_line(_: object, payload: dict[str, object]) -> None:
            lines.append(dict(payload))

        headless_stream_runtime.emit_reference_jsonl_event(
            None,
            {"type": "thread.started", "thread_id": "thread_1"},
            emit_json_line_fn=emit_json_line,
        )
        headless_stream_runtime.emit_reference_jsonl_event(
            None,
            {"type": "item.completed", "item": {"type": "mcp_tool_call", "tool": "list_dir"}},
            emit_json_line_fn=emit_json_line,
        )
        headless_stream_runtime.emit_reference_jsonl_event(
            None,
            {"type": "item.completed", "item": {"type": "agent_message", "text": "done"}},
            emit_json_line_fn=emit_json_line,
        )
        headless_stream_runtime.emit_reference_jsonl_event(
            None,
            {"type": "error", "error": "invalid_request"},
            emit_json_line_fn=emit_json_line,
        )

        self.assertEqual(lines[0]["event_type"], "session")
        self.assertEqual(lines[1]["event_type"], "tool")
        self.assertEqual(lines[2]["event_type"], "turn")
        self.assertEqual(lines[3]["event_type"], "error")

    def test_emit_reference_jsonl_event_can_omit_agenthub_extensions_for_codex_jsonl(self) -> None:
        lines: list[dict[str, object]] = []

        def emit_json_line(_: object, payload: dict[str, object]) -> None:
            lines.append(dict(payload))

        headless_stream_runtime.emit_reference_jsonl_event(
            None,
            {"type": "thread.started", "thread_id": "thread_1"},
            request_id="req_1",
            codex_jsonl=True,
            emit_json_line_fn=emit_json_line,
        )
        headless_stream_runtime.emit_reference_jsonl_event(
            None,
            {
                "type": "item.completed",
                "item": {"id": "item_1", "type": "agent_message", "text": "done"},
            },
            request_id="req_1",
            codex_jsonl=True,
            emit_json_line_fn=emit_json_line,
        )

        self.assertEqual(lines[0], {"type": "thread.started", "thread_id": "thread_1"})
        self.assertEqual(
            lines[1],
            {
                "type": "item.completed",
                "item": {"id": "item_1", "type": "agent_message", "text": "done"},
            },
        )

from __future__ import annotations

import sys
import unittest

from cli.agent_cli.models import ResponseInputItem
from cli.agent_cli.runtime_services import planner_context_history_runtime  # noqa: E402
from cli.agent_cli.runtime_services import prompt_turn_history_runtime  # noqa: E402
from cli.agent_cli.runtime_services import prompt_turn_runtime  # noqa: E402

class _RuntimeStub:
    _PLANNER_HISTORY_LIMIT_MESSAGES = 6

    def __init__(self) -> None:
        self._base_history = []
        self.history_turns = []
        self.history = []

    @staticmethod
    def _normalized_history_item(item):
        if not isinstance(item, dict):
            return None
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant", "system", "developer"} or not content:
            return None
        return {"role": role, "content": content}

    @staticmethod
    def _normalized_planner_input_item(item):
        if not isinstance(item, dict):
            return None
        if str(item.get("type") or "").strip():
            return ResponseInputItem.from_dict(item).to_dict()
        normalized = _RuntimeStub._normalized_history_item(item)
        if normalized is None:
            return None
        return planner_context_history_runtime.planner_message_input_item(
            normalized["role"],
            normalized["content"],
        )

    @staticmethod
    def _preferred_assistant_turn_text(*, turn_events, assistant_history_text, response_item_text, assistant_fallback_text):
        return prompt_turn_runtime.preferred_assistant_turn_text(
            turn_events=turn_events,
            assistant_history_text=assistant_history_text,
            response_item_text=response_item_text,
            assistant_fallback_text=assistant_fallback_text,
        )

    @staticmethod
    def _turn_used_provider(turn):
        return prompt_turn_runtime.turn_used_provider(turn)

class PromptTurnHistoryRuntimeTests(unittest.TestCase):
    def test_planner_history_merges_base_history_and_provider_turn_projection(self) -> None:
        runtime = _RuntimeStub()
        runtime._base_history = [{"role": "system", "content": "base guardrail"}]
        runtime.history_turns = [
            {
                "user_text": "ignored",
                "assistant_text": "host command output",
                "protocol_diagnostics": {"protocol_path": {"provider_used": False}},
            },
            {
                "user_text": "inspect repo",
                "assistant_history_text": "final answer\n\nran ls",
                "assistant_text": "fallback answer",
                "response_items": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "draft answer\n\nran ls"}],
                    }
                ],
                "turn_events": [
                    {"item": {"type": "command_execution", "command": "ls"}},
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": "final answer"},
                    },
                ],
            },
        ]

        history = prompt_turn_history_runtime.planner_history(runtime)

        self.assertEqual(
            history,
            [
                {"role": "system", "content": "base guardrail"},
                {"role": "user", "content": "inspect repo"},
                {"role": "assistant", "content": "final answer"},
            ],
        )

    def test_planner_history_falls_back_to_legacy_history_when_no_projected_items(self) -> None:
        runtime = _RuntimeStub()
        runtime.history = [
            {"role": "user", "content": "legacy user"},
            {"role": "assistant", "content": "legacy assistant"},
            {"role": "assistant", "content": "   "},
        ]

        history = prompt_turn_history_runtime.planner_history(runtime)

        self.assertEqual(
            history,
            [
                {"role": "user", "content": "legacy user"},
                {"role": "assistant", "content": "legacy assistant"},
            ],
        )

    def test_planner_history_records_fail_closed_reasoning_diagnostics_for_tool_history_projection(self) -> None:
        runtime = _RuntimeStub()
        runtime.history_turns = [
            {
                "user_text": "现在北京时间几点？",
                "assistant_text": "北京时间 10:00。",
                "response_items": [
                    {
                        "type": "reasoning",
                        "content": [{"type": "reasoning", "text": "先查询北京时间"}],
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "北京时间 10:00。"}],
                    },
                ],
                "turn_events": [
                    {
                        "type": "item.completed",
                        "item": {
                            "type": "command_execution",
                            "call_id": "call_exec_1",
                            "command": "date",
                            "aggregated_output": "10:00\n",
                            "exit_code": 0,
                            "status": "completed",
                        },
                    },
                    {
                        "type": "item.completed",
                        "item": {"type": "agent_message", "text": "北京时间 10:00。"},
                    },
                ],
            }
        ]

        history = prompt_turn_history_runtime.planner_history(runtime)

        self.assertEqual(
            history,
            [
                {"role": "user", "content": "现在北京时间几点？"},
                {"role": "assistant", "content": "北京时间 10:00。"},
            ],
        )
        self.assertEqual(
            runtime._shared_replay_reasoning_retention_diagnostics,
            [
                {
                    "item_type": "reasoning",
                    "source": "tool_history_projection",
                    "retention": "stripped",
                    "guard": "missing_encrypted_content",
                    "summary_present": False,
                    "content_present": True,
                    "detail": "shared replay stripped previous-turn reasoning because encrypted_content is missing",
                }
            ],
        )

    def test_planner_message_history_input_items_fail_closed_on_unsafe_reasoning_items(self) -> None:
        runtime = _RuntimeStub()

        items = planner_context_history_runtime.planner_message_history_input_items(
            runtime,
            [
                {
                    "type": "reasoning",
                    "content": [{"type": "reasoning", "text": "先检查仓库"}],
                },
                {"role": "assistant", "content": "safe assistant text"},
            ],
        )

        self.assertEqual(
            items,
            [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "input_text", "text": "safe assistant text"}],
                }
            ],
        )
        self.assertEqual(
            runtime._shared_replay_reasoning_retention_diagnostics,
            [
                {
                    "item_type": "reasoning",
                    "source": "planner_context_history",
                    "retention": "stripped",
                    "guard": "missing_encrypted_content",
                    "summary_present": False,
                    "content_present": True,
                    "detail": "shared replay stripped previous-turn reasoning because encrypted_content is missing",
                }
            ],
        )

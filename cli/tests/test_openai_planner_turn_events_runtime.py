from __future__ import annotations

from cli.agent_cli.models_turn_events import reasoning_replay_projection_from_turn_event_item
from cli.agent_cli.models import response_message_item
from cli.agent_cli.providers import openai_planner_turn_events_runtime as runtime
from cli.agent_cli.providers.openai_planner_turn_events import _canonical_turn_events

def test_runtime_final_text_prefers_response_items_over_assistant_text() -> None:
    final_text = runtime.final_text_for_turn_events(
        assistant_text="fallback",
        response_items=[response_message_item("assistant", "native final", phase="final_answer")],
    )

    assert final_text == "native final"


def test_runtime_final_text_ignores_commentary_when_final_phase_exists() -> None:
    final_text = runtime.final_text_for_turn_events(
        assistant_text="fallback",
        response_items=[
            response_message_item("assistant", "我来查一下北京今天的天气。", phase="commentary"),
            response_message_item("assistant", "北京今天晴，18°C。", phase="final_answer"),
        ],
    )

    assert final_text == "北京今天晴，18°C。"

def test_runtime_rewrite_existing_turn_events_backfills_missing_agent_message() -> None:
    rewritten = runtime.rewrite_existing_turn_events(
        [
            {"type": "item.completed", "item": {"id": "item_3", "type": "mcp_tool_call", "tool": "list_dir"}},
            {"type": "turn.completed", "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}},
        ],
        final_text="done",
    )

    assert rewritten[-2]["type"] == "item.completed"
    assert rewritten[-2]["item"] == {"id": "item_0", "type": "agent_message", "text": "done"}
    assert rewritten[-1]["type"] == "turn.completed"

def test_canonical_turn_events_rewrites_existing_events_with_response_item_text() -> None:
    events = _canonical_turn_events(
        assistant_text="fallback",
        response_items=[response_message_item("assistant", "canonical final", phase="final_answer")],
        executed_item_events=[],
        existing_turn_events=[
            {"type": "turn.started"},
            {
                "type": "item.completed",
                "item": {"id": "item_0", "type": "agent_message", "text": "stale"},
            },
            {"type": "turn.completed", "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}},
        ],
    )

    assert events[1]["item"]["text"] == "canonical final"


def test_canonical_turn_events_rewrite_does_not_merge_commentary_into_final_message() -> None:
    events = _canonical_turn_events(
        assistant_text="fallback",
        response_items=[
            response_message_item("assistant", "我来查一下北京今天的天气。", phase="commentary"),
            response_message_item("assistant", "北京今天晴，18°C。", phase="final_answer"),
        ],
        executed_item_events=[],
        existing_turn_events=[
            {"type": "turn.started"},
            {
                "type": "item.completed",
                "item": {
                    "id": "item_0",
                    "type": "agent_message",
                    "text": "我来查一下北京今天的天气。",
                    "phase": "commentary",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "item_1",
                    "type": "agent_message",
                    "text": "stale final",
                    "phase": "final_answer",
                },
            },
            {"type": "turn.completed", "usage": {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}},
        ],
    )

    assert events[1]["item"]["text"] == "我来查一下北京今天的天气。"
    assert events[2]["item"]["text"] == "北京今天晴，18°C。"


def test_turn_event_reasoning_replay_projection_fail_closed_without_encrypted_content() -> None:
    projection = reasoning_replay_projection_from_turn_event_item(
        {
            "type": "reasoning",
            "text": "先检查仓库",
            "summary": [{"type": "summary_text", "text": "先检查仓库"}],
        }
    )

    assert projection["input_item"] is None
    assert projection["diagnostic"] == {
        "item_type": "reasoning",
        "source": "turn_event_replay",
        "retention": "stripped",
        "guard": "missing_encrypted_content",
        "summary_present": True,
        "content_present": True,
        "detail": "shared replay stripped previous-turn reasoning because encrypted_content is missing",
    }


def test_turn_event_reasoning_replay_projection_preserves_summary_when_encrypted_content_exists() -> None:
    projection = reasoning_replay_projection_from_turn_event_item(
        {
            "type": "reasoning",
            "summary": [{"type": "summary_text", "text": "先检查仓库"}],
            "encrypted_content": "enc-1",
        }
    )

    assert projection["diagnostic"] is None
    assert projection["input_item"] == {
        "type": "reasoning",
        "summary": [{"type": "summary_text", "text": "先检查仓库"}],
        "encrypted_content": "enc-1",
    }

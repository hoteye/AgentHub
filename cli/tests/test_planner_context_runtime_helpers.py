from __future__ import annotations

from cli.agent_cli.runtime_services import planner_context_runtime_helpers


class _RuntimeStub:
    def _turn_events_have_structured_tool_items(self, turn_events):
        del turn_events
        return False

    def _assistant_text_from_turn_events(self, turn_events):
        for raw_event in reversed(list(turn_events or [])):
            if not isinstance(raw_event, dict) or str(raw_event.get("type") or "").strip() != "item.completed":
                continue
            item = raw_event.get("item")
            if not isinstance(item, dict) or str(item.get("type") or "").strip() != "agent_message":
                continue
            text = str(item.get("text") or "").strip()
            if text:
                return text
        return ""

    def _preferred_assistant_turn_text(
        self,
        *,
        turn_events,
        assistant_history_text,
        response_item_text,
        assistant_fallback_text,
    ):
        del turn_events, response_item_text
        return assistant_history_text or assistant_fallback_text


def _planner_message_input_item(role: str, content: str):
    return {
        "type": "message",
        "role": role,
        "content": [{"type": "input_text" if role == "user" else "output_text", "text": content}],
    }


def test_runtime_planner_turn_response_replay_items_omits_completed_turn_commentary_messages() -> None:
    runtime = _RuntimeStub()
    turn = {
        "response_items": [
            {
                "type": "message",
                "role": "assistant",
                "phase": "commentary",
                "content": [{"type": "output_text", "text": "我补两类测试：核心清理逻辑和命令行输出。"}],
            },
            {
                "type": "message",
                "role": "assistant",
                "phase": "final_answer",
                "content": [{"type": "output_text", "text": "- 修改文件：test_csv_clean.py\n- 测试是否通过：通过"}],
            },
        ],
        "turn_events": [
            {"type": "turn.started"},
            {
                "type": "item.completed",
                "item": {
                    "id": "item_1",
                    "type": "agent_message",
                    "phase": "commentary",
                    "text": "我补两类测试：核心清理逻辑和命令行输出。",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "item_2",
                    "type": "agent_message",
                    "phase": "final_answer",
                    "text": "- 修改文件：test_csv_clean.py\n- 测试是否通过：通过",
                },
            },
            {"type": "turn.completed"},
        ],
    }

    items = planner_context_runtime_helpers.planner_turn_response_replay_items(
        runtime,
        turn,
        planner_message_input_item_fn=_planner_message_input_item,
    )

    assert [item.get("type") for item in items] == ["message"]
    assert items[0]["role"] == "assistant"
    assert items[0]["phase"] == "final_answer"
    assert items[0]["content"][0]["text"] == "- 修改文件：test_csv_clean.py\n- 测试是否通过：通过"

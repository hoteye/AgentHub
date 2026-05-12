from __future__ import annotations

from cli.agent_cli.models import ResponseInputItem, RolloutItem, ThreadHistoryTurn, ToolEvent
from cli.agent_cli import thread_store_replay


def _tool_output_event(call_id: str, text: str) -> dict:
    return {
        "type": "item.completed",
        "item": {
            "type": "function_call_output",
            "call_id": call_id,
            "output": text,
        },
    }


def _assistant_event(text: str) -> dict:
    return {
        "type": "item.completed",
        "item": {
            "type": "agent_message",
            "text": text,
        },
    }


def _provider_turn(*, turn_id: str, timestamp: str, user_text: str, call_ids: list[str], assistant_text: str) -> ThreadHistoryTurn:
    turn_events = [_tool_output_event(call_id, f"output for {call_id}") for call_id in call_ids]
    turn_events.append(_assistant_event(assistant_text))
    return ThreadHistoryTurn(
        turn_id=turn_id,
        timestamp=timestamp,
        user_text=user_text,
        assistant_text=assistant_text,
        assistant_history_text=assistant_text,
        turn_events=turn_events,
    )


def test_planner_input_items_from_turns_does_not_split_structured_turn_segments() -> None:
    turn_1 = _provider_turn(
        turn_id="turn_1",
        timestamp="2026-04-14T00:00:00+00:00",
        user_text="turn one prompt",
        call_ids=["call_turn1_tail"],
        assistant_text="turn one done",
    )
    turn_2 = _provider_turn(
        turn_id="turn_2",
        timestamp="2026-04-14T00:01:00+00:00",
        user_text="turn two prompt",
        call_ids=["call_turn2_a", "call_turn2_b"],
        assistant_text="turn two done",
    )

    items = thread_store_replay.planner_input_items_from_turns(
        [turn_1, turn_2],
        planner_history_limit=6,
    )

    assert [item.get("role") for item in items if item.get("type") == "message"] == [
        "user",
        "assistant",
    ]
    assert items[0]["role"] == "user"
    assert items[0]["content"][0]["text"] == "turn two prompt"
    assert all(str(item.get("call_id") or "") != "call_turn1_tail" for item in items)


def test_planner_input_items_from_rollout_items_does_not_start_with_orphan_tool_output() -> None:
    turn_1 = _provider_turn(
        turn_id="turn_1",
        timestamp="2026-04-14T00:00:00+00:00",
        user_text="turn one prompt",
        call_ids=["call_turn1_tail"],
        assistant_text="turn one done",
    )
    turn_2 = _provider_turn(
        turn_id="turn_2",
        timestamp="2026-04-14T00:01:00+00:00",
        user_text="turn two prompt",
        call_ids=["call_turn2_a", "call_turn2_b"],
        assistant_text="turn two done",
    )
    rollout_items = [
        RolloutItem(
            item_type="turn",
            thread_id="thread_1",
            timestamp=turn_1.timestamp,
            turn=turn_1,
        ).to_dict(),
        RolloutItem(
            item_type="turn",
            thread_id="thread_1",
            timestamp=turn_2.timestamp,
            turn=turn_2,
        ).to_dict(),
    ]

    items = thread_store_replay.planner_input_items_from_rollout_items(
        rollout_items,
        planner_history_limit=6,
    )

    assert items[0]["type"] == "message"
    assert items[0]["role"] == "user"
    assert items[0]["content"][0]["text"] == "turn two prompt"
    assert all(str(item.get("call_id") or "") != "call_turn1_tail" for item in items)


def test_planner_turn_response_replay_items_prefers_explicit_input_image_output_truth() -> None:
    image_artifact = {
        "path": "/tmp/diagram.png",
        "mime_type": "image/png",
        "size_bytes": 42,
        "width": 10,
        "height": 12,
        "image_url": "data:image/png;base64,AAA",
        "detail": "high",
    }
    turn = ThreadHistoryTurn(
        turn_id="turn_media_truth",
        timestamp="2026-04-15T00:02:00+00:00",
        user_text="inspect image",
        assistant_text="image injected",
        assistant_history_text="image injected",
        response_items=[
            ResponseInputItem.from_dict(
                {
                    "type": "message",
                    "role": "assistant",
                    "phase": "final_answer",
                    "content": [{"type": "output_text", "text": "image injected"}],
                }
            )
        ],
        tool_events=[
            ToolEvent(
                name="view_image",
                ok=True,
                summary="image ready",
                payload={
                    "provider_call_id": "call_view_image_1",
                    "ok": True,
                    "image_artifacts": [image_artifact],
                },
            )
        ],
        turn_events=[
            {"type": "turn.started"},
            {
                "type": "item.completed",
                "item": {
                    "id": "item_1",
                    "type": "mcp_tool_call",
                    "tool": "view_image",
                    "status": "completed",
                    "result": {"structured_content": {"image_artifacts": [image_artifact]}},
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "item_2",
                    "type": "function_call_output",
                    "call_id": "call_view_image_1",
                    "output": [
                        {
                            "type": "input_image",
                            "image_url": "data:image/png;base64,AAA",
                            "detail": "high",
                        }
                    ],
                    "success": True,
                },
            },
            {"type": "item.completed", "item": {"id": "item_3", "type": "agent_message", "text": "image injected"}},
            {"type": "turn.completed"},
        ],
    )

    items = thread_store_replay.planner_turn_response_replay_items(turn)
    outputs = [item for item in items if str(item.get("type") or "").strip() == "function_call_output"]

    assert len(outputs) == 1
    assert outputs[0]["call_id"] == "call_view_image_1"
    assert isinstance(outputs[0]["output"], list)
    assert outputs[0]["output"][0]["type"] == "input_image"


def test_planner_turn_response_replay_items_dedupes_duplicate_input_image_outputs_within_turn() -> None:
    turn = ThreadHistoryTurn(
        turn_id="turn_media_dedupe",
        timestamp="2026-04-15T00:03:00+00:00",
        user_text="inspect image",
        assistant_text="done",
        assistant_history_text="done",
        response_items=[
            ResponseInputItem.from_dict(
                {
                "type": "function_call_output",
                "call_id": "call_img_1",
                "output": [
                    {
                        "type": "input_image",
                        "image_url": "data:image/png;base64,AAA",
                        "detail": "original",
                    }
                ],
                "image_transport_subject": "/tmp/diagram.png",
                "success": True,
            }
        ),
        ResponseInputItem.from_dict(
            {
                "type": "function_call_output",
                "call_id": "call_img_2",
                "output": [
                    {
                        "type": "input_image",
                        "image_url": "data:image/png;base64,AAA",
                        "detail": "original",
                    }
                ],
                "image_transport_subject": "/tmp/diagram.png",
                "success": True,
            }
        ),
            ResponseInputItem.from_dict(
                {
                    "type": "message",
                    "role": "assistant",
                    "phase": "final_answer",
                    "content": [{"type": "output_text", "text": "done"}],
                }
            ),
        ],
    )

    items = thread_store_replay.planner_turn_response_replay_items(turn)
    outputs = [item for item in items if str(item.get("type") or "").strip() == "function_call_output"]

    assert len(outputs) == 1
    assert outputs[0]["call_id"] == "call_img_1"
    assert outputs[0]["output"][0]["type"] == "input_image"


def test_planner_turn_response_replay_items_omits_completed_turn_commentary_messages() -> None:
    turn = ThreadHistoryTurn(
        turn_id="turn_commentary_history",
        timestamp="2026-04-21T00:00:00+00:00",
        user_text="补测试并跑通",
        assistant_text="- 修改文件：test_csv_clean.py\n- 测试是否通过：通过",
        assistant_history_text="- 修改文件：test_csv_clean.py\n- 测试是否通过：通过",
        response_items=[
            ResponseInputItem.from_dict(
                {
                    "type": "message",
                    "role": "assistant",
                    "phase": "commentary",
                    "content": [{"type": "output_text", "text": "我补两类测试：核心清理逻辑和命令行输出。"}],
                }
            ),
            ResponseInputItem.from_dict(
                {
                    "type": "message",
                    "role": "assistant",
                    "phase": "final_answer",
                    "content": [{"type": "output_text", "text": "- 修改文件：test_csv_clean.py\n- 测试是否通过：通过"}],
                }
            ),
        ],
        turn_events=[
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
    )

    items = thread_store_replay.planner_turn_response_replay_items(turn)

    assert [item.get("type") for item in items] == ["message"]
    assert items[0]["role"] == "assistant"
    assert items[0]["phase"] == "final_answer"
    assert items[0]["content"][0]["text"] == "- 修改文件：test_csv_clean.py\n- 测试是否通过：通过"


def test_planner_input_items_from_turns_dedupes_duplicate_input_images_across_bounded_turns() -> None:
    repeated_output = [
        {
            "type": "input_image",
            "image_url": "data:image/png;base64,AAA",
            "detail": "original",
        }
    ]
    turn_1 = ThreadHistoryTurn(
        turn_id="turn_media_1",
        timestamp="2026-04-15T00:04:00+00:00",
        user_text="first inspect",
        assistant_text="done one",
        assistant_history_text="done one",
        response_items=[
            ResponseInputItem.from_dict(
                {
                    "type": "function_call_output",
                    "call_id": "call_img_1",
                    "output": repeated_output,
                    "image_transport_subject": "/tmp/diagram.png",
                    "success": True,
                }
            ),
            ResponseInputItem.from_dict(
                {
                    "type": "message",
                    "role": "assistant",
                    "phase": "final_answer",
                    "content": [{"type": "output_text", "text": "done one"}],
                }
            ),
        ],
    )
    turn_2 = ThreadHistoryTurn(
        turn_id="turn_media_2",
        timestamp="2026-04-15T00:05:00+00:00",
        user_text="second inspect",
        assistant_text="done two",
        assistant_history_text="done two",
        response_items=[
            ResponseInputItem.from_dict(
                {
                    "type": "function_call_output",
                    "call_id": "call_img_2",
                    "output": repeated_output,
                    "image_transport_subject": "/tmp/diagram.png",
                    "success": True,
                }
            ),
            ResponseInputItem.from_dict(
                {
                    "type": "message",
                    "role": "assistant",
                    "phase": "final_answer",
                    "content": [{"type": "output_text", "text": "done two"}],
                }
            ),
        ],
    )

    items = thread_store_replay.planner_input_items_from_turns(
        [turn_1, turn_2],
        planner_history_limit=8,
    )

    outputs = [item for item in items if str(item.get("type") or "").strip() == "function_call_output"]
    assert len(outputs) == 1
    assert outputs[0]["call_id"] == "call_img_1"
    assert outputs[0]["output"][0]["type"] == "input_image"

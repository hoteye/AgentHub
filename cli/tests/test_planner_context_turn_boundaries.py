from __future__ import annotations

from types import SimpleNamespace

from cli.agent_cli.runtime_services import planner_context_runtime
from cli.agent_cli.runtime_services import prompt_turn_runtime


def _tool_output_item(call_id: str, text: str) -> dict:
    return {
        "type": "function_call_output",
        "call_id": call_id,
        "output": text,
    }


def _assistant_message(text: str) -> dict:
    return {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": text}],
        "phase": "final_answer",
    }


def _turn_payload(*, user_text: str, call_ids: list[str], assistant_text: str) -> dict:
    response_items = [_tool_output_item(call_id, f"output for {call_id}") for call_id in call_ids]
    response_items.append(_assistant_message(assistant_text))
    return {
        "user_text": user_text,
        "assistant_text": assistant_text,
        "assistant_history_text": assistant_text,
        "response_items": response_items,
        "turn_events": [
            {
                "type": "item.completed",
                "item": {
                    "type": "agent_message",
                    "text": assistant_text,
                },
            }
        ],
        "tool_events": [{"name": "exec_command", "ok": True, "summary": "ok"}],
        "protocol_diagnostics": {"protocol_path": {"provider_used": True}},
    }


def _runtime_stub(*, history_turns: list[dict] | None = None, rollout_items: list[dict] | None = None):
    return SimpleNamespace(
        rollout_items=list(rollout_items or []),
        history_turns=list(history_turns or []),
        _base_history=[],
        _PLANNER_HISTORY_LIMIT_MESSAGES=6,
        _turn_used_provider=prompt_turn_runtime.turn_used_provider,
        _assistant_text_from_turn_events=prompt_turn_runtime.assistant_text_from_turn_events,
        _response_items_with_canonical_final_message=prompt_turn_runtime.response_items_with_canonical_final_message,
        _preferred_assistant_turn_text=prompt_turn_runtime.preferred_assistant_turn_text,
        _turn_events_have_structured_tool_items=prompt_turn_runtime.turn_events_have_structured_tool_items,
        _planner_history=lambda: [],
    )


def test_planner_conversation_turn_items_preserves_turn_boundaries() -> None:
    runtime = _runtime_stub(
        history_turns=[
            _turn_payload(
                user_text="turn one prompt",
                call_ids=["call_turn1_tail"],
                assistant_text="turn one done",
            ),
            _turn_payload(
                user_text="turn two prompt",
                call_ids=["call_turn2_a", "call_turn2_b"],
                assistant_text="turn two done",
            ),
        ]
    )

    items = planner_context_runtime.planner_conversation_turn_items(runtime)

    assert items[0]["type"] == "message"
    assert items[0]["role"] == "user"
    assert items[0]["content"][0]["text"] == "turn two prompt"
    assert all(str(item.get("call_id") or "") != "call_turn1_tail" for item in items)


def test_planner_conversation_rollout_items_preserves_turn_boundaries() -> None:
    runtime = _runtime_stub(
        rollout_items=[
            {
                "type": "turn",
                "turn": _turn_payload(
                    user_text="turn one prompt",
                    call_ids=["call_turn1_tail"],
                    assistant_text="turn one done",
                ),
            },
            {
                "type": "turn",
                "turn": _turn_payload(
                    user_text="turn two prompt",
                    call_ids=["call_turn2_a", "call_turn2_b"],
                    assistant_text="turn two done",
                ),
            },
        ]
    )

    items = planner_context_runtime.planner_conversation_rollout_items(runtime)

    assert items[0]["type"] == "message"
    assert items[0]["role"] == "user"
    assert items[0]["content"][0]["text"] == "turn two prompt"
    assert all(str(item.get("call_id") or "") != "call_turn1_tail" for item in items)

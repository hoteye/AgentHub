from __future__ import annotations

import json
from types import SimpleNamespace

from cli.agent_cli.runtime_core.command_handlers_structured_runtime import (
    handle_request_user_input_command,
)


def _multi_question_arg_text() -> str:
    return (
        '{"questions":['
        '{"id":"confirm_path","header":"Confirm","question":"Proceed?",'
        '"options":[{"label":"Yes (Recommended)","description":"Continue."},{"label":"No","description":"Stop."}]},'
        '{"id":"delivery","header":"Delivery","question":"How should we ship?",'
        '"options":[{"label":"Standard","description":"3-5 days"},{"label":"Express","description":"1-2 days"}]}'
        "]}"
    )


def test_multi_question_submit_preserves_canonical_answers_in_tool_event_and_items() -> None:
    runtime = SimpleNamespace(
        collaboration_mode="default",
        default_mode_request_user_input=True,
        request_user_input_handler=lambda _payload: {
            "answers": {
                "confirm_path": {"answers": ["Yes (Recommended)"]},
                "delivery": {"answers": ["Express"]},
            }
        },
    )

    result = handle_request_user_input_command(runtime, arg_text=_multi_question_arg_text())

    event = result.tool_events[0]
    assert event.name == "request_user_input"
    assert event.ok is True
    response = event.payload["response"]
    assert response["answers"]["confirm_path"]["answers"] == ["Yes (Recommended)"]
    assert response["answers"]["delivery"]["answers"] == ["Express"]

    started = result.item_events[0]
    assert started["type"] == "item.started"
    assert started["item"]["tool"] == "request_user_input"
    questions = started["item"]["arguments"]["questions"]
    assert [q["id"] for q in questions] == ["confirm_path", "delivery"]
    assert all(q["is_other"] is True for q in questions)

    completed = result.item_events[-1]
    assert completed["type"] == "item.completed"
    assert completed["item"]["status"] == "completed"
    structured = completed["item"]["result"]["structured_content"]["response"]
    assert structured["answers"]["confirm_path"]["answers"] == ["Yes (Recommended)"]
    assert structured["answers"]["delivery"]["answers"] == ["Express"]


def test_multi_question_other_custom_answer_is_preserved_in_completed_item_and_payload() -> None:
    runtime = SimpleNamespace(
        collaboration_mode="default",
        default_mode_request_user_input=True,
        request_user_input_handler=lambda _payload: {
            "answers": {
                "confirm_path": "yes",
                "delivery": "custom delivery",
            }
        },
    )

    result = handle_request_user_input_command(runtime, arg_text=_multi_question_arg_text())

    event = result.tool_events[0]
    response = event.payload["response"]
    assert response["answers"]["confirm_path"]["answers"] == ["yes"]
    assert response["answers"]["delivery"]["answers"] == ["custom delivery"]

    completed = result.item_events[-1]
    structured = completed["item"]["result"]["structured_content"]["response"]
    assert structured["answers"]["delivery"]["answers"] == ["custom delivery"]
    assert structured["answers"]["delivery"]["answers"][0] != "__other__"

    rendered = json.loads(result.assistant_text)
    assert rendered["answers"]["delivery"]["answers"] == ["custom delivery"]

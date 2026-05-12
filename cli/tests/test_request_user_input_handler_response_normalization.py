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
        '"options":[{"label":"Yes","description":"Continue."},{"label":"No","description":"Stop."}]},'
        '{"id":"delivery","header":"Delivery","question":"How should we ship?",'
        '"options":[{"label":"Standard","description":"3-5 days"},{"label":"Express","description":"1-2 days"}]}'
        "]}"
    )


def test_handler_legacy_and_partial_canonical_outputs_are_normalized() -> None:
    runtime = SimpleNamespace(
        collaboration_mode="default",
        default_mode_request_user_input=True,
        request_user_input_handler=lambda _payload: {
            "answers": {
                "confirm_path": "yes",
                "delivery": {"answer": "custom delivery"},
                "ignored_field": "should be filtered",
            },
            "metadata": {"source": "legacy-and-partial"},
        },
    )

    result = handle_request_user_input_command(runtime, arg_text=_multi_question_arg_text())

    assert result.tool_events[0].ok is True
    normalized = json.loads(result.assistant_text)
    assert normalized["answers"]["confirm_path"]["answers"] == ["yes"]
    assert normalized["answers"]["delivery"]["answers"] == ["custom delivery"]
    assert "ignored_field" not in normalized["answers"]
    assert normalized["metadata"] == {"source": "legacy-and-partial"}

    completed = result.item_events[-1]
    structured = completed["item"]["result"]["structured_content"]["response"]
    assert structured["answers"]["confirm_path"]["answers"] == ["yes"]
    assert structured["answers"]["delivery"]["answers"] == ["custom delivery"]


def test_handler_bad_shape_is_safely_handled_and_followup_request_still_works() -> None:
    calls = {"count": 0}

    def _handler(_payload):
        calls["count"] += 1
        if calls["count"] == 1:
            return {"answers": "invalid-shape", "metadata": {"source": "bad-shape"}}
        return {"answers": {"confirm_path": "yes"}}

    runtime = SimpleNamespace(
        collaboration_mode="default",
        default_mode_request_user_input=True,
        request_user_input_handler=_handler,
    )

    first = handle_request_user_input_command(runtime, arg_text=_multi_question_arg_text())
    assert first.tool_events[0].ok is True
    first_response = json.loads(first.assistant_text)
    assert first_response["answers"] == {}
    assert first.tool_events[0].payload["response"]["answers"] == {}
    assert first_response["metadata"] == {"source": "bad-shape"}

    second = handle_request_user_input_command(runtime, arg_text=_multi_question_arg_text())
    assert second.tool_events[0].ok is True
    second_response = json.loads(second.assistant_text)
    assert second_response["answers"]["confirm_path"]["answers"] == ["yes"]


def test_non_dict_handler_response_cancels_without_throwing_and_next_call_recovers() -> None:
    calls = {"count": 0}

    def _handler(_payload):
        calls["count"] += 1
        if calls["count"] == 1:
            return "not-a-dict"
        return {"answers": {"confirm_path": "yes"}}

    runtime = SimpleNamespace(
        collaboration_mode="default",
        default_mode_request_user_input=True,
        request_user_input_handler=_handler,
    )

    first = handle_request_user_input_command(runtime, arg_text=_multi_question_arg_text())
    assert first.tool_events[0].ok is False
    assert first.tool_events[0].name == "request_user_input"
    assert first.item_events[-1]["item"]["status"] == "failed"

    second = handle_request_user_input_command(runtime, arg_text=_multi_question_arg_text())
    assert second.tool_events[0].ok is True
    second_response = json.loads(second.assistant_text)
    assert second_response["answers"]["confirm_path"]["answers"] == ["yes"]

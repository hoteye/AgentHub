from __future__ import annotations

import json
from types import SimpleNamespace

from cli.agent_cli.runtime_core.command_handlers_structured_runtime import (
    handle_request_user_input_command,
)


def _request_user_input_arg_text() -> str:
    return (
        '{"questions":[{"id":"confirm_path","header":"Confirm","question":"Proceed?",'
        '"options":[{"label":"Yes (Recommended)","description":"Continue."},'
        '{"label":"No","description":"Stop."}]}]}'
    )


def test_request_user_input_success_emits_structured_tool_and_item_events() -> None:
    runtime = SimpleNamespace(
        collaboration_mode="default",
        default_mode_request_user_input=True,
        request_user_input_handler=lambda _payload: {
            "answers": {"confirm_path": "yes"},
            "metadata": {"source": "test"},
        },
    )

    result = handle_request_user_input_command(runtime, arg_text=_request_user_input_arg_text())

    assert result.tool_events[0].name == "request_user_input"
    assert result.tool_events[0].ok is True
    assert result.tool_events[0].summary == "request_user_input completed"
    response_payload = result.tool_events[0].payload["response"]
    assert response_payload["answers"]["confirm_path"]["answers"] == ["yes"]
    assert response_payload["metadata"] == {"source": "test"}

    rendered = json.loads(result.assistant_text)
    assert rendered["answers"]["confirm_path"]["answers"] == ["yes"]
    assert rendered["metadata"] == {"source": "test"}

    started = result.item_events[0]
    assert started["type"] == "item.started"
    assert started["item"]["tool"] == "request_user_input"
    assert started["item"]["status"] == "in_progress"
    assert started["item"]["arguments"]["questions"][0]["id"] == "confirm_path"
    assert started["item"]["arguments"]["questions"][0]["is_other"] is True

    completed = next(
        event
        for event in result.item_events
        if event["type"] == "item.completed" and event["item"]["type"] == "mcp_tool_call"
    )
    assert completed["type"] == "item.completed"
    assert completed["item"]["tool"] == "request_user_input"
    assert completed["item"]["status"] == "completed"
    assert completed["item"]["error"] is None
    assert completed["item"]["result"]["structured_content"]["response"]["answers"]["confirm_path"]["answers"] == ["yes"]
    assert result.tool_events[0].payload["function_call_output_model_visible"] is True
    assert result.tool_events[0].payload["function_call_output"]["answers"]["confirm_path"]["answers"] == ["yes"]


def test_request_user_input_cancel_emits_failed_item_event_when_handler_missing() -> None:
    runtime = SimpleNamespace(
        collaboration_mode="default",
        default_mode_request_user_input=True,
        request_user_input_handler=None,
    )

    result = handle_request_user_input_command(runtime, arg_text=_request_user_input_arg_text())

    assert result.assistant_text == "request_user_input was cancelled before receiving a response"
    assert result.tool_events[0].name == "request_user_input"
    assert result.tool_events[0].ok is False
    assert result.tool_events[0].summary == "request_user_input cancelled"
    assert result.tool_events[0].payload["error"] == "request_user_input was cancelled before receiving a response"

    started = result.item_events[0]
    assert started["type"] == "item.started"
    assert started["item"]["tool"] == "request_user_input"
    assert started["item"]["status"] == "in_progress"

    completed = next(
        event
        for event in result.item_events
        if event["type"] == "item.completed" and event["item"]["type"] == "mcp_tool_call"
    )
    assert completed["type"] == "item.completed"
    assert completed["item"]["tool"] == "request_user_input"
    assert completed["item"]["status"] == "failed"
    assert completed["item"]["result"] is None
    assert completed["item"]["error"]["message"] == "request_user_input was cancelled before receiving a response"
    assert result.tool_events[0].payload["function_call_output_model_visible"] is True
    assert result.tool_events[0].payload["function_call_output"] == "request_user_input was cancelled before receiving a response"

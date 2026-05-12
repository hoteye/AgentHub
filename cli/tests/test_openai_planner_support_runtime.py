from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from cli.agent_cli.providers.openai_planner import (
    OpenAIPlanner,
    _log_responses_request,
    _log_responses_response,
)

def test_openai_planner_support_helpers_preserve_flat_message_and_json_parsing() -> None:
    assert OpenAIPlanner._message_input_item(" assistant ", "hi") == {
        "role": "assistant",
        "content": "hi",
    }
    assert OpenAIPlanner._extract_json_payload("```json\n{\"ok\": true}\n```") == {"ok": True}
    assert OpenAIPlanner._extract_json_payload("prefix {\"count\": 2} suffix") == {"count": 2}

def test_openai_planner_support_helpers_preserve_optional_bool_mapping() -> None:
    assert OpenAIPlanner._optional_bool("YES") is True
    assert OpenAIPlanner._optional_bool("off", True) is False
    assert OpenAIPlanner._optional_bool("unknown", True) is True

def test_openai_planner_support_helpers_log_request_and_response_shapes() -> None:
    log_timeline_mock = MagicMock()
    response = SimpleNamespace(id="resp_123", output=[])

    from unittest.mock import patch

    with patch("cli.agent_cli.providers.openai_planner.timeline_debug_enabled", return_value=True), patch(
        "cli.agent_cli.providers.openai_planner.log_timeline", log_timeline_mock
    ), patch("cli.agent_cli.providers.openai_planner.json_ready", side_effect=lambda payload: payload):
        _log_responses_request(
            "responses.test",
            {
                "input": [{"role": "user", "content": "hello"}],
                "tools": [{"type": "function", "name": "exec_command"}],
                "stream": True,
                "previous_response_id": "resp_prev",
            },
        )
        _log_responses_response("responses.test", response)

    request_call = log_timeline_mock.call_args_list[0]
    response_call = log_timeline_mock.call_args_list[1]

    assert request_call.args[0] == "responses.test.request_raw"
    assert request_call.kwargs["input_count"] == 1
    assert request_call.kwargs["tool_count"] == 1
    assert request_call.kwargs["stream"] is True
    assert request_call.kwargs["previous_response_id"] == "resp_prev"
    assert response_call.args[0] == "responses.test.response_raw"
    assert response_call.kwargs["response_id"] == "resp_123"

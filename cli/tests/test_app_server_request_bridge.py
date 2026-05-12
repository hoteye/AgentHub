from __future__ import annotations

import threading

from cli.agent_cli import app_server_request_bridge
from cli.agent_cli.runtime_core.tool_call_context_runtime import (
    active_app_server_turn_id,
    active_provider_tool_call_id,
)


def test_request_user_input_via_client_uses_active_turn_and_call_ids_and_protocol_question_fields() -> None:
    pending_server_requests: dict[str, object] = {}
    emitted: list[dict[str, object]] = []

    def _emit(message: dict[str, object]) -> None:
        emitted.append(dict(message))
        pending = pending_server_requests[str(message["id"])]
        pending.response_payload = {"answers": {"confirm_path": {"answers": ["yes"]}}}
        pending.response_event.set()

    with active_app_server_turn_id("turn_test_123"):
        with active_provider_tool_call_id("call_test_123"):
            response = app_server_request_bridge._request_user_input_via_client(
                payload={
                    "questions": [
                        {
                            "id": "confirm_path",
                            "header": "Confirm",
                            "question": "Proceed?",
                            "is_other": True,
                            "is_secret": False,
                            "options": [
                                {"label": "Yes (Recommended)", "description": "Continue."},
                                {"label": "No", "description": "Stop."},
                            ],
                        }
                    ]
                },
                thread_id="thread_test_123",
                pending_server_requests_lock=threading.Lock(),
                pending_server_requests=pending_server_requests,
                emit=_emit,
            )

    assert response == {"answers": {"confirm_path": {"answers": ["yes"]}}}
    assert len(emitted) == 1
    request = emitted[0]
    assert request["method"] == "item/tool/requestUserInput"
    params = request["params"]
    assert params["threadId"] == "thread_test_123"
    assert params["turnId"] == "turn_test_123"
    assert params["itemId"] == "call_test_123"
    question = params["questions"][0]
    assert question["id"] == "confirm_path"
    assert question["isOther"] is True
    assert question["isSecret"] is False
    assert "is_other" not in question
    assert "is_secret" not in question
    assert question["options"] == [
        {"label": "Yes (Recommended)", "description": "Continue."},
        {"label": "No", "description": "Stop."},
    ]

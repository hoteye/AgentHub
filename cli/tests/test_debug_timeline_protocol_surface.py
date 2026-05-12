from __future__ import annotations

from cli.agent_cli.debug_timeline import summarize_current_turn_driver_tail, summarize_protocol_items_tail
from cli.agent_cli.environment_context import render_environment_context_update_message

def _message_item(role: str, text: str) -> dict:
    return {
        "type": "message",
        "role": role,
        "content": [{"type": "input_text", "text": text}],
    }

def test_summarize_current_turn_driver_tail_excludes_current_turn_prelude_and_user() -> None:
    items = [
        _message_item("user", "first question"),
        {
            "type": "reasoning",
            "id": "rs_1",
            "content": [{"type": "reasoning", "text": "check previous tool result"}],
        },
        {
            "type": "function_call_output",
            "call_id": "call_pwd_1",
            "output": [{"type": "output_text", "text": "/repo"}],
            "success": True,
        },
        _message_item("assistant", "The directory is /repo."),
        _message_item("developer", "sandbox policy"),
        {
            "type": "reference_context_item",
            "item": {
                "item_type": "workspace_context",
                "path": "/repo",
                "metadata": {"instructions_digest": "digest_1"},
            },
        },
        _message_item(
            "user",
            render_environment_context_update_message(
                None,
                {
                    "cwd": "/repo",
                    "shell": "bash",
                    "current_date": "2026-04-01",
                    "timezone": "Asia/Shanghai",
                    "network_access": "enabled",
                },
            ),
        ),
        _message_item("user", "what was the directory just now"),
    ]

    tail = summarize_current_turn_driver_tail(items, tail_len=8)

    assert [item["type"] for item in tail] == ["reasoning", "function_call_output", "message"]
    assert tail[0]["provider_item_id"] == "rs_1"
    assert tail[1]["call_id"] == "call_pwd_1"
    assert tail[2]["role"] == "assistant"

def test_summarize_protocol_items_tail_surfaces_native_item_previews() -> None:
    tail = summarize_protocol_items_tail(
        [
            {
                "type": "web_search_call",
                "id": "ws_1",
                "status": "completed",
                "action": {"query": "北京时间几点"},
            },
            {
                "type": "shell_call_output",
                "call_id": "shell_1",
                "status": "completed",
                "output": [{"stdout": "hello\n", "stderr": ""}],
            },
        ],
        tail_len=8,
    )

    assert tail[0]["provider_item_id"] == "ws_1"
    assert tail[0]["query_preview"] == "北京时间几点"
    assert tail[1]["call_id"] == "shell_1"
    assert tail[1]["output_preview"] == "hello"

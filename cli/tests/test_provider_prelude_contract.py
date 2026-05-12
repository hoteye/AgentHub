from __future__ import annotations

from cli.agent_cli.provider import (
    build_ordered_request_prelude_items,
    extract_current_turn_prelude_contract,
    request_prelude_contract,
)

def test_build_ordered_request_prelude_items_places_workspace_before_environment() -> None:
    items = build_ordered_request_prelude_items(
        developer_item={
            "type": "message",
            "role": "developer",
            "content": [{"type": "input_text", "text": "developer"}],
        },
        environment_items=[
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "<environment_context><cwd>/repo</cwd></environment_context>"}],
            }
        ],
        workspace_message_items=[
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "REFERENCE_CONTEXT_BASELINE:\n# AENGTHUB.md instructions for /repo"}],
            }
        ],
    )

    assert request_prelude_contract(items)["section_order"] == [
        "developer",
        "workspace_context",
        "environment_context",
    ]

def test_extract_current_turn_prelude_contract_uses_suffix_before_last_user_prompt() -> None:
    input_items = [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "之前的问题"}],
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "之前的回答"}],
        },
        {
            "type": "message",
            "role": "developer",
            "content": [{"type": "input_text", "text": "developer"}],
        },
        {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "# AENGTHUB.md instructions for /repo\n\n<environment_context>\n  <cwd>/repo</cwd>\n</environment_context>",
                }
            ],
        },
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "当前问题"}],
        },
    ]

    assert extract_current_turn_prelude_contract(input_items)["section_order"] == [
        "developer",
        "workspace_context",
        "environment_context",
    ]

def test_extract_current_turn_prelude_contract_accepts_flat_role_content_messages() -> None:
    input_items = [
        {"role": "user", "content": "之前的问题"},
        {"role": "assistant", "content": "之前的回答"},
        {"role": "developer", "content": "developer"},
        {
            "type": "reference_context_item",
            "item": {"item_type": "workspace_context", "cwd": "/repo"},
        },
        {
            "role": "user",
            "content": "<environment_context>\n  <cwd>/repo</cwd>\n</environment_context>",
        },
        {"role": "user", "content": "当前问题"},
    ]

    assert extract_current_turn_prelude_contract(input_items)["section_order"] == [
        "developer",
        "workspace_context",
        "environment_context",
    ]

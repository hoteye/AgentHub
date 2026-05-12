from cli.agent_cli.models import (
    PromptResponse,
    ResponseInputItem,
    ToolEvent,
    compose_turn_events_from_response_items,
    prompt_response_turn_events,
    response_message_item,
)
from cli.agent_cli.models_response_projection import replay_input_items_from_turn_events


def test_compose_turn_events_from_response_items_preserves_commentary_and_reasoning() -> None:
    executed_item_events = [
        {
            "type": "item.started",
            "item": {
                "id": "item_0",
                "type": "mcp_tool_call",
                "server": "local",
                "tool": "grep_files",
                "arguments": {"pattern": "provider"},
                "status": "in_progress",
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "item_0",
                "type": "mcp_tool_call",
                "server": "local",
                "tool": "grep_files",
                "arguments": {"pattern": "provider"},
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": "cli/agent_cli/agent.py\ncli/agent_cli/provider.py",
                        }
                    ]
                },
                "status": "completed",
            },
        },
    ]
    response_items = [
        response_message_item("assistant", "先整理线索", phase="commentary"),
        ResponseInputItem(
            item_type="reasoning",
            role="assistant",
            content=[{"type": "reasoning", "text": "命中 grep 后继续读文件"}],
        ),
        response_message_item("assistant", "最终答案", phase="final_answer"),
    ]

    turn_events = compose_turn_events_from_response_items(
        assistant_text="最终答案",
        response_items=[item for item in response_items if item is not None],
        executed_item_events=executed_item_events,
    )

    completed_types = [
        str((event.get("item") or {}).get("type") or "")
        for event in turn_events
        if event.get("type") == "item.completed"
    ]
    assert completed_types == ["agent_message", "reasoning", "mcp_tool_call", "agent_message"]
    started_item = next(event for event in turn_events if event.get("type") == "item.started")
    assert started_item["item"]["id"] == "item_2"
    final_item = [event for event in turn_events if event.get("type") == "item.completed"][-1]
    assert final_item["item"]["id"] == "item_3"
    assert final_item["item"]["text"] == "最终答案"


def test_compose_turn_events_from_response_items_skips_duplicate_streamed_final_answer() -> None:
    turn_events = compose_turn_events_from_response_items(
        assistant_text="你好！有什么我可以帮你的吗？",
        response_items=[
            response_message_item(
                "assistant",
                "你好！有什么我可以帮你的吗？",
                phase="final_answer",
            )
        ],
        executed_item_events=[
            {
                "type": "item.updated",
                "item": {
                    "id": "msg_1:0",
                    "type": "agent_message",
                    "text": "你好！有什么我可以帮你的吗？",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "msg_1:0",
                    "type": "agent_message",
                    "text": "你好！有什么我可以帮你的吗？",
                },
            },
        ],
    )

    completed_agent_messages = [
        event["item"]
        for event in turn_events
        if event.get("type") == "item.completed"
        and isinstance(event.get("item"), dict)
        and event["item"].get("type") == "agent_message"
    ]
    assert completed_agent_messages == [
        {
            "id": "item_0",
            "type": "agent_message",
            "text": "你好！有什么我可以帮你的吗？",
        }
    ]


def test_compose_turn_events_from_response_items_projects_summary_only_reasoning() -> None:
    turn_events = compose_turn_events_from_response_items(
        assistant_text="最终答案",
        response_items=[
            ResponseInputItem(
                item_type="reasoning",
                role="assistant",
                content=None,
                content_present=True,
                extra={
                    "summary": [{"type": "summary_text", "text": "先查北京时间"}],
                    "encrypted_content": "enc-1",
                    "id": "rs_1",
                    "status": "completed",
                },
            ),
            response_message_item("assistant", "最终答案", phase="final_answer"),
        ],
    )

    reasoning_items = [
        event["item"]
        for event in turn_events
        if event.get("type") == "item.completed"
        and isinstance(event.get("item"), dict)
        and event["item"].get("type") == "reasoning"
    ]
    assert reasoning_items == [
        {
            "id": "item_0",
            "type": "reasoning",
            "text": "先查北京时间",
            "status": "completed",
            "summary": [{"type": "summary_text", "text": "先查北京时间"}],
            "encrypted_content": "enc-1",
            "provider_item_id": "rs_1",
        }
    ]


def test_compose_turn_events_from_response_items_projects_provider_native_web_search_call() -> None:
    turn_events = compose_turn_events_from_response_items(
        assistant_text="最终答案",
        response_items=[
            ResponseInputItem(
                item_type="web_search_call",
                content="",
                extra={
                    "id": "ws_1",
                    "status": "completed",
                    "action": {
                        "type": "search",
                        "query": "北京 今天天气",
                        "queries": ["北京 今天天气"],
                    },
                },
            ),
            response_message_item("assistant", "最终答案", phase="final_answer"),
        ],
    )

    completed_items = [
        event["item"]
        for event in turn_events
        if event.get("type") == "item.completed" and isinstance(event.get("item"), dict)
    ]
    assert completed_items[0] == {
        "id": "ws_1",
        "type": "web_search_call",
        "status": "completed",
        "search_phase": "search_results_received",
        "action": {"type": "search", "query": "北京 今天天气", "queries": ["北京 今天天气"]},
        "query": "北京 今天天气",
    }
    assert completed_items[1]["type"] == "agent_message"


def test_replay_input_items_from_turn_events_preserves_provider_native_web_search_call() -> None:
    replay_items = replay_input_items_from_turn_events(
        [
            {
                "type": "item.completed",
                "item": {
                    "id": "ws_1",
                    "type": "web_search_call",
                    "status": "completed",
                    "query": "北京 今天天气",
                },
            }
        ]
    )

    assert replay_items == [
        {
            "type": "web_search_call",
            "id": "ws_1",
            "status": "completed",
            "action": {
                "type": "search",
                "query": "北京 今天天气",
                "queries": ["北京 今天天气"],
            },
        }
    ]


def test_replay_input_items_from_turn_events_preserves_started_only_provider_native_web_search_call() -> (
    None
):
    replay_items = replay_input_items_from_turn_events(
        [
            {
                "type": "item.started",
                "item": {
                    "id": "ws_1",
                    "type": "web_search_call",
                    "status": "in_progress",
                    "search_phase": "search_dispatched",
                    "action": {
                        "type": "search",
                        "query": "北京 今天天气",
                        "queries": ["北京 今天天气"],
                    },
                },
            }
        ]
    )

    assert replay_items == [
        {
            "type": "web_search_call",
            "id": "ws_1",
            "status": "in_progress",
            "action": {
                "type": "search",
                "query": "北京 今天天气",
                "queries": ["北京 今天天气"],
            },
        }
    ]


def test_replay_input_items_from_turn_events_prefers_completed_provider_native_web_search_call_over_started() -> (
    None
):
    replay_items = replay_input_items_from_turn_events(
        [
            {
                "type": "item.started",
                "item": {
                    "id": "ws_1",
                    "type": "web_search_call",
                    "status": "in_progress",
                    "search_phase": "search_dispatched",
                    "action": {
                        "type": "search",
                        "query": "北京 今天天气",
                        "queries": ["北京 今天天气"],
                    },
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "ws_1",
                    "type": "web_search_call",
                    "status": "completed",
                    "search_phase": "search_results_received",
                    "action": {
                        "type": "search",
                        "query": "北京 今天天气",
                        "queries": ["北京 今天天气"],
                    },
                },
            },
        ]
    )

    assert replay_items == [
        {
            "type": "web_search_call",
            "id": "ws_1",
            "status": "completed",
            "action": {
                "type": "search",
                "query": "北京 今天天气",
                "queries": ["北京 今天天气"],
            },
        }
    ]


def test_replay_input_items_from_turn_events_keeps_completed_web_search_call_when_events_are_reversed() -> (
    None
):
    replay_items = replay_input_items_from_turn_events(
        [
            {
                "type": "item.completed",
                "item": {
                    "id": "ws_1",
                    "type": "web_search_call",
                    "status": "completed",
                    "search_phase": "search_results_received",
                    "action": {
                        "type": "search",
                        "query": "北京 今天天气",
                        "queries": ["北京 今天天气"],
                    },
                },
            },
            {
                "type": "item.started",
                "item": {
                    "id": "ws_1",
                    "type": "web_search_call",
                    "status": "in_progress",
                    "search_phase": "search_dispatched",
                    "action": {
                        "type": "search",
                        "query": "北京 今天天气",
                        "queries": ["北京 今天天气"],
                    },
                },
            },
        ]
    )

    assert replay_items == [
        {
            "type": "web_search_call",
            "id": "ws_1",
            "status": "completed",
            "action": {
                "type": "search",
                "query": "北京 今天天气",
                "queries": ["北京 今天天气"],
            },
        }
    ]


def test_compose_turn_events_from_response_items_projects_provider_shell_items_to_command_execution() -> (
    None
):
    turn_events = compose_turn_events_from_response_items(
        assistant_text="最终答案",
        response_items=[
            ResponseInputItem(
                item_type="shell_call",
                content="",
                extra={
                    "call_id": "call_shell_1",
                    "status": "completed",
                    "action": {
                        "type": "exec",
                        "command": ["python", "-V"],
                        "timeout_ms": 1000,
                    },
                },
            ),
            ResponseInputItem(
                item_type="shell_call_output",
                content="",
                extra={
                    "call_id": "call_shell_1",
                    "status": "completed",
                    "output": [
                        {
                            "stdout": "Python 3.13.0\n",
                            "stderr": "",
                            "outcome": {"type": "exit", "exit_code": 0},
                        }
                    ],
                },
            ),
            response_message_item("assistant", "最终答案", phase="final_answer"),
        ],
    )

    completed_items = [
        event["item"]
        for event in turn_events
        if event.get("type") == "item.completed" and isinstance(event.get("item"), dict)
    ]
    assert [item["type"] for item in completed_items] == [
        "command_execution",
        "command_execution",
        "agent_message",
    ]
    assert completed_items[0]["id"] == "call_shell_1"
    assert completed_items[0]["command"] == "python -V"
    assert completed_items[1]["id"] == "call_shell_1"
    assert completed_items[1]["aggregated_output"] == "Python 3.13.0\n"
    assert completed_items[1]["exit_code"] == 0


def test_prompt_response_turn_events_reuses_response_item_composition_for_tool_turns() -> None:
    response = PromptResponse(
        user_text="inspect provider",
        commentary_text="先搜索",
        assistant_text="最终答案",
        response_items=[
            response_message_item("assistant", "先搜索", phase="commentary"),
            ResponseInputItem(
                item_type="reasoning",
                role="assistant",
                content=[{"type": "reasoning", "text": "需要先 grep 再 read"}],
            ),
            response_message_item("assistant", "最终答案", phase="final_answer"),
        ],
        tool_events=[
            ToolEvent(
                name="grep_files",
                ok=True,
                summary="paths=2",
                payload={
                    "pattern": "provider",
                    "paths": ["cli/agent_cli/agent.py", "cli/agent_cli/provider.py"],
                    "text": "cli/agent_cli/agent.py\ncli/agent_cli/provider.py",
                },
            )
        ],
    )

    turn_events = prompt_response_turn_events(response)

    completed_types = [
        str((event.get("item") or {}).get("type") or "")
        for event in turn_events
        if event.get("type") == "item.completed"
    ]
    assert completed_types == ["agent_message", "reasoning", "mcp_tool_call", "agent_message"]


def test_prompt_response_turn_events_backfills_agent_message_before_terminal_event() -> None:
    response = PromptResponse(
        user_text="child smoke",
        assistant_text="handled child smoke",
        turn_events=[{"type": "turn.completed", "usage": {"output_tokens": 3}}],
    )

    turn_events = prompt_response_turn_events(response)

    assert turn_events == [
        {
            "type": "item.completed",
            "item": {
                "id": "item_0",
                "type": "agent_message",
                "text": "handled child smoke",
                "phase": "final_answer",
            },
        },
        {"type": "turn.completed", "usage": {"output_tokens": 3}},
    ]


def test_prompt_response_turn_events_does_not_duplicate_existing_agent_message() -> None:
    response = PromptResponse(
        user_text="child smoke",
        assistant_text="handled child smoke",
        turn_events=[
            {
                "type": "item.completed",
                "item": {"id": "item_0", "type": "agent_message", "text": "handled child smoke"},
            },
            {"type": "turn.completed"},
        ],
    )

    turn_events = prompt_response_turn_events(response)

    assert turn_events == response.turn_events


def test_compose_turn_events_from_response_items_auto_completes_open_todo_list() -> None:
    turn_events = compose_turn_events_from_response_items(
        assistant_text="Plan updated",
        response_items=[response_message_item("assistant", "Plan updated", phase="final_answer")],
        executed_item_events=[
            {
                "type": "item.started",
                "item": {
                    "id": "item_0",
                    "type": "todo_list",
                    "items": [
                        {"text": "inspect", "completed": False},
                        {"text": "patch", "completed": False},
                    ],
                },
            },
            {
                "type": "item.updated",
                "item": {
                    "id": "item_0",
                    "type": "todo_list",
                    "items": [
                        {"text": "inspect", "completed": True},
                        {"text": "patch", "completed": False},
                    ],
                },
            },
        ],
    )

    todo_events = [
        event
        for event in turn_events
        if isinstance(event.get("item"), dict) and event["item"].get("type") == "todo_list"
    ]
    assert [event["type"] for event in todo_events] == [
        "item.started",
        "item.updated",
        "item.completed",
    ]
    assert todo_events[0]["item"]["id"] == "item_0"
    assert todo_events[1]["item"]["id"] == "item_0"
    assert todo_events[2]["item"]["id"] == "item_0"
    assert todo_events[2]["item"]["items"] == [
        {"text": "inspect", "completed": True},
        {"text": "patch", "completed": False},
    ]

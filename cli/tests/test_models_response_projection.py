from __future__ import annotations

from cli.agent_cli.core.turn_engine_item_events import _provisional_started_item_event
from cli.agent_cli.models import (
    ToolEvent,
    replay_input_items_from_turn_events,
    response_items_with_tool_outputs,
)
from cli.agent_cli.models_response_projection import (
    _call_id_needs_tool_event_override,
    _reasoning_retention_diagnostic_key,
    shared_replay_reasoning_projection,
)
from cli.agent_cli.providers.adapters import openai_responses_input_runtime


def _reasoning_turn_events() -> list[dict]:
    return [
        {
            "type": "item.completed",
            "item": {
                "type": "reasoning",
                "summary": [
                    {
                        "type": "summary_text",
                        "text": "Inspect the workspace and plan the next step.",
                    }
                ],
                "encrypted_content": "gAAAAA-test-encrypted-content",
                "content": [
                    {
                        "type": "reasoning",
                        "text": "Inspect the workspace and plan the next step.",
                    }
                ],
            },
        },
        {
            "type": "item.completed",
            "item": {
                "type": "agent_message",
                "text": "我先看一下当前目录，再继续改脚本。",
            },
        },
    ]


def _typed_message_input_item(role: str, content: object) -> dict[str, object] | None:
    if isinstance(content, list):
        return {"type": "message", "role": role, "content": content}
    block_type = "input_text" if role == "user" else "output_text"
    return {
        "type": "message",
        "role": role,
        "content": [{"type": block_type, "text": str(content or "")}],
    }


def test_second_turn_replay_items_preserve_sanitized_reasoning_replay_items() -> None:
    items = replay_input_items_from_turn_events(_reasoning_turn_events())

    assert items == [
        {
            "type": "reasoning",
            "content": [
                {"type": "reasoning", "text": "Inspect the workspace and plan the next step."}
            ],
            "summary": [
                {"type": "summary_text", "text": "Inspect the workspace and plan the next step."}
            ],
            "encrypted_content": "gAAAAA-test-encrypted-content",
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "我先看一下当前目录，再继续改脚本。"}],
        },
    ]


def test_response_items_with_tool_outputs_preserves_sanitized_reasoning_replay_items() -> None:
    response_items = [
        {
            "type": "reasoning",
            "content": [
                {"type": "reasoning", "text": "Inspect the workspace and plan the next step."}
            ],
            "summary": [
                {"type": "summary_text", "text": "Inspect the workspace and plan the next step."}
            ],
            "encrypted_content": "gAAAAA-test-encrypted-content",
            "id": "rs_1",
            "status": "completed",
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "我先看一下当前目录，再继续改脚本。"}],
        },
    ]
    turn_events = _reasoning_turn_events() + [
        {
            "type": "item.completed",
            "item": {
                "type": "command_execution",
                "call_id": "call_exec_1",
                "command": "pwd",
                "aggregated_output": "/tmp/workspace\n",
                "exit_code": 0,
                "status": "completed",
            },
        }
    ]

    items = response_items_with_tool_outputs(response_items, turn_events, tool_events=[])

    assert [item.get("type") for item in items] == [
        "reasoning",
        "function_call",
        "function_call_output",
        "message",
    ]
    assert items[0] == {
        "type": "reasoning",
        "content": [{"type": "reasoning", "text": "Inspect the workspace and plan the next step."}],
        "summary": [
            {"type": "summary_text", "text": "Inspect the workspace and plan the next step."}
        ],
        "encrypted_content": "gAAAAA-test-encrypted-content",
    }
    assert "id" not in items[0]
    assert "status" not in items[0]


def test_second_turn_replay_items_fail_closed_for_empty_reasoning_turn_events() -> None:
    items = replay_input_items_from_turn_events(
        [
            {
                "type": "item.completed",
                "item": {
                    "type": "reasoning",
                    "summary": [],
                    "content": [],
                },
            }
        ]
    )

    assert items == []


def test_second_turn_replay_items_strip_provider_rejected_reasoning_fields() -> None:
    items = replay_input_items_from_turn_events(
        [
            {
                "type": "item.completed",
                "item": {
                    "type": "reasoning",
                    "provider_item_id": "rs_1",
                    "status": "completed",
                    "summary": [{"type": "summary_text", "text": "Inspect first"}],
                    "encrypted_content": "enc-1",
                    "content": [{"type": "reasoning", "text": "Inspect first"}],
                },
            }
        ]
    )

    assert items == [
        {
            "type": "reasoning",
            "content": [{"type": "reasoning", "text": "Inspect first"}],
            "summary": [{"type": "summary_text", "text": "Inspect first"}],
            "encrypted_content": "enc-1",
        }
    ]


def test_shared_replay_reasoning_projection_fail_closed_without_encrypted_content() -> None:
    projection = shared_replay_reasoning_projection(
        {
            "type": "reasoning",
            "content": [{"type": "reasoning", "text": "Inspect first"}],
            "summary": [{"type": "summary_text", "text": "Inspect first"}],
        }
    )

    assert projection["input_item"] is None
    assert projection["diagnostic"] == {
        "item_type": "reasoning",
        "source": "tool_history_projection",
        "retention": "stripped",
        "guard": "missing_encrypted_content",
        "summary_present": True,
        "content_present": True,
        "detail": "shared replay stripped previous-turn reasoning because encrypted_content is missing",
    }


def test_reasoning_retention_diagnostic_key_falls_back_to_repr_for_non_jsonable_values() -> None:
    key = _reasoning_retention_diagnostic_key({"example": {1, 2}})

    assert key == "{'example': {1, 2}}"


def test_response_items_with_tool_outputs_restores_missing_call_item_before_existing_output() -> (
    None
):
    response_items = [
        {
            "type": "function_call_output",
            "call_id": "call_read_1",
            "output": "L1: original",
            "success": True,
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "文件内容为：original"}],
        },
    ]
    tool_events = [
        {
            "name": "read_file",
            "ok": True,
            "summary": "读取完成",
            "payload": {
                "provider_call_id": "call_read_1",
                "arguments": {"file_path": "/tmp/f.txt"},
            },
        }
    ]

    items = response_items_with_tool_outputs(
        response_items, turn_events=[], tool_events=tool_events
    )

    assert [item.get("type") for item in items] == [
        "function_call",
        "function_call_output",
        "message",
    ]
    assert items[0]["call_id"] == "call_read_1"
    assert items[0]["name"] == "read_file"


def test_response_items_with_tool_outputs_drops_unpaired_existing_tool_call_input() -> None:
    response_items = [
        {
            "type": "function_call",
            "call_id": "call_visible_child_1",
            "name": "spawn_child_tab",
            "arguments": '{"task": "inspect README"}',
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "queued"}],
        },
    ]

    items = response_items_with_tool_outputs(response_items, turn_events=[], tool_events=[])

    assert [item.get("type") for item in items] == ["message"]


def test_response_items_with_tool_outputs_preserves_paired_existing_tool_call_input() -> None:
    response_items = [
        {
            "type": "function_call",
            "call_id": "call_visible_child_1",
            "name": "spawn_child_tab",
            "arguments": '{"task": "inspect README"}',
        },
        {
            "type": "function_call_output",
            "call_id": "call_visible_child_1",
            "output": "visible child tab spawned",
            "success": True,
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "queued"}],
        },
    ]

    items = response_items_with_tool_outputs(response_items, turn_events=[], tool_events=[])

    assert [item.get("type") for item in items] == [
        "function_call",
        "function_call_output",
        "message",
    ]
    assert items[0]["call_id"] == "call_visible_child_1"
    assert items[1]["call_id"] == "call_visible_child_1"


def test_response_items_with_tool_outputs_reuses_tool_event_provider_call_id_for_image_ready_replay() -> (
    None
):
    image_artifact = {
        "path": "/tmp/sample.png",
        "mime_type": "image/png",
        "size_bytes": 42,
        "width": 10,
        "height": 12,
        "image_url": "data:image/png;base64,AAA",
        "detail": "high",
    }
    response_items = [
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "image ready"}],
        }
    ]
    turn_events = [
        {
            "type": "item.completed",
            "item": {
                "id": "item_1",
                "type": "mcp_tool_call",
                "tool": "view_image",
                "arguments": {"path": "/tmp/sample.png"},
                "result": {"structured_content": {"image_artifacts": [image_artifact]}},
                "status": "completed",
            },
        },
        {
            "type": "item.completed",
            "item": {
                "type": "agent_message",
                "text": "image ready",
            },
        },
    ]
    tool_events = [
        {
            "name": "view_image",
            "ok": True,
            "summary": "image ready",
            "payload": {
                "provider_call_id": "call_view_image_1",
                "ok": True,
                "path": "/tmp/sample.png",
                "requested_path": "sample.png",
                "image_artifacts": [image_artifact],
            },
        }
    ]

    items = response_items_with_tool_outputs(response_items, turn_events, tool_events)

    function_call = next(item for item in items if item.get("type") == "function_call")
    function_output = next(item for item in items if item.get("type") == "function_call_output")
    assert function_call["call_id"] == "call_view_image_1"
    assert function_output["call_id"] == "call_view_image_1"


def test_response_items_with_tool_outputs_prefers_existing_provider_exec_call_id_over_projected_duplicate() -> (
    None
):
    response_items = [
        {
            "type": "function_call",
            "call_id": "call_exec_provider_1",
            "name": "exec_command",
            "arguments": (
                '{"cmd": "pytest -q", "workdir": "/tmp/project", '
                '"yield_time_ms": 500, "max_output_tokens": 4000}'
            ),
            "status": "completed",
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "done"}],
        },
    ]
    turn_events = [
        {
            "type": "item.completed",
            "item": {
                "id": "turn_exec_1",
                "call_id": "turn_exec_1",
                "type": "command_execution",
                "status": "completed",
                "command": "pytest -q",
                "function_call_name": "exec_command",
                "function_call_arguments": {
                    "cmd": "pytest -q",
                    "workdir": "/tmp/project",
                    "yield_time_ms": 500,
                    "max_output_tokens": 4000,
                    "login": True,
                    "tty": False,
                },
                "aggregated_output": "48 passed\n",
                "exit_code": 0,
            },
        }
    ]

    items = response_items_with_tool_outputs(response_items, turn_events, tool_events=[])

    assert [item.get("type") for item in items] == [
        "function_call",
        "function_call_output",
        "message",
    ]
    assert items[0]["call_id"] == "call_exec_provider_1"
    assert items[1]["call_id"] == "call_exec_provider_1"
    assert items[1]["success"] is True


def test_replay_input_items_from_turn_events_preserves_update_plan_from_todo_list_events() -> None:
    turn_events = [
        {
            "type": "item.started",
            "item": {
                "id": "item_plan_1",
                "type": "todo_list",
                "explanation": "sync",
                "plan": [
                    {"step": "inspect", "status": "completed"},
                    {"step": "patch", "status": "in_progress"},
                ],
                "items": [
                    {"text": "inspect", "completed": True},
                    {"text": "patch", "completed": False},
                ],
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "item_plan_1",
                "type": "todo_list",
                "explanation": "sync",
                "plan": [
                    {"step": "inspect", "status": "completed"},
                    {"step": "patch", "status": "in_progress"},
                ],
                "items": [
                    {"text": "inspect", "completed": True},
                    {"text": "patch", "completed": False},
                ],
            },
        },
        {
            "type": "item.completed",
            "item": {
                "type": "agent_message",
                "text": "done",
            },
        },
    ]

    items = replay_input_items_from_turn_events(turn_events)

    assert [item.get("type") for item in items] == [
        "function_call",
        "function_call_output",
        "message",
    ]
    assert items[0]["name"] == "update_plan"
    assert items[0]["call_id"] == "item_plan_1"
    assert (
        items[0]["arguments"]
        == '{"explanation": "sync", "plan": [{"step": "inspect", "status": "completed"}, {"step": "patch", "status": "in_progress"}]}'
    )
    assert items[1]["call_id"] == "item_plan_1"
    assert items[1]["output"] == "Plan updated"
    assert items[1]["success"] is True


def test_replay_input_items_from_turn_events_prefers_provider_function_call_over_duplicate_todo_projection() -> (
    None
):
    turn_events = [
        {
            "type": "item.completed",
            "item": {
                "id": "item_1",
                "call_id": "call_plan_provider_1",
                "type": "function_call",
                "name": "update_plan",
                "arguments": '{"plan": [{"step": "inspect", "status": "in_progress"}]}',
                "status": "completed",
            },
        },
        {
            "type": "item.started",
            "item": {
                "id": "item_plan_1",
                "type": "todo_list",
                "plan": [
                    {"step": "inspect", "status": "in_progress"},
                ],
                "items": [
                    {"text": "inspect", "completed": False},
                ],
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "item_plan_1",
                "type": "todo_list",
                "plan": [
                    {"step": "inspect", "status": "in_progress"},
                ],
                "items": [
                    {"text": "inspect", "completed": False},
                ],
            },
        },
    ]

    items = replay_input_items_from_turn_events(turn_events)

    assert [item.get("type") for item in items] == [
        "function_call",
        "function_call_output",
    ]
    assert items[0]["call_id"] == "call_plan_provider_1"
    assert items[0]["name"] == "update_plan"
    assert items[1]["call_id"] == "call_plan_provider_1"
    assert items[1]["output"] == "Plan updated"


def test_replay_input_items_from_turn_events_preserves_full_exec_command_arguments() -> None:
    turn_events = [
        {
            "type": "item.started",
            "item": {
                "id": "call_exec_1",
                "call_id": "call_exec_1",
                "type": "command_execution",
                "status": "in_progress",
                "command": "pytest -q",
                "function_call_name": "exec_command",
                "function_call_arguments": {
                    "cmd": "pytest -q",
                    "workdir": "/tmp/project",
                    "yield_time_ms": 500,
                    "max_output_tokens": 4000,
                    "login": True,
                    "tty": False,
                },
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "call_exec_1",
                "call_id": "call_exec_1",
                "type": "command_execution",
                "status": "completed",
                "command": "pytest -q",
                "function_call_name": "exec_command",
                "function_call_arguments": {
                    "cmd": "pytest -q",
                    "workdir": "/tmp/project",
                    "yield_time_ms": 500,
                    "max_output_tokens": 4000,
                    "login": True,
                    "tty": False,
                },
                "aggregated_output": "48 passed\n",
                "exit_code": 0,
            },
        },
    ]

    items = replay_input_items_from_turn_events(turn_events)

    assert [item.get("type") for item in items] == ["function_call", "function_call_output"]
    assert items[0]["name"] == "exec_command"
    assert items[0]["call_id"] == "call_exec_1"
    assert items[0]["arguments"] == (
        '{"cmd": "pytest -q", "workdir": "/tmp/project", "yield_time_ms": 500, '
        '"max_output_tokens": 4000, "login": true, "tty": false}'
    )
    assert items[1]["call_id"] == "call_exec_1"
    assert items[1]["success"] is True


def test_response_items_with_tool_outputs_avoids_duplicate_provider_and_structured_tool_calls_from_turn_events() -> (
    None
):
    response_items = [
        {
            "type": "function_call",
            "call_id": "call_plan_provider_1",
            "name": "update_plan",
            "arguments": '{"plan": [{"step": "inspect", "status": "in_progress"}]}',
            "id": "item_1",
            "status": "completed",
        },
        {
            "type": "function_call",
            "call_id": "call_exec_provider_1",
            "name": "exec_command",
            "arguments": '{"cmd": "pwd"}',
            "id": "item_2",
            "status": "completed",
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "done"}],
        },
    ]
    turn_events = [
        {
            "type": "item.completed",
            "item": {
                "id": "item_1",
                "call_id": "call_plan_provider_1",
                "type": "function_call",
                "name": "update_plan",
                "arguments": '{"plan": [{"step": "inspect", "status": "in_progress"}]}',
                "status": "completed",
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "item_plan_1",
                "type": "todo_list",
                "plan": [
                    {"step": "inspect", "status": "in_progress"},
                ],
                "items": [
                    {"text": "inspect", "completed": False},
                ],
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "item_2",
                "call_id": "call_exec_provider_1",
                "type": "function_call",
                "name": "exec_command",
                "arguments": '{"cmd": "pwd"}',
                "status": "completed",
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "turn_exec_1",
                "call_id": "turn_exec_1",
                "type": "command_execution",
                "status": "completed",
                "command": "pwd",
                "function_call_name": "exec_command",
                "function_call_arguments": {
                    "cmd": "pwd",
                },
                "aggregated_output": "/tmp/project\n",
                "exit_code": 0,
            },
        },
    ]

    items = response_items_with_tool_outputs(response_items, turn_events, tool_events=[])

    assert [item.get("type") for item in items] == [
        "function_call",
        "function_call",
        "function_call_output",
        "function_call_output",
        "message",
    ]
    assert [item.get("call_id") for item in items[:4]] == [
        "call_plan_provider_1",
        "call_exec_provider_1",
        "call_plan_provider_1",
        "call_exec_provider_1",
    ]
    assert (
        len(
            [
                item
                for item in items
                if item.get("type") == "function_call" and item.get("name") == "update_plan"
            ]
        )
        == 1
    )
    assert (
        len(
            [
                item
                for item in items
                if item.get("type") == "function_call" and item.get("name") == "exec_command"
            ]
        )
        == 1
    )


def test_replay_input_items_from_turn_events_preserves_write_stdin_name_and_arguments() -> None:
    turn_events = [
        {
            "type": "item.completed",
            "item": {
                "id": "call_write_1",
                "call_id": "call_write_1",
                "type": "command_execution",
                "status": "completed",
                "command": "/write_stdin session_1",
                "function_call_name": "write_stdin",
                "function_call_arguments": {
                    "session_id": "session_1",
                    "chars": "",
                    "yield_time_ms": 1000,
                    "max_output_tokens": 8000,
                },
                "aggregated_output": "still running\n",
            },
        },
    ]

    items = replay_input_items_from_turn_events(turn_events)

    assert [item.get("type") for item in items] == ["function_call", "function_call_output"]
    assert items[0]["name"] == "write_stdin"
    assert items[0]["call_id"] == "call_write_1"
    assert items[0]["arguments"] == (
        '{"session_id": "session_1", "chars": "", "yield_time_ms": 1000, "max_output_tokens": 8000}'
    )
    assert items[1]["call_id"] == "call_write_1"


def test_response_items_with_tool_outputs_preserves_write_stdin_metadata_from_provisional_command_execution() -> (
    None
):
    write_arguments = {
        "session_id": "session_1",
        "chars": "",
        "yield_time_ms": 1000,
        "max_output_tokens": 4000,
    }
    turn_events = [
        _provisional_started_item_event(
            tool_name="write_stdin",
            arguments=write_arguments,
            command_text="/write_stdin session_1 '' --yield-time-ms 1000 --max-output-tokens 4000",
            item_id="item_5",
        ),
        {
            "type": "item.completed",
            "item": {
                "id": "item_5",
                "type": "command_execution",
                "command": "write_stdin running session_1",
                "aggregated_output": "",
                "exit_code": None,
                "status": "completed",
            },
        },
    ]

    items = response_items_with_tool_outputs(
        [],
        turn_events,
        tool_events=[
            ToolEvent(
                name="write_stdin",
                ok=True,
                summary="write_stdin running session_1",
                payload={
                    "provider_call_id": "call_write_provider_1",
                    "provider_tool_type": "function_call",
                    "function_call_name": "write_stdin",
                    "function_call_arguments": dict(write_arguments),
                    "function_call_output": "Process running with session ID session_1\nOutput:\n",
                },
            )
        ],
    )

    assert items == [
        {
            "type": "function_call",
            "name": "write_stdin",
            "call_id": "call_write_provider_1",
            "arguments": (
                '{"session_id": "session_1", "chars": "", "yield_time_ms": 1000, "max_output_tokens": 4000}'
            ),
            "content": [],
        },
        {
            "type": "function_call_output",
            "call_id": "call_write_provider_1",
            "output": "Process running with session ID session_1\nOutput:\n",
            "success": True,
            "content": [],
        },
    ]


def test_response_items_with_tool_outputs_promotes_structured_apply_patch_turn_events_to_provider_function_call() -> (
    None
):
    structured_arguments = {
        "file_path": "notes.txt",
        "content": "hello\n",
    }
    turn_events = [
        {
            "type": "item.started",
            "item": {
                "id": "item_patch_1",
                "type": "mcp_tool_call",
                "tool": "apply_patch",
                "status": "in_progress",
                "arguments": {
                    "operation": "file_write",
                    "file_path": "notes.txt",
                    "content": "hello\n",
                },
                "result": None,
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "item_patch_1",
                "type": "mcp_tool_call",
                "tool": "apply_patch",
                "status": "completed",
                "arguments": dict(structured_arguments),
                "result": {
                    "content": [{"type": "text", "text": "apply_patch files=1"}],
                    "structured_content": {
                        "request_kind": "structured_write",
                        "function_call_name": "apply_patch",
                        "function_call_arguments": dict(structured_arguments),
                    },
                },
            },
        },
    ]

    items = response_items_with_tool_outputs(
        [],
        turn_events,
        tool_events=[
            ToolEvent(
                name="apply_patch",
                ok=True,
                summary="apply_patch files=1",
                payload={
                    "provider_call_id": "call_patch_provider_1",
                    "provider_tool_type": "function_call",
                    "function_call_name": "apply_patch",
                    "function_call_arguments": dict(structured_arguments),
                    "function_call_output": "Success. Updated the following files:\nA notes.txt\n",
                },
            )
        ],
    )

    assert items == [
        {
            "type": "function_call",
            "name": "apply_patch",
            "call_id": "call_patch_provider_1",
            "arguments": '{"file_path": "notes.txt", "content": "hello\\n"}',
            "content": [],
        },
        {
            "type": "function_call_output",
            "call_id": "call_patch_provider_1",
            "output": "Success. Updated the following files:\nA notes.txt\n",
            "success": True,
            "content": [],
        },
    ]


def test_response_items_with_tool_outputs_prefers_provider_apply_patch_function_call_for_raw_patch() -> (
    None
):
    patch_text = "*** Begin Patch\n*** Add File: notes.txt\n+hello\n*** End Patch"
    turn_events = [
        {
            "type": "item.started",
            "item": {
                "id": "item_patch_1",
                "type": "mcp_tool_call",
                "tool": "apply_patch",
                "status": "in_progress",
                "arguments": {
                    "patch": "",
                    "operation": "patch",
                },
                "result": None,
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "item_patch_1",
                "type": "mcp_tool_call",
                "tool": "apply_patch",
                "status": "completed",
                "arguments": {
                    "patch": patch_text,
                },
                "result": {
                    "content": [{"type": "text", "text": "apply_patch files=1"}],
                    "structured_content": {
                        "request_kind": "raw_patch",
                        "function_call_name": "apply_patch",
                        "function_call_arguments": {
                            "patch": patch_text,
                        },
                    },
                },
            },
        },
    ]

    items = response_items_with_tool_outputs(
        [],
        turn_events,
        tool_events=[
            ToolEvent(
                name="apply_patch",
                ok=True,
                summary="apply_patch files=1",
                payload={
                    "provider_call_id": "call_patch_provider_1",
                    "provider_tool_type": "function_call",
                    "function_call_name": "apply_patch",
                    "function_call_arguments": {
                        "patch": patch_text,
                    },
                    "function_call_output": "Success. Updated the following files:\nA notes.txt\n",
                },
            )
        ],
    )

    assert items == [
        {
            "type": "function_call",
            "name": "apply_patch",
            "call_id": "call_patch_provider_1",
            "arguments": '{"patch": "*** Begin Patch\\n*** Add File: notes.txt\\n+hello\\n*** End Patch"}',
            "content": [],
        },
        {
            "type": "function_call_output",
            "call_id": "call_patch_provider_1",
            "output": "Success. Updated the following files:\nA notes.txt\n",
            "success": True,
            "content": [],
        },
    ]


def test_replay_input_items_from_turn_events_drops_synthetic_function_call_id_field() -> None:
    turn_events = [
        {
            "type": "item.completed",
            "item": {
                "id": "item_2",
                "call_id": "call_exec_provider_1",
                "type": "function_call",
                "name": "exec_command",
                "arguments": '{"cmd":"pwd"}',
                "status": "completed",
            },
        },
        {
            "type": "item.completed",
            "item": {
                "type": "function_call_output",
                "call_id": "call_exec_provider_1",
                "output": "Process exited with code 0\nOutput:\n/tmp/project\n",
            },
        },
    ]

    items = replay_input_items_from_turn_events(turn_events)

    assert items[0]["type"] == "function_call"
    assert items[0]["call_id"] == "call_exec_provider_1"
    assert "id" not in items[0]


def test_response_items_with_tool_outputs_drops_synthetic_tool_item_ids() -> None:
    response_items = [
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "done"}],
        },
    ]
    turn_events = [
        {
            "type": "item.completed",
            "item": {
                "id": "item_2",
                "call_id": "call_exec_provider_1",
                "type": "function_call",
                "name": "exec_command",
                "arguments": '{"cmd":"pwd"}',
                "status": "completed",
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "item_4",
                "call_id": "call_plan_provider_1",
                "type": "function_call",
                "name": "update_plan",
                "arguments": '{"plan":[{"step":"inspect","status":"completed"}]}',
                "status": "completed",
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "item_exec_1",
                "call_id": "item_exec_1",
                "type": "command_execution",
                "status": "completed",
                "command": "pwd",
                "function_call_name": "exec_command",
                "function_call_arguments": {"cmd": "pwd"},
                "aggregated_output": "/tmp/project\n",
                "exit_code": 0,
            },
        },
        {
            "type": "item.completed",
            "item": {
                "id": "item_plan_1",
                "type": "todo_list",
                "plan": [{"step": "inspect", "status": "completed"}],
                "items": [{"text": "inspect", "completed": True}],
            },
        },
    ]

    items = response_items_with_tool_outputs(response_items, turn_events, tool_events=[])

    function_calls = [item for item in items if item.get("type") == "function_call"]
    assert [item.get("call_id") for item in function_calls] == [
        "call_exec_provider_1",
        "call_plan_provider_1",
    ]
    assert all("id" not in item for item in function_calls)


def test_openai_responses_input_runtime_drops_synthetic_function_call_id() -> None:
    normalized = openai_responses_input_runtime.normalize_single_input_item(
        {
            "type": "function_call",
            "id": "item_2",
            "call_id": "call_exec_provider_1",
            "name": "exec_command",
            "arguments": '{"cmd":"pwd"}',
            "status": "completed",
        },
        reference_parity=False,
        typed_message_input_item_fn=_typed_message_input_item,
        workspace_context_message_text_fn=lambda _payload, _reference_parity: "",
    )

    assert normalized == {
        "type": "function_call",
        "call_id": "call_exec_provider_1",
        "name": "exec_command",
        "arguments": '{"cmd":"pwd"}',
        "status": "completed",
    }


def test_call_id_needs_tool_event_override_only_matches_explicit_item_namespace() -> None:
    assert _call_id_needs_tool_event_override("item_1") is True
    assert _call_id_needs_tool_event_override("item_plan_1") is True
    assert _call_id_needs_tool_event_override("item-1") is True
    assert _call_id_needs_tool_event_override("items_1") is False
    assert _call_id_needs_tool_event_override("itemized_1") is False

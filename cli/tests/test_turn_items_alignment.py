from __future__ import annotations

import json

from cli.agent_cli.core.turn_items import (
    FunctionCallItem,
    FunctionCallOutputItem,
    MessageItem,
    ReasoningItem,
    turn_item_from_dict,
)
from cli.agent_cli.models import (
    CommandExecutionResult,
    FunctionCallOutputPayload,
    ResponseInputItem,
    ToolEvent,
    function_call_input_items_from_tool_events,
    function_call_input_items_from_turn_events,
    function_call_output_content_items_to_text,
    response_items_with_tool_outputs,
    tool_events_to_turn_events,
    tool_output_input_items_from_tool_events,
    tool_output_input_items_from_turn_events,
)
from cli.agent_cli.providers.tool_turn_events import ToolTurnEventsMixin


class _DummyToolTurnEvents(ToolTurnEventsMixin):
    pass


def test_message_item_roundtrip_user() -> None:
    raw = {
        "type": "message",
        "role": "user",
        "content": [{"type": "input_text", "text": " hi  there "}],
    }
    item = MessageItem.from_dict(raw)
    assert item.role == "user"
    assert item.text == "hi there"
    out = item.to_dict()
    assert out["type"] == "message"
    assert out["role"] == "user"
    assert out["content"][0]["type"] == "input_text"
    assert out["content"][0]["text"] == "hi there"


def test_message_item_roundtrip_assistant() -> None:
    raw = {
        "type": "message",
        "role": "assistant",
        "content": [{"type": "output_text", "text": " ok "}],
    }
    item = MessageItem.from_dict(raw)
    assert item.role == "assistant"
    assert item.text == "ok"
    out = item.to_dict()
    assert out["content"][0]["type"] == "output_text"
    assert out["content"][0]["text"] == "ok"


def test_reasoning_item_roundtrip() -> None:
    raw = {
        "type": "reasoning",
        "content": [
            {"type": "reasoning", "text": " step1 "},
            {"type": "reasoning", "text": "step2"},
        ],
    }
    item = ReasoningItem.from_dict(raw)
    assert item.text == "step1 step2"
    out = item.to_dict()
    assert out["type"] == "reasoning"
    assert out["content"][0]["text"] == "step1 step2"


def test_response_input_reasoning_to_dict_strips_provider_rejected_fields() -> None:
    item = ResponseInputItem.from_dict(
        {
            "type": "reasoning",
            "id": "rs_123",
            "status": "completed",
            "summary": [{"type": "summary_text", "text": "先查北京时间"}],
            "encrypted_content": "enc-1",
            "content": None,
        }
    )

    assert item.to_dict() == {
        "type": "reasoning",
        "summary": [{"type": "summary_text", "text": "先查北京时间"}],
        "encrypted_content": "enc-1",
        "content": None,
    }


def test_function_call_item_roundtrip() -> None:
    raw = {
        "type": "function_call",
        "name": "file_list",
        "call_id": "abc",
        "arguments": {"path": ".", "limit": 5},
    }
    item = FunctionCallItem.from_dict(raw)
    assert item.name == "file_list"
    assert item.call_id == "abc"
    assert json.loads(item.arguments)["limit"] == 5
    out = item.to_dict()
    assert out["type"] == "function_call"
    assert out["name"] == "file_list"
    assert out["call_id"] == "abc"
    assert json.loads(out["arguments"])["path"] == "."


def test_function_call_item_accepts_string_arguments() -> None:
    raw = {
        "type": "function_call",
        "name": "file_list",
        "call_id": "abc",
        "arguments": '  {"path":"."} ',
    }
    item = FunctionCallItem.from_dict(raw)
    assert json.loads(item.arguments)["path"] == "."
    out = item.to_dict()
    assert out["arguments"].startswith("{")


def test_function_call_output_roundtrip() -> None:
    raw = {"type": "function_call_output", "call_id": "abc", "output": "done", "success": True}
    item = FunctionCallOutputItem.from_dict(raw)
    assert item.call_id == "abc"
    assert item.output.to_text() == "done"
    assert item.success is True
    out = item.to_dict()
    assert out["type"] == "function_call_output"
    assert out["output"] == "done"
    assert out["success"] is True


def test_function_call_output_roundtrip_preserves_content_items() -> None:
    raw = {
        "type": "function_call_output",
        "call_id": "abc",
        "output": [
            {"type": "input_text", "text": "line 1"},
            {"type": "input_image", "image_url": "data:image/png;base64,AAA"},
            {"type": "input_text", "text": "line 2"},
        ],
    }
    item = FunctionCallOutputItem.from_dict(raw)
    assert item.output.to_text() == "line 1\nline 2"
    out = item.to_dict()
    assert isinstance(out["output"], list)
    assert out["output"][0]["type"] == "input_text"
    assert out["output"][1]["type"] == "input_image"


def test_function_call_output_content_items_to_text_joins_text_segments() -> None:
    payload = FunctionCallOutputPayload.from_output(
        [
            {"type": "input_text", "text": "line 1"},
            {"type": "input_image", "image_url": "data:image/png;base64,AAA"},
            {"type": "input_text", "text": "line 2"},
        ]
    )

    assert function_call_output_content_items_to_text(payload.body) == "line 1\nline 2"  # type: ignore[arg-type]


def test_function_call_output_payload_text_segments_follow_trimmed_text_items() -> None:
    payload = FunctionCallOutputPayload.from_output(
        [
            {"type": "input_text", "text": " line 1 "},
            {"type": "input_image", "image_url": "data:image/png;base64,AAA"},
            {"type": "input_text", "text": "\nline 2\n"},
        ]
    )

    assert payload.text_segments() == ["line 1", "line 2"]


def test_function_call_output_content_items_to_text_ignores_blank_text_and_images() -> None:
    payload = FunctionCallOutputPayload.from_output(
        [
            {"type": "input_text", "text": "   "},
            {"type": "input_image", "image_url": "data:image/png;base64,AAA"},
        ]
    )

    assert function_call_output_content_items_to_text(payload.body) is None  # type: ignore[arg-type]


def test_turn_item_from_dict_dispatch() -> None:
    assert isinstance(
        turn_item_from_dict({"type": "message", "role": "user", "content": "x"}), MessageItem
    )
    assert isinstance(turn_item_from_dict({"type": "reasoning", "content": "x"}), ReasoningItem)
    assert isinstance(
        turn_item_from_dict({"type": "function_call", "name": "x", "call_id": "1"}),
        FunctionCallItem,
    )
    assert isinstance(
        turn_item_from_dict({"type": "function_call_output", "call_id": "1", "output": "y"}),
        FunctionCallOutputItem,
    )
    assert turn_item_from_dict({"type": "unknown"}) == {"type": "unknown"}


def test_tool_output_input_items_from_turn_events_prefers_text_over_structured_content() -> None:
    items = tool_output_input_items_from_turn_events(
        [
            {
                "type": "item.completed",
                "item": {
                    "id": "item_0",
                    "type": "mcp_tool_call",
                    "tool": "read_file",
                    "status": "completed",
                    "result": {
                        "content": [{"type": "text", "text": "L10: def plan()"}],
                        "structured_content": {
                            "file_path": "cli/agent_cli/providers/openai_planner.py",
                            "offset": 10,
                            "text": "L10: def plan()",
                        },
                    },
                },
            }
        ]
    )

    assert items == [
        {
            "type": "function_call_output",
            "call_id": "item_0",
            "output": "L10: def plan()",
            "success": True,
            "content": [],
        }
    ]


def test_tool_turn_events_emit_function_call_output_for_image_artifacts() -> None:
    image_artifact = {
        "path": "/tmp/diagram.png",
        "mime_type": "image/png",
        "size_bytes": 42,
        "width": 10,
        "height": 12,
        "image_url": "data:image/png;base64,AAA",
        "detail": "high",
    }
    execution = CommandExecutionResult(
        assistant_text="View local image.",
        tool_events=[
            ToolEvent(
                name="view_image",
                ok=True,
                summary="image ready: diagram.png",
                payload={
                    "provider_call_id": "call_view_image_1",
                    "ok": True,
                    "requested_path": "diagram.png",
                    "path": "/tmp/diagram.png",
                    "detail": "Image ready for continuation.",
                    "image_artifacts": [image_artifact],
                },
            )
        ],
        item_events=[
            {
                "type": "item.started",
                "item": {
                    "id": "item_0",
                    "type": "mcp_tool_call",
                    "tool": "view_image",
                    "arguments": {"path": "/tmp/diagram.png"},
                    "status": "in_progress",
                },
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "item_0",
                    "type": "mcp_tool_call",
                    "tool": "view_image",
                    "arguments": {"path": "/tmp/diagram.png"},
                    "result": {
                        "structured_content": {
                            "image_artifacts": [image_artifact],
                        }
                    },
                    "status": "completed",
                },
            },
        ],
    )

    normalized = _DummyToolTurnEvents._normalized_execution_events(execution)

    output_event = next(
        event
        for event in normalized
        if event["type"] == "item.completed" and event["item"]["type"] == "function_call_output"
    )
    assert output_event["item"]["id"] == "item_1"
    assert output_event["item"]["call_id"] == "call_view_image_1"
    assert output_event["item"]["output"] == [
        {"type": "input_image", "image_url": "data:image/png;base64,AAA", "detail": "high"}
    ]
    assert output_event["item"]["success"] is True
    assert output_event["item"]["image_transport_family"] == "dedicated_tool_native_view_image"
    assert output_event["item"]["image_transport_subject"] == "diagram.png"


def test_tool_turn_events_do_not_emit_function_call_output_for_failed_media_ingest() -> None:
    execution = CommandExecutionResult(
        assistant_text="View local image.",
        tool_events=[
            ToolEvent(
                name="view_image",
                ok=False,
                summary="view image failed",
                payload={
                    "provider_call_id": "call_view_image_1",
                    "ok": False,
                    "error_code": "file_not_found",
                    "display_message": "Image file does not exist: /tmp/missing.png",
                    "requested_path": "missing.png",
                    "path": "/tmp/missing.png",
                },
            )
        ],
        item_events=[
            {
                "type": "item.completed",
                "item": {
                    "id": "item_0",
                    "type": "mcp_tool_call",
                    "tool": "view_image",
                    "arguments": {"path": "missing.png"},
                    "error": {"message": "Image file does not exist: /tmp/missing.png"},
                    "status": "failed",
                },
            }
        ],
    )

    normalized = _DummyToolTurnEvents._normalized_execution_events(execution)

    assert not any(
        event.get("type") == "item.completed"
        and isinstance(event.get("item"), dict)
        and event["item"].get("type") == "function_call_output"
        for event in normalized
    )


def test_tool_turn_events_emit_file_read_image_projection_with_transport_family() -> None:
    execution = CommandExecutionResult(
        assistant_text="Read image file.",
        tool_events=[
            ToolEvent(
                name="read_file",
                ok=True,
                summary="file read image block",
                payload={
                    "provider_call_id": "call_read_file_1",
                    "function_call_output": [
                        {"type": "text", "text": "image content"},
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": "AAA",
                            },
                        },
                    ],
                    "path": "/tmp/diagram.png",
                },
            )
        ],
        item_events=[
            {
                "type": "item.completed",
                "item": {
                    "id": "item_0",
                    "type": "mcp_tool_call",
                    "tool": "read_file",
                    "arguments": {"path": "/tmp/diagram.png"},
                    "status": "completed",
                },
            }
        ],
    )

    normalized = _DummyToolTurnEvents._normalized_execution_events(execution)

    output_event = next(
        event
        for event in normalized
        if event["type"] == "item.completed" and event["item"]["type"] == "function_call_output"
    )
    assert output_event["item"]["call_id"] == "call_read_file_1"
    assert output_event["item"]["output"] == [
        {"type": "input_text", "text": "image content"},
        {"type": "input_image", "image_url": "data:image/png;base64,AAA"},
    ]
    assert output_event["item"]["image_transport_family"] == "image_aware_file_read"
    assert output_event["item"]["image_transport_subject"] == "/tmp/diagram.png"


def test_tool_turn_events_emit_view_document_projection_with_document_metadata() -> None:
    view_document_payload = {
        "provider_call_id": "call_view_document_1",
        "ok": True,
        "requested_path": "notes.md",
        "path": "/tmp/notes.md",
        "source_mode": "tool_path",
        "capability_baseline": "extraction_only",
        "document_class": "text_like",
        "extraction_state": "text_slice_ready",
        "mode": "text_slice",
        "media_mode": "text_slice",
        "mime_type": "text/markdown",
        "supported_modes": ["text_slice", "structured_content"],
        "text_slice": {
            "text": "beta",
            "encoding": "utf-8",
            "offset": 6,
            "max_chars": 4,
            "returned_chars": 4,
            "total_chars": 16,
            "truncated": True,
            "line_count": 1,
        },
        "structured_content": None,
        "error_code": "",
        "display_message": "",
    }
    execution = CommandExecutionResult(
        assistant_text="View local document.",
        tool_events=[
            ToolEvent(
                name="view_document",
                ok=True,
                summary="document text slice ready: notes.md",
                payload=view_document_payload,
            )
        ],
        item_events=[
            {
                "type": "item.completed",
                "item": {
                    "id": "item_0",
                    "type": "mcp_tool_call",
                    "tool": "view_document",
                    "arguments": {"path": "/tmp/notes.md"},
                    "status": "completed",
                },
            }
        ],
    )

    normalized = _DummyToolTurnEvents._normalized_execution_events(execution)

    output_event = next(
        event
        for event in normalized
        if event["type"] == "item.completed" and event["item"]["type"] == "function_call_output"
    )
    assert output_event["item"] == {
        "id": "item_1",
        "type": "function_call_output",
        "call_id": "call_view_document_1",
        "output": [{"type": "input_text", "text": "beta"}],
        "document_projection_mode": "tool_result_content_block",
        "document_projection_state": "document_projected_text",
        "document_projection_subject": "/tmp/notes.md",
        "success": True,
    }


def test_tool_turn_events_emit_explicit_model_visible_function_call_output() -> None:
    execution = CommandExecutionResult(
        assistant_text="delegated agent agent_1 started",
        tool_events=[
            ToolEvent(
                name="spawn_agent",
                ok=True,
                summary="spawn_agent started",
                payload={
                    "provider_call_id": "call_spawn_agent_1",
                    "function_call_output": '{"agent_id": "agent_1", "nickname": null}',
                    "function_call_output_model_visible": True,
                },
            )
        ],
        item_events=[],
    )

    normalized = _DummyToolTurnEvents._normalized_execution_events(execution)

    output_event = next(
        event
        for event in normalized
        if event["type"] == "item.completed" and event["item"]["type"] == "function_call_output"
    )
    assert output_event["item"] == {
        "id": "item_0",
        "type": "function_call_output",
        "call_id": "call_spawn_agent_1",
        "output": '{"agent_id": "agent_1", "nickname": null}',
        "success": True,
    }


def test_tool_turn_events_do_not_emit_view_document_projection_for_failed_document_payload() -> (
    None
):
    execution = CommandExecutionResult(
        assistant_text="View local document.",
        tool_events=[
            ToolEvent(
                name="view_document",
                ok=False,
                summary="view document failed",
                payload={
                    "provider_call_id": "call_view_document_2",
                    "ok": False,
                    "requested_path": "missing.md",
                    "path": "/tmp/missing.md",
                    "source_mode": "tool_path",
                    "capability_baseline": "extraction_only",
                    "document_class": "unknown",
                    "extraction_state": "extraction_failed",
                    "mode": "text_slice",
                    "media_mode": "unsupported_media",
                    "mime_type": "text/markdown",
                    "supported_modes": ["text_slice", "structured_content"],
                    "text_slice": None,
                    "structured_content": None,
                    "error_code": "unreadable_document",
                    "display_message": "Document file is not readable.",
                },
            )
        ],
        item_events=[
            {
                "type": "item.completed",
                "item": {
                    "id": "item_0",
                    "type": "mcp_tool_call",
                    "tool": "view_document",
                    "arguments": {"path": "/tmp/missing.md"},
                    "status": "failed",
                    "error": {"message": "Document file is not readable."},
                },
            }
        ],
    )

    normalized = _DummyToolTurnEvents._normalized_execution_events(execution)

    assert not any(
        event.get("type") == "item.completed"
        and isinstance(event.get("item"), dict)
        and event["item"].get("type") == "function_call_output"
        for event in normalized
    )


def test_shell_tool_events_render_reference_style_wrapped_command() -> None:
    events, _ = tool_events_to_turn_events(
        [
            ToolEvent(
                name="exec_command",
                ok=True,
                summary="",
                payload={
                    "command": "find . -maxdepth 1 -mindepth 1 -printf '%P\\n' | sort",
                    "shell": "/bin/bash",
                    "login": True,
                    "stdout": "README.md\nsrc\n",
                },
            )
        ]
    )

    completed = next(
        event
        for event in events
        if event["type"] == "item.completed" and event["item"]["type"] == "command_execution"
    )
    assert (
        completed["item"]["command"]
        == "/bin/bash -lc \"find . -maxdepth 1 -mindepth 1 -printf '%P\\\\n' | sort\""
    )


def test_shell_tool_events_do_not_inject_posix_wrapper_when_shell_missing() -> None:
    events, _ = tool_events_to_turn_events(
        [
            ToolEvent(
                name="exec_command",
                ok=True,
                summary="",
                payload={
                    "command": "Get-Location",
                    "login": True,
                    "stdout": "C:\\\\repo\n",
                },
            )
        ]
    )

    completed = next(
        event
        for event in events
        if event["type"] == "item.completed" and event["item"]["type"] == "command_execution"
    )
    assert completed["item"]["command"] == "Get-Location"


def test_shell_tool_events_do_not_wrap_non_posix_shell_commands() -> None:
    events, _ = tool_events_to_turn_events(
        [
            ToolEvent(
                name="exec_command",
                ok=True,
                summary="",
                payload={
                    "command": "Get-Location",
                    "shell": "powershell.exe",
                    "login": True,
                    "stdout": "C:\\\\repo\n",
                },
            )
        ]
    )

    completed = next(
        event
        for event in events
        if event["type"] == "item.completed" and event["item"]["type"] == "command_execution"
    )
    assert completed["item"]["command"] == "Get-Location"


def test_native_shell_tool_events_preserve_provider_call_id_in_command_execution_projection() -> (
    None
):
    events, _ = tool_events_to_turn_events(
        [
            ToolEvent(
                name="shell",
                ok=True,
                summary="",
                payload={
                    "provider_call_id": "call_shell_1",
                    "provider_tool_type": "shell_call",
                    "command": "pwd",
                    "stdout": "/repo\n",
                },
            )
        ]
    )

    completed = next(
        event
        for event in events
        if event["type"] == "item.completed" and event["item"]["type"] == "command_execution"
    )
    assert completed["item"]["id"] == "call_shell_1"
    assert completed["item"]["call_id"] == "call_shell_1"
    assert completed["item"]["command"] == "pwd"


def test_exec_command_turn_items_preserve_command_execution_metadata_for_live_session() -> None:
    events, _ = tool_events_to_turn_events(
        [
            ToolEvent(
                name="exec_command",
                ok=True,
                summary="exec_command running 1000",
                payload={
                    "call_id": "call_exec_1",
                    "command": "python -i",
                    "session_id": "1000",
                    "process_id": "1000",
                    "cwd": "/repo",
                    "duration_ms": 250,
                    "status": "written",
                    "stdout": "ready\n",
                },
            )
        ]
    )

    completed = next(
        event
        for event in events
        if event["type"] == "item.completed" and event["item"]["type"] == "command_execution"
    )
    assert completed["item"]["id"] == "call_exec_1"
    assert completed["item"]["call_id"] == "call_exec_1"
    assert completed["item"]["status"] == "in_progress"
    assert completed["item"]["cwd"] == "/repo"
    assert completed["item"]["process_id"] == "1000"
    assert completed["item"]["duration_ms"] == 250
    assert completed["item"]["aggregated_output"] == "ready\n"


def test_tool_output_input_items_from_turn_events_formats_command_execution_as_unified_exec_text() -> (
    None
):
    items = tool_output_input_items_from_turn_events(
        [
            {
                "type": "item.completed",
                "item": {
                    "id": "call_exec_1",
                    "type": "command_execution",
                    "call_id": "call_exec_1",
                    "command": "python -i",
                    "aggregated_output": "ready\n",
                    "process_id": "1000",
                    "duration_ms": 250,
                    "status": "in_progress",
                },
            }
        ]
    )

    assert items == [
        {
            "type": "function_call_output",
            "call_id": "call_exec_1",
            "output": "Wall time: 0.2500 seconds\nProcess running with session ID 1000\nOutput:\nready\n",
            "success": True,
            "content": [],
        }
    ]


def test_function_call_input_items_from_tool_events_preserves_native_shell_call_shape() -> None:
    items = function_call_input_items_from_tool_events(
        [
            ToolEvent(
                name="shell",
                ok=True,
                summary="shell started",
                payload={
                    "provider_call_id": "call_shell_1",
                    "provider_tool_type": "shell_call",
                    "provider_raw_item": {
                        "type": "shell_call",
                        "call_id": "call_shell_1",
                        "action": {
                            "type": "exec",
                            "command": ["pwd"],
                            "timeout_ms": 1000,
                            "max_output_length": 12000,
                        },
                    },
                    "command": "pwd",
                },
            )
        ]
    )

    assert items == [
        {
            "type": "shell_call",
            "call_id": "call_shell_1",
            "action": {
                "type": "exec",
                "command": ["pwd"],
                "timeout_ms": 1000,
                "max_output_length": 12000,
            },
        }
    ]


def test_tool_output_input_items_from_tool_events_preserves_native_shell_output_shape() -> None:
    items = tool_output_input_items_from_tool_events(
        [
            ToolEvent(
                name="shell",
                ok=True,
                summary="shell completed",
                payload={
                    "provider_call_id": "call_shell_1",
                    "provider_tool_type": "shell_call",
                    "provider_raw_item": {
                        "type": "shell_call",
                        "call_id": "call_shell_1",
                        "action": {
                            "type": "exec",
                            "command": ["pwd"],
                            "timeout_ms": 1000,
                            "max_output_length": 12000,
                        },
                    },
                    "stdout": "/repo\n",
                    "stderr": "",
                    "exit_code": 0,
                    "status": "completed",
                },
            )
        ]
    )

    assert items == [
        {
            "type": "shell_call_output",
            "call_id": "call_shell_1",
            "output": [
                {
                    "stdout": "/repo\n",
                    "stderr": "",
                    "outcome": {"type": "exit", "exit_code": 0},
                }
            ],
            "max_output_length": 12000,
            "status": "completed",
        }
    ]


def test_response_items_with_tool_outputs_does_not_duplicate_native_shell_projection() -> None:
    items = response_items_with_tool_outputs(
        [
            {
                "type": "shell_call",
                "call_id": "call_shell_1",
                "action": {
                    "type": "exec",
                    "command": ["pwd"],
                    "timeout_ms": 1000,
                    "max_output_length": 12000,
                },
                "status": "completed",
            },
            {
                "type": "shell_call_output",
                "call_id": "call_shell_1",
                "output": [
                    {
                        "stdout": "/repo\n",
                        "stderr": "",
                        "outcome": {"type": "exit", "exit_code": 0},
                    }
                ],
                "status": "completed",
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "done"}],
            },
        ],
        [
            {
                "type": "item.completed",
                "item": {
                    "id": "call_shell_1",
                    "type": "command_execution",
                    "call_id": "call_shell_1",
                    "command": "pwd",
                    "aggregated_output": "/repo\n",
                    "exit_code": 0,
                    "status": "completed",
                },
            }
        ],
        tool_events=[],
    )

    assert [item["type"] for item in items] == [
        "shell_call",
        "shell_call_output",
        "message",
    ]


def test_generic_web_search_tool_event_turn_items_do_not_use_result_payload_as_arguments() -> None:
    events, _ = tool_events_to_turn_events(
        [
            ToolEvent(
                name="web_search",
                ok=True,
                summary="web results=1",
                payload={
                    "ok": True,
                    "engine": "bing_rss",
                    "query": "北京天气怎么样今天",
                    "count": 1,
                    "results": [{"title": "天气", "url": "https://example.com/weather"}],
                },
            )
        ]
    )

    completed = next(
        event
        for event in events
        if event["type"] == "item.completed" and event["item"]["type"] == "mcp_tool_call"
    )
    assert completed["item"]["tool"] == "web_search"
    assert completed["item"]["arguments"] == {"query": "北京天气怎么样今天"}
    assert "results" not in completed["item"]["arguments"]


def test_function_call_input_items_from_tool_events_sanitizes_web_search_result_payload_arguments() -> (
    None
):
    items = function_call_input_items_from_tool_events(
        [
            ToolEvent(
                name="web_search",
                ok=True,
                summary="web results=1",
                payload={
                    "call_id": "item_1",
                    "arguments": {
                        "ok": True,
                        "engine": "bing_rss",
                        "query": "北京天气怎么样今天",
                        "count": 1,
                        "results": [{"title": "天气", "url": "https://example.com/weather"}],
                    },
                    "query": "北京天气怎么样今天",
                },
            )
        ]
    )

    assert len(items) == 1
    assert items[0]["type"] == "function_call"
    assert items[0]["name"] == "web_search"
    assert json.loads(items[0]["arguments"]) == {"query": "北京天气怎么样今天"}


def test_function_call_input_items_from_tool_events_preserve_write_replay_arguments() -> None:
    items = function_call_input_items_from_tool_events(
        [
            ToolEvent(
                name="apply_patch",
                ok=True,
                summary="apply_patch files=1",
                payload={
                    "provider_call_id": "call_write_1",
                    "provider_tool_type": "function_call",
                    "function_call_name": "Write",
                    "function_call_arguments": {
                        "file_path": "notes.txt",
                        "content": "hello\n",
                    },
                    "request_kind": "structured_write",
                    "source_tool_name": "Write",
                    "guard_profile": "claude_write",
                },
            )
        ]
    )

    assert len(items) == 1
    assert items[0]["type"] == "function_call"
    assert items[0]["name"] == "Write"
    assert json.loads(items[0]["arguments"]) == {
        "file_path": "notes.txt",
        "content": "hello\n",
    }


def test_function_call_input_items_from_tool_events_preserve_raw_apply_patch_replay_input() -> None:
    patch_text = "*** Begin Patch\n*** Add File: notes.txt\n+hello\n*** End Patch"
    items = function_call_input_items_from_tool_events(
        [
            ToolEvent(
                name="apply_patch",
                ok=True,
                summary="apply_patch files=1",
                payload={
                    "provider_call_id": "call_patch_1",
                    "provider_tool_type": "custom_tool_call",
                    "function_call_name": "apply_patch",
                    "function_call_arguments": {
                        "patch": patch_text,
                    },
                    "request_kind": "raw_patch",
                },
            )
        ]
    )

    assert len(items) == 1
    assert items[0] == {
        "type": "custom_tool_call",
        "call_id": "call_patch_1",
        "name": "apply_patch",
        "input": patch_text,
    }


def test_function_call_input_items_from_turn_events_preserve_structured_apply_patch_as_function_call() -> (
    None
):
    items = function_call_input_items_from_turn_events(
        [
            {
                "type": "item.completed",
                "item": {
                    "id": "item_1",
                    "type": "mcp_tool_call",
                    "tool": "apply_patch",
                    "status": "completed",
                    "arguments": {
                        "operation": "file_write",
                        "file_path": "notes.txt",
                        "content": "hello\n",
                    },
                    "result": {
                        "structured_content": {
                            "request_kind": "structured_write",
                            "function_call_name": "apply_patch",
                            "function_call_arguments": {
                                "file_path": "notes.txt",
                                "content": "hello\n",
                            },
                        }
                    },
                },
            }
        ]
    )

    assert len(items) == 1
    assert items[0]["type"] == "function_call"
    assert items[0]["name"] == "apply_patch"
    assert json.loads(items[0]["arguments"]) == {
        "file_path": "notes.txt",
        "content": "hello\n",
    }


def test_function_call_input_items_from_turn_events_preserve_raw_apply_patch_as_custom_tool_call() -> (
    None
):
    patch_text = "*** Begin Patch\n*** Add File: notes.txt\n+hello\n*** End Patch"
    items = function_call_input_items_from_turn_events(
        [
            {
                "type": "item.completed",
                "item": {
                    "id": "item_1",
                    "type": "mcp_tool_call",
                    "tool": "apply_patch",
                    "status": "completed",
                    "arguments": {
                        "patch": patch_text,
                    },
                    "result": {
                        "structured_content": {
                            "request_kind": "raw_patch",
                        }
                    },
                },
            }
        ]
    )

    assert len(items) == 1
    assert items[0] == {
        "type": "custom_tool_call",
        "call_id": "item_1",
        "name": "apply_patch",
        "input": patch_text,
        "content": [],
    }


def test_function_call_input_items_from_turn_events_sanitizes_web_search_result_payload_arguments() -> (
    None
):
    items = function_call_input_items_from_turn_events(
        [
            {
                "type": "item.completed",
                "item": {
                    "id": "item_1",
                    "type": "mcp_tool_call",
                    "tool": "web_search",
                    "status": "completed",
                    "arguments": {
                        "ok": True,
                        "engine": "bing_rss",
                        "query": "北京天气怎么样今天",
                        "count": 1,
                        "results": [{"title": "天气", "url": "https://example.com/weather"}],
                    },
                    "result": {
                        "content": [{"type": "text", "text": "done"}],
                        "structured_content": {
                            "ok": True,
                            "query": "北京天气怎么样今天",
                            "results": [{"title": "天气", "url": "https://example.com/weather"}],
                        },
                    },
                },
            }
        ]
    )

    assert len(items) == 1
    assert items[0]["type"] == "function_call"
    assert items[0]["name"] == "web_search"
    assert json.loads(items[0]["arguments"]) == {"query": "北京天气怎么样今天"}

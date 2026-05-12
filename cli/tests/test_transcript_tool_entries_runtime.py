from __future__ import annotations

from cli.agent_cli.ui import transcript_tool_entries as facade
from cli.agent_cli.ui import transcript_tool_entries_runtime as runtime

def test_tool_event_from_turn_tool_item_promotes_shell_approval_name() -> None:
    item = {
        "server": "local",
        "tool": "exec_command",
        "status": "failed",
        "arguments": {"command": "rm -rf /tmp/demo"},
        "result": {"structured_content": {"approval_id": "appr_1", "status": "pending"}},
        "error": {"message": "approval required"},
    }

    event = runtime.tool_event_from_turn_tool_item(item)

    assert event is not None
    assert event.name == "shell_approval_requested"
    assert event.ok is False
    assert event.payload["approval_id"] == "appr_1"
    assert event.payload["arguments"] == {"command": "rm -rf /tmp/demo"}

def test_command_execution_entry_keeps_facade_contract() -> None:
    entry = facade.command_execution_entry(
        {
            "command": "/bin/bash -lc \"printf 'a\\nb\\nc\\nd\\ne\\nf'\"",
            "aggregated_output": "a\nb\nc\nd\ne\nf",
            "status": "completed",
            "exit_code": 0,
        },
        item_key="item_1",
        scope_activity_key=lambda value: f"scope:{value}" if value else None,
    )

    assert entry.kind == "activity"
    assert entry.layer == "tool"
    assert entry.status == "success"
    assert entry.activity_key == "scope:item_1"
    assert entry.render_mode == "tool_command"
    assert entry.lines[0] == "• Ran printf 'a"
    assert entry.lines[1] == "  │ b…"
    assert entry.lines[2] == "  └ a"

def test_mcp_tool_call_entry_renders_completed_error_detail() -> None:
    entry = facade.mcp_tool_call_entry(
        {
            "server": "workspace",
            "tool": "file_search",
            "arguments": {"query": "needle", "path": "src"},
            "status": "failed",
            "error": {"message": "backend unavailable"},
        },
        item_key="item_2",
        scope_activity_key=lambda value: value,
    )

    assert entry.lines[0] == '• Called workspace.file_search({"query":"needle","path":"src"})'
    assert "Error: backend unavailable" in "\n".join(entry.lines)
    assert entry.status == "error"


def test_input_image_output_transport_details_prefers_transport_subject_and_family() -> None:
    display_name, image_count, transport_family, state = runtime.input_image_output_transport_details(
        {
            "call_id": "call_read_file_1",
            "output": [{"type": "input_image", "image_url": "data:image/png;base64,AAA"}],
            "image_transport_family": "image_aware_file_read",
            "image_transport_subject": "/tmp/diagram.png",
        }
    )

    assert display_name == "diagram.png"
    assert image_count == 1
    assert transport_family == "image_aware_file_read"
    assert state == "image_injected_file_read"


def test_input_image_output_transport_details_infers_view_image_family_from_call_id() -> None:
    display_name, image_count, transport_family, state = runtime.input_image_output_transport_details(
        {
            "call_id": "call_view_image_1",
            "image_transport_subject": "/tmp/diagram.png",
            "output": [{"type": "input_image", "image_url": "data:image/png;base64,AAA", "detail": "original"}],
        }
    )

    assert display_name == "diagram.png"
    assert image_count == 1
    assert transport_family == "dedicated_tool_native_view_image"
    assert state == "image_injected_tool_native"


def test_input_image_output_transport_details_does_not_treat_original_detail_as_subject() -> None:
    display_name, image_count, transport_family, state = runtime.input_image_output_transport_details(
        {
            "call_id": "call_view_image_1",
            "output": [{"type": "input_image", "image_url": "data:image/png;base64,AAA", "detail": "original"}],
        }
    )

    assert display_name == ""
    assert image_count == 1
    assert transport_family == "dedicated_tool_native_view_image"
    assert state == "image_injected_tool_native"


def test_view_document_extraction_details_report_document_family_state() -> None:
    display_name, extraction_mode, state = runtime.view_document_extraction_details(
        {
            "tool": "view_document",
            "status": "completed",
            "result": {
                "structured_content": {
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
                    "text_slice": {"text": "beta"},
                    "structured_content": None,
                }
            },
        }
    )

    assert display_name == "notes.md"
    assert extraction_mode == "text_slice"
    assert state == "document_extracted_text"


def test_document_output_projection_details_report_document_projection_state() -> None:
    display_name, projection_mode, state = runtime.document_output_projection_details(
        {
            "type": "function_call_output",
            "document_projection_mode": "tool_result_content_block",
            "document_projection_state": "document_projected_structured",
            "document_projection_subject": "/tmp/data.json",
            "output": [{"type": "input_text", "text": '{"name":"demo"}'}],
        }
    )

    assert display_name == "data.json"
    assert projection_mode == "tool_result_content_block"
    assert state == "document_projected_structured"

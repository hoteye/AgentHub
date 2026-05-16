from __future__ import annotations

from dataclasses import replace

from cli.agent_cli.ui import transcript_tool_entries as facade
from cli.agent_cli.ui import transcript_tool_entries_runtime as runtime
from cli.agent_cli.ui.transcript_history import (
    TranscriptEntry,
    render_transcript_visual_entries,
)
from cli.agent_cli.ui.transcript_structured_rendering_runtime import (
    STRUCTURED_TOOL_RENDERERS,
    ToolTranscriptRenderer,
    structured_renderer_tool_names,
)


def test_structured_renderer_registry_exposes_tool_renderers() -> None:
    assert all(
        isinstance(renderer, ToolTranscriptRenderer) for renderer in STRUCTURED_TOOL_RENDERERS
    )
    assert structured_renderer_tool_names() == (
        "command_execution",
        "command_exploration",
        "document_output",
        "input_image_output",
        "mcp_tool_call",
        "todo_list",
        "view_document",
        "view_image",
    )


def test_unknown_structured_tool_falls_back_to_legacy_render_mode() -> None:
    entry = TranscriptEntry(
        kind="activity",
        layer="tool",
        lines=["• Legacy fallback", "  └ still rendered"],
        structured={
            "type": "tool",
            "name": "unknown_tool",
            "state": "completed",
            "title": "Ignored structured payload",
        },
    )

    rendered = render_transcript_visual_entries([entry], width=80)

    assert rendered.lines == [
        "◆ Legacy fallback",
        "  └ still rendered",
    ]


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
    assert entry.structured is not None
    assert entry.structured["type"] == "tool"
    assert entry.structured["name"] == "command_execution"
    assert entry.structured["state"] == "completed"
    assert entry.structured["input"]["command"] == "printf 'a\nb\nc\nd\ne\nf'"
    assert entry.structured["metadata"]["output_truncated"] is True
    assert entry.structured["metadata"]["output_line_count"] == 6
    assert entry.lines[0] == "• Ran printf 'a"
    assert entry.lines[1] == "  │ b…"
    assert entry.lines[2] == "  └ a"

    rendered = render_transcript_visual_entries([entry], width=80)
    assert rendered.lines[:4] == [
        "$ Ran printf 'a",
        "  │ b…",
        "  │ exit: 0",
        "  │ output: 6 lines, preview shown",
    ]


def test_command_visual_render_surfaces_structured_shell_metadata() -> None:
    entry = facade.command_execution_entry(
        {
            "command": "pytest -q",
            "aggregated_output": "18 passed",
            "status": "completed",
            "exit_code": 0,
            "cwd": "/repo",
            "duration_ms": 4120,
        },
        item_key="item_shell_metadata",
        scope_activity_key=lambda value: value,
    )

    rendered = render_transcript_visual_entries([entry], width=80)

    assert entry.structured is not None
    assert entry.structured["metadata"]["cwd"] == "/repo"
    assert entry.structured["metadata"]["duration_ms"] == 4120
    assert rendered.lines == [
        "$ Ran pytest -q",
        "  │ cwd: /repo",
        "  │ exit: 0",
        "  │ duration: 4.12s",
        "  └ 18 passed",
    ]


def test_command_visual_render_uses_structured_payload_before_legacy_lines() -> None:
    entry = facade.command_execution_entry(
        {
            "command": "/bin/bash -lc \"printf 'a\\nb'\"",
            "aggregated_output": "a\nb",
            "status": "completed",
            "exit_code": 0,
        },
        item_key="item_structured_command",
        scope_activity_key=lambda value: value,
    )
    tampered = replace(entry, lines=["BROKEN LEGACY LINE"])

    rendered = render_transcript_visual_entries([tampered], width=80)

    assert rendered.lines == [
        "$ Ran printf 'a",
        "  │ b'",
        "  │ exit: 0",
        "  └ a",
        "    b",
    ]


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
    assert entry.structured is not None
    assert entry.structured["type"] == "tool"
    assert entry.structured["name"] == "mcp_tool_call"
    assert entry.structured["state"] == "error"
    assert entry.structured["metadata"]["tool_name"] == "file_search"


def test_mcp_visual_render_uses_structured_payload_before_legacy_lines() -> None:
    entry = facade.mcp_tool_call_entry(
        {
            "server": "search",
            "tool": "find_docs",
            "arguments": {"query": "ratatui styling", "limit": 3},
            "status": "completed",
            "result": {"content": [{"type": "text", "text": "Found guidance"}]},
        },
        item_key="item_structured_mcp",
        scope_activity_key=lambda value: value,
    )
    tampered = replace(entry, lines=["BROKEN LEGACY LINE"])

    rendered = render_transcript_visual_entries([tampered], width=80)

    assert rendered.lines == [
        '◆ Called search.find_docs({"query":"ratatui styling","limit":3})',
        "  └ Found guidance",
    ]


def test_artifact_visual_render_uses_structured_payload_before_legacy_lines() -> None:
    entry = facade.view_image_mcp_tool_entry(
        {
            "tool": "view_image",
            "status": "completed",
            "result": {
                "structured_content": {
                    "path": "/tmp/diagram.png",
                    "requested_path": "diagram.png",
                    "image_artifacts": [{"path": "/tmp/diagram.png"}],
                }
            },
        },
        item_key="item_structured_image",
        scope_activity_key=lambda value: value,
    )
    assert entry is not None
    tampered = replace(entry, lines=["BROKEN LEGACY LINE"])

    rendered = render_transcript_visual_entries([tampered], width=80)

    assert rendered.lines == [
        "◆ Image ready diagram.png",
        "  │ state: image_ready",
    ]


def test_input_image_output_transport_details_prefers_transport_subject_and_family() -> None:
    display_name, image_count, transport_family, state = (
        runtime.input_image_output_transport_details(
            {
                "call_id": "call_read_file_1",
                "output": [{"type": "input_image", "image_url": "data:image/png;base64,AAA"}],
                "image_transport_family": "image_aware_file_read",
                "image_transport_subject": "/tmp/diagram.png",
            }
        )
    )

    assert display_name == "diagram.png"
    assert image_count == 1
    assert transport_family == "image_aware_file_read"
    assert state == "image_injected_file_read"


def test_input_image_output_transport_details_infers_view_image_family_from_call_id() -> None:
    display_name, image_count, transport_family, state = (
        runtime.input_image_output_transport_details(
            {
                "call_id": "call_view_image_1",
                "image_transport_subject": "/tmp/diagram.png",
                "output": [
                    {
                        "type": "input_image",
                        "image_url": "data:image/png;base64,AAA",
                        "detail": "original",
                    }
                ],
            }
        )
    )

    assert display_name == "diagram.png"
    assert image_count == 1
    assert transport_family == "dedicated_tool_native_view_image"
    assert state == "image_injected_tool_native"


def test_input_image_output_transport_details_does_not_treat_original_detail_as_subject() -> None:
    display_name, image_count, transport_family, state = (
        runtime.input_image_output_transport_details(
            {
                "call_id": "call_view_image_1",
                "output": [
                    {
                        "type": "input_image",
                        "image_url": "data:image/png;base64,AAA",
                        "detail": "original",
                    }
                ],
            }
        )
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

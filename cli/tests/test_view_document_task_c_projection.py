from __future__ import annotations

import json

from cli.agent_cli.core.provider_session import default_tool_result_items
from cli.agent_cli.models import CommandExecutionResult, ToolEvent
from cli.agent_cli.providers.adapters import openai_responses_input_runtime
from cli.agent_cli.providers.tool_turn_events import ToolTurnEventsMixin
from cli.agent_cli.ui import app_turn_event_runtime
from cli.agent_cli.ui import transcript_tool_entries


class _DummyToolTurnEvents(ToolTurnEventsMixin):
    pass


def _view_document_text_payload(*, ok: bool = True) -> dict[str, object]:
    payload: dict[str, object] = {
        "ok": ok,
        "requested_path": "notes.md",
        "path": "/tmp/notes.md",
        "source_mode": "tool_path",
        "capability_baseline": "extraction_only",
        "document_class": "text_like",
        "extraction_state": "text_slice_ready" if ok else "extraction_failed",
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
        }
        if ok
        else None,
        "structured_content": None,
        "error_code": "" if ok else "unreadable_document",
        "display_message": "" if ok else "Document extraction failed.",
    }
    return payload


def _view_document_structured_payload() -> dict[str, object]:
    return {
        "ok": True,
        "requested_path": "data.json",
        "path": "/tmp/data.json",
        "source_mode": "tool_path",
        "capability_baseline": "extraction_only",
        "document_class": "structured_json",
        "extraction_state": "structured_content_ready",
        "mode": "auto",
        "media_mode": "structured_content",
        "mime_type": "application/json",
        "supported_modes": ["text_slice", "structured_content"],
        "text_slice": None,
        "structured_content": {
            "format": "json",
            "data": {"name": "demo", "count": 2},
        },
        "error_code": "",
        "display_message": "",
    }


def test_default_tool_result_items_project_view_document_text_slice_to_input_text() -> None:
    items = default_tool_result_items(
        call_id="call_doc_1",
        command_text="/view_document notes.md",
        assistant_text="View local document.",
        events=[
            ToolEvent(
                name="view_document",
                ok=True,
                summary="document text slice ready: notes.md",
                payload=_view_document_text_payload(),
            )
        ],
    )

    assert items == [
        {
            "type": "function_call_output",
            "call_id": "call_doc_1",
            "output": [{"type": "input_text", "text": "beta"}],
            "document_projection_mode": "tool_result_content_block",
            "document_projection_state": "document_projected_text",
            "document_projection_subject": "/tmp/notes.md",
            "success": True,
        }
    ]


def test_default_tool_result_items_keep_failed_view_document_payload_fail_closed() -> None:
    items = default_tool_result_items(
        call_id="call_doc_2",
        command_text="/view_document missing.md",
        assistant_text="View local document.",
        events=[
            ToolEvent(
                name="view_document",
                ok=False,
                summary="view document failed",
                payload=_view_document_text_payload(ok=False),
            )
        ],
    )

    assert items[0]["type"] == "function_call_output"
    assert items[0]["call_id"] == "call_doc_2"
    assert items[0]["success"] is False
    assert "document_projection_mode" not in items[0]
    assert json.loads(str(items[0]["output"]))["error_code"] == "unreadable_document"


def test_openai_responses_input_runtime_projects_view_document_structured_content_to_input_text() -> None:
    normalized = openai_responses_input_runtime.normalize_single_input_item(
        {
            "type": "function_call_output",
            "call_id": "call_doc_structured",
            "output": json.dumps(_view_document_structured_payload(), ensure_ascii=False),
            "success": True,
        },
        reference_parity=False,
        typed_message_input_item_fn=lambda role, content: {
            "type": "message",
            "role": role,
            "content": content,
        },
        workspace_context_message_text_fn=lambda payload, parity: "",
    )

    assert normalized is not None
    assert normalized["type"] == "function_call_output"
    assert normalized["call_id"] == "call_doc_structured"
    assert normalized["output"][0]["type"] == "input_text"
    assert json.loads(normalized["output"][0]["text"]) == {"name": "demo", "count": 2}


def test_tool_turn_events_emit_document_projection_output_without_image_transport_fields() -> None:
    execution = CommandExecutionResult(
        assistant_text="View local document.",
        tool_events=[
            ToolEvent(
                name="view_document",
                ok=True,
                summary="document text slice ready: notes.md",
                payload={
                    "provider_call_id": "call_doc_1",
                    **_view_document_text_payload(),
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
                    "arguments": {"path": "/tmp/notes.md"},
                    "result": {"structured_content": _view_document_text_payload()},
                    "status": "completed",
                },
            }
        ],
    )

    normalized = _DummyToolTurnEvents._normalized_execution_events(execution)

    output_event = next(
        event
        for event in normalized
        if event["type"] == "item.completed"
        and event["item"]["type"] == "function_call_output"
    )
    assert output_event["item"] == {
        "id": "item_1",
        "type": "function_call_output",
        "call_id": "call_doc_1",
        "output": [{"type": "input_text", "text": "beta"}],
        "document_projection_mode": "tool_result_content_block",
        "document_projection_state": "document_projected_text",
        "document_projection_subject": "/tmp/notes.md",
        "success": True,
    }


def test_tool_turn_events_do_not_emit_document_projection_output_for_failed_view_document() -> None:
    execution = CommandExecutionResult(
        assistant_text="View local document.",
        tool_events=[
            ToolEvent(
                name="view_document",
                ok=False,
                summary="view document failed",
                payload={
                    "provider_call_id": "call_doc_2",
                    **_view_document_text_payload(ok=False),
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
                    "error": {"message": "Document extraction failed."},
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


def test_transcript_tool_entries_render_document_extraction_and_projection_states() -> None:
    extraction_entry = transcript_tool_entries.view_document_mcp_tool_entry(
        {
            "tool": "view_document",
            "status": "completed",
            "result": {"structured_content": _view_document_text_payload()},
        },
        item_key="item_1",
        scope_activity_key=lambda value: value,
    )
    projection_entry = transcript_tool_entries.document_output_entry(
        {
            "type": "function_call_output",
            "document_projection_mode": "tool_result_content_block",
            "document_projection_state": "document_projected_text",
            "document_projection_subject": "/tmp/notes.md",
            "output": [{"type": "input_text", "text": "beta"}],
        },
        item_key="item_2",
        scope_activity_key=lambda value: value,
    )

    assert extraction_entry is not None
    assert extraction_entry.lines == [
        "• Document extracted",
        "  └ notes.md (text slice)",
        "    state=document_extracted_text",
    ]
    assert extraction_entry.render_mode == "tool_view_document_ready"

    assert projection_entry is not None
    assert projection_entry.lines == [
        "• Document projected (tool result)",
        "  └ notes.md",
        "    state=document_projected_text",
    ]
    assert projection_entry.render_mode == "tool_document_output"


def test_app_turn_event_runtime_prefers_document_entries_for_view_document_items() -> None:
    class _FakeApp:
        COMMAND_OUTPUT_MAX_LINES = 5

        def _turn_event_item_key(self, item):  # noqa: ANN001, ANN201
            return str(item.get("id") or "")

        def _scope_activity_key(self, value):  # noqa: ANN001, ANN201
            return value

    extraction_entry = app_turn_event_runtime.turn_event_entry(
        _FakeApp(),
        {
            "type": "item.completed",
            "item": {
                "id": "item_1",
                "type": "mcp_tool_call",
                "tool": "view_document",
                "status": "completed",
                "result": {"structured_content": _view_document_text_payload()},
            },
        },
    )
    projection_entry = app_turn_event_runtime.turn_event_entry(
        _FakeApp(),
        {
            "type": "item.completed",
            "item": {
                "id": "item_2",
                "type": "function_call_output",
                "document_projection_mode": "tool_result_content_block",
                "document_projection_state": "document_projected_text",
                "document_projection_subject": "/tmp/notes.md",
                "output": [{"type": "input_text", "text": "beta"}],
            },
        },
    )

    assert extraction_entry is not None
    assert extraction_entry.render_mode == "tool_view_document_ready"
    assert extraction_entry.lines[2] == "    state=document_extracted_text"

    assert projection_entry is not None
    assert projection_entry.render_mode == "tool_document_output"
    assert projection_entry.lines[2] == "    state=document_projected_text"

from __future__ import annotations

from cli.agent_cli import image_transport_runtime as runtime


def test_image_transport_family_for_tool_uses_shared_resolution_rules() -> None:
    assert (
        runtime.image_transport_family_for_tool(tool_name="view_image")
        == "dedicated_tool_native_view_image"
    )
    assert (
        runtime.image_transport_family_for_tool(tool_name="read_file")
        == "image_aware_file_read"
    )
    assert (
        runtime.image_transport_family_for_tool(tool_name="user_image_input")
        == "attachment_first_message_native"
    )


def test_image_transport_family_from_output_item_uses_explicit_then_evidence() -> None:
    assert (
        runtime.image_transport_family_from_output_item(
            {"image_transport_family": "image_aware_file_read"},
            [{"type": "input_image", "image_url": "data:image/png;base64,AAA"}],
        )
        == "image_aware_file_read"
    )
    assert (
        runtime.image_transport_family_from_output_item(
            {"call_id": "call_view_image_1"},
            [{"type": "input_image", "image_url": "data:image/png;base64,AAA"}],
        )
        == "dedicated_tool_native_view_image"
    )
    assert (
        runtime.image_transport_family_from_output_item(
            {"image_transport_subject": "attachment:demo.png"},
            [{"type": "input_image", "image_url": "data:image/png;base64,AAA"}],
        )
        == "attachment_first_message_native"
    )


def test_image_transport_subject_prefers_payload_paths_before_legacy_detail_hints() -> None:
    assert (
        runtime.image_transport_subject(
            payload={"path": "/tmp/a.png"},
            output_items=[{"type": "input_image", "detail": "/tmp/b.png"}],
        )
        == "/tmp/a.png"
    )
    assert (
        runtime.image_transport_subject(
            payload={},
            output_items=[{"type": "input_image", "detail": "/tmp/b.png"}],
        )
        == "/tmp/b.png"
    )
    assert (
        runtime.image_transport_subject(
            payload={},
            output_items=[{"type": "input_image", "detail": "original"}],
        )
        == ""
    )

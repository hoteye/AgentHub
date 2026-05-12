from __future__ import annotations

import pytest

from cli.agent_cli import image_transport_runtime as runtime


@pytest.mark.parametrize(
    ("profile", "tool_name", "expected_family", "expected_state"),
    [
        (
            "codex_openai",
            "view_image",
            "dedicated_tool_native_view_image",
            "image_injected_tool_native",
        ),
        (
            "claude_code",
            "read_file",
            "image_aware_file_read",
            "image_injected_file_read",
        ),
        (
            "codex_openai",
            "user_image_input",
            "attachment_first_message_native",
            "image_injected_attachment",
        ),
    ],
)
def test_synthetic_image_transport_projection_matrix(
    profile: str,
    tool_name: str,
    expected_family: str,
    expected_state: str,
) -> None:
    family = runtime.image_transport_family_for_tool(
        tool_name=tool_name,
        tool_surface_profile=profile,
    )

    assert family == expected_family
    assert runtime.IMAGE_TRANSPORT_FAMILY_TO_STATE[family] == expected_state


def test_synthetic_matrix_keeps_generic_chat_to_text_only_tool_result_family() -> None:
    assert (
        runtime.image_transport_family_for_tool(
            tool_name="generic_media_tool",
            tool_surface_profile="generic_chat",
        )
        == "tool_native_image_continuation"
    )

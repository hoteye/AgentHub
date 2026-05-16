from __future__ import annotations

from cli.agent_cli.ui.transcript_structured_visual_blocks import structured_tool_block_lines


def test_structured_tool_block_lines_uses_shared_header_metadata_and_detail_shape() -> None:
    assert structured_tool_block_lines(
        "Ran pytest -q",
        width=80,
        metadata=["cwd: /repo", "exit: 0"],
        details=["18 passed"],
    ) == [
        "• Ran pytest -q",
        "  │ cwd: /repo",
        "  │ exit: 0",
        "  └ 18 passed",
    ]


def test_structured_tool_block_lines_splits_multiline_details() -> None:
    assert structured_tool_block_lines(
        "Called tool",
        width=80,
        details=["first\nsecond"],
    ) == [
        "• Called tool",
        "  └ first",
        "    second",
    ]

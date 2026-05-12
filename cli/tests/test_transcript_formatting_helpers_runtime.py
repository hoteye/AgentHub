from __future__ import annotations

from cli.agent_cli.ui import transcript_formatting_helpers_runtime

def test_format_transcript_block_lines_preserves_first_and_continuation_prefixes() -> None:
    assert transcript_formatting_helpers_runtime.format_transcript_block_lines(
        "Hello\nWorld",
        first_prefix="› ",
        continuation_prefix="  ",
    ) == ["› Hello", "  World"]

def test_activity_param_text_falls_back_to_structured_detail() -> None:
    assert transcript_formatting_helpers_runtime.activity_param_text(
        {},
        "query=needle\npath=src",
        "query",
        "pattern",
    ) == "needle"


def test_activity_param_text_reads_pipe_delimited_detail_segments() -> None:
    assert transcript_formatting_helpers_runtime.activity_param_text(
        {},
        "/tmp/example.png | detail=Image ready for continuation. | format=png",
        "detail",
    ) == "Image ready for continuation."

def test_merge_exploration_detail_items_coalesces_adjacent_reads_and_skips_empty_subjects() -> None:
    details = [("read", "a.py")]

    merged = transcript_formatting_helpers_runtime.merge_exploration_detail_items(details, ("read", "b.py"))
    merged = transcript_formatting_helpers_runtime.merge_exploration_detail_items(merged, ("search", ""))

    assert merged == [("read", "a.py, b.py")]

def test_render_exploration_entry_lines_formats_running_header_and_tree_body() -> None:
    assert transcript_formatting_helpers_runtime.render_exploration_entry_lines(
        [("search", "needle in src"), ("read", "main.py")],
        status="running",
    ) == [
        "• Exploring",
        "  └ Search needle in src",
        "    Read main.py",
    ]

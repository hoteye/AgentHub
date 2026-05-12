from __future__ import annotations

from cli.agent_cli.models import ActivityEvent, ToolEvent
from cli.agent_cli.runtime_core.event_rendering import activity_events_for_tool_event
from cli.agent_cli.ui.transcript_formatting import (
    format_activity_detail_lines,
    format_activity_summary,
    format_plan_steps,
    format_transcript_block,
)
from cli.agent_cli.ui.transcript_history import (
    RenderedTranscript,
    TranscriptEntry,
    activity_entry,
    assistant_message_entry,
    blank_entry,
    commentary_message_entry,
    render_transcript_entries,
    render_transcript_visual_entries,
)


def _render_plan_lines(detail: str) -> list[str]:
    steps = format_plan_steps(detail)
    lines = ["• Todo List"]
    if steps:
        first_step, *rest_steps = steps
        lines.append(f"  └ {first_step}")
        lines.extend(f"    {step}" for step in rest_steps)
    else:
        lines.append("  └ (no steps provided)")
    return lines


def _render_tool_activity(event: ActivityEvent) -> list[str]:
    summary = format_activity_summary(event)
    lines = [summary] if summary else []
    lines.extend(format_activity_detail_lines(str(event.detail or "")))
    return lines


def _render_command_output(title: str, stream: str) -> list[str]:
    if stream == "stdout":
        return []
    return format_activity_detail_lines(title, stream=stream)


def test_user_block_still_prefers_reference_prompt_prefix() -> None:
    lines = format_transcript_block(
        "Hello\nReference style", first_prefix="› ", continuation_prefix="  "
    )

    assert lines == ["› Hello", "  Reference style"]


def test_assistant_reply_uses_bullet_prefix() -> None:
    lines = format_transcript_block(
        "Replying now\nWith detail", first_prefix="• ", continuation_prefix="  "
    )

    assert lines == ["• Replying now", "  With detail"]


def test_plan_activity_produces_tree_indent_with_plan_steps() -> None:
    lines = _render_plan_lines("1. select_conversation\n2. read_recent_messages")

    assert lines == [
        "• Todo List",
        "  └ select_conversation",
        "    read_recent_messages",
    ]


def test_tool_activity_shows_summary_plus_tree_indent_detail() -> None:
    event = ActivityEvent(
        title="select_conversation",
        status="running",
        kind="tool",
        detail="current Enterprise WeChat automation validation\nread_recent_messages",
    )

    assert _render_tool_activity(event) == [
        "• Running select_conversation",
        "  └ current Enterprise WeChat automation validation",
        "    read_recent_messages",
    ]


def test_stdout_command_output_skipped_by_default() -> None:
    assert _render_command_output("python -V", "stdout") == []


def test_stderr_command_output_includes_tree_indent_with_label() -> None:
    assert _render_command_output("first line\nsecond line", "stderr") == [
        "  └ stderr: first line",
        "    second line",
    ]


def test_command_output_events_are_hidden_from_transcript_entries() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="first line\nsecond line",
            status="info",
            kind="command_output",
            detail="stderr",
        )
    )

    assert entry is None


def test_successful_policy_search_activity_suppresses_low_value_detail_lines() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Searched policy documents",
            status="success",
            kind="tool",
            detail="count=8",
        )
    )

    assert entry is not None
    assert entry.lines == ["• Searched policy documents"]


def test_web_search_activity_keeps_ranked_result_detail_lines() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Searched the web",
            status="success",
            kind="web",
            detail=(
                "query=OpenAI docs\n"
                "count=3\n"
                "1. platform.openai.com | high | OpenAI API docs\n"
                "2. mirror.example.com | low | OpenAI mirror\n"
                "3. github.com | high | openai-python"
            ),
        )
    )

    assert entry is not None
    assert entry.layer == "web"
    assert entry.lines == [
        "• Searched the web",
        "  └ OpenAI docs",
    ]
    assert entry.expanded_lines is None


def test_open_page_activity_keeps_ref_and_title_detail() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Opened webpage",
            status="success",
            kind="web",
            detail="page_1 | platform.openai.com | OpenAI API docs | scope=main | links=12 | preview=Build agents with the Responses API.",
        )
    )

    assert entry is not None
    assert entry.layer == "web"
    assert entry.lines == [
        "• Opened webpage",
        "  └ OpenAI API docs",
    ]


def test_click_page_activity_formats_title_and_metadata() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Opened clicked link",
            status="success",
            kind="web",
            detail="page_2 | Quickstart | scope=main | links=3 | preview=Install the SDK and send a first request.",
        )
    )

    assert entry is not None
    assert entry.lines == [
        "• Opened clicked link",
        "  └ Quickstart",
    ]


def test_find_page_activity_formats_match_count_and_scope() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Found text in page",
            status="success",
            kind="web",
            detail="count=5 | page_2 | scope=main",
        )
    )

    assert entry is not None
    assert entry.lines == [
        "• Found text in page",
        "  └ 5 matches",
    ]


def test_successful_command_keeps_compact_exit_summary_detail() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Ran python -V",
            status="success",
            kind="command",
            detail="exit 0 | 0.12s",
        )
    )

    assert entry is not None
    assert entry.lines == ["• Ran python -V"]


def test_apply_patch_activity_keeps_compact_change_summary() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Applied patch",
            status="success",
            kind="tool",
            detail="files=2\nadd=1\nupdate=1\n/tmp/demo.txt",
        )
    )

    assert entry is not None
    assert entry.lines == [
        "• Applied patch",
        "  └ 2 files changed",
    ]


def test_created_file_activity_shows_filename() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Created file",
            status="success",
            kind="tool",
            detail="files=1\n/tmp/demo.txt\nwrite_mode=create",
        )
    )

    assert entry is not None
    assert entry.lines == [
        "• Created file",
        "  └ demo.txt",
    ]


def test_patch_approval_requested_activity_renders_in_overlay_not_transcript() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Requested patch approval",
            status="success",
            kind="tool",
            detail=(
                "approval_1\nfiles=2\n/approve approval_1\n/approve approval_1 mode session\n"
                "/reject approval_1\nadd | notes.txt\nupdate | demo.txt"
            ),
        )
    )

    assert entry is None


def test_shell_approval_requested_activity_renders_in_overlay_not_transcript() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Requested shell approval",
            status="success",
            kind="tool",
            detail=(
                "approval_2\necho hello\n/approve approval_2\n/approve approval_2 mode session\n"
                "/approve approval_2 mode rule\n/reject approval_2\n/reject approval_2 mode cancel\ntimeout=60"
            ),
        )
    )

    assert entry is None


def test_approval_list_activity_stays_compact() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Listed approvals",
            status="success",
            kind="tool",
            detail="count=2\nstatus=pending\napproval_1 | pending | apply_patch | Approve workspace patch",
        )
    )

    assert entry is not None
    assert entry.lines == [
        "• Listed approvals",
        "  └ 2 pending approvals",
    ]


def test_approval_decision_activity_stays_compact() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Approved patch",
            status="success",
            kind="tool",
            detail="approval_1\nstatus=approved\nby=tester",
        )
    )

    assert entry is not None
    assert entry.lines == [
        "• Approved patch",
        "  └ approval_1",
    ]


def test_approval_decision_activity_surfaces_continuation_status() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Approved command",
            status="success",
            kind="tool",
            code="approval.decision.command",
            detail="approval_2\nstatus=approved\ncontinuation=completed",
            params={
                "approval_id": "approval_2",
                "status": "approved",
                "continuation_status": "completed",
            },
        )
    )

    assert entry is not None
    assert entry.lines == [
        "• Approved command",
        "  └ approval_2",
        "    Continuing after approval: completed",
    ]


def test_command_approval_decision_activity_stays_compact() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Approved command",
            status="success",
            kind="tool",
            code="approval.decision.command",
            detail="approval_2\nstatus=approved\ndecision=accept\ncommand=echo hello\nby=tester",
            params={
                "approval_id": "approval_2",
                "status": "approved",
                "decision_type": "accept",
                "action_type": "shell_command",
                "command": "echo hello",
            },
        )
    )

    assert entry is not None
    assert entry.lines == [
        "✔ You approved AgentHub to run echo hello this time",
    ]


def test_command_approval_rule_activity_matches_reference_style() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Approved command",
            status="success",
            kind="tool",
            code="approval.decision.command",
            detail="approval_2\nstatus=approved\ndecision=accept_with_execpolicy_amendment\ncommand=pnpm exec vite\nby=tester",
            params={
                "approval_id": "approval_2",
                "status": "approved",
                "decision_type": "accept_with_execpolicy_amendment",
                "action_type": "shell_command",
                "command": "pnpm exec vite",
            },
        )
    )

    assert entry is not None
    assert entry.lines == [
        "✔ You approved AgentHub to always run commands that start with pnpm exec vite",
    ]


def test_command_approval_cancel_activity_matches_reference_style() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Rejected command",
            status="success",
            kind="tool",
            code="approval.decision.command",
            detail="approval_2\nstatus=rejected\ndecision=cancel\ncommand=echo hello",
            params={
                "approval_id": "approval_2",
                "status": "rejected",
                "decision_type": "cancel",
                "action_type": "shell_command",
                "command": "echo hello",
            },
        )
    )

    assert entry is not None
    assert entry.lines == [
        "✗ You canceled the request to run echo hello",
    ]


def test_file_search_activity_keeps_match_summary() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Searched files",
            status="success",
            kind="tool",
            detail="count=2\nquery=hello\npath=src\nsrc/app.py:8 | TODO hello",
        )
    )

    assert entry is not None
    assert entry.lines == [
        "• Explored",
        "  └ Search hello in src",
    ]


def test_canonical_grep_files_activity_keeps_match_summary() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Searched file paths",
            status="success",
            kind="tool",
            detail="count=2\npattern=hello\npath=src\nsrc/app.py\nsrc/lib.py",
        )
    )

    assert entry is not None
    assert entry.lines == [
        "• Explored",
        "  └ Search hello in src",
    ]


def test_file_read_activity_stays_compact_without_body_dump() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Read file",
            status="success",
            kind="tool",
            detail="README.md | lines=8",
        )
    )

    assert entry is not None
    assert entry.lines == [
        "• Explored",
        "  └ Read README.md",
    ]


def test_file_list_activity_formats_count_and_path() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Listed files",
            status="success",
            kind="tool",
            detail="count=3\npath=src\nsrc/app.py\nsrc/lib.py",
        )
    )

    assert entry is not None
    assert entry.lines == [
        "• Explored",
        "  └ List src",
    ]


def test_canonical_list_dir_activity_formats_count_and_path() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Listed directory",
            status="success",
            kind="tool",
            detail="count=3\ndir_path=src\nE1: [file] app.py\nE2: [file] lib.py",
        )
    )

    assert entry is not None
    assert entry.lines == [
        "• Explored",
        "  └ List src",
    ]


def test_running_list_dir_activity_uses_reference_exploring_header() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Running list_dir",
            status="running",
            kind="tool",
            detail="dir_path=.",
        )
    )

    assert entry is not None
    assert entry.lines == [
        "• Exploring",
        "  └ List .",
    ]


def test_view_image_activity_defaults_to_image_ready_and_shows_state_line() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Viewed image",
            status="success",
            kind="tool",
            detail="/tmp/example.png | format=png | size=42",
        )
    )

    assert entry is not None
    assert entry.lines == [
        "• Image ready",
        "  └ example.png",
        "    state=image_ready",
    ]


def test_list_conversations_success_is_hidden_from_transcript() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Listed visible conversations",
            status="success",
            kind="tool",
            detail="4 visible, current demo",
        )
    )

    assert entry is None


def test_read_recent_messages_success_does_not_expand_message_body() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Read recent messages from current conversation",
            status="success",
            kind="tool",
            detail="user: hi\nassistant: hello",
        )
    )

    assert entry is not None
    assert entry.lines == ["• Read recent messages from current conversation"]


def test_prepare_send_success_only_keeps_risk_line() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Prepared reply for current conversation",
            status="success",
            kind="tool",
            detail="draft body preview\nrisk medium",
        )
    )

    assert entry is not None
    assert entry.lines == [
        "• Prepared reply for current conversation",
        "  └ risk medium",
    ]


def test_shell_failure_activity_only_uses_final_summary_and_stderr_tail() -> None:
    failure_event = ToolEvent(
        name="shell",
        ok=False,
        summary="shell rc=1",
        payload={
            "command": "run fail",
            "returncode": 1,
            "duration_ms": 123,
            "stderr": "first line\nsecond line\nthird line\nfourth line\n",
        },
    )

    events = activity_events_for_tool_event(failure_event)
    assert len(events) == 1
    entry = activity_entry(events[0])
    assert entry is not None
    assert entry.lines == [
        "✗ Command failed: run fail",
        "  └ exit 1 | 0.12s",
        "    stderr: second line",
        "    third line",
        "    fourth line",
    ]


def test_failed_command_activity_keeps_stderr_tail_in_final_summary() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Command failed: python broken.py",
            status="error",
            kind="command",
            detail="exit 1 | 0.12s\nstderr: Traceback line 1\nTraceback line 2",
        )
    )

    assert entry is not None
    assert entry.lines == [
        "✗ Command failed: python broken.py",
        "  └ exit 1 | 0.12s",
        "    stderr: Traceback line 1",
        "    Traceback line 2",
    ]


def test_transcript_layers_preserve_spacing_between_groups() -> None:
    tool_event = ActivityEvent(
        title="Run helper tool",
        status="success",
        kind="tool",
        detail="step one",
    )
    tool_entry = activity_entry(tool_event)
    assert tool_entry is not None
    entries = [
        commentary_message_entry("context updated"),
        blank_entry(),
        tool_entry,
        blank_entry(),
        assistant_message_entry("final answer"),
    ]
    assert render_transcript_entries(entries) == [
        "• context updated",
        "",
        "• Run helper tool",
        "  └ step one",
        "",
        "• final answer",
    ]


def test_activity_entry_layer_reflects_tool_vs_commentary() -> None:
    tool_event = ActivityEvent(
        title="Fetch records",
        status="success",
        kind="tool",
        detail="done",
    )
    web_event = ActivityEvent(
        title="Searched the web",
        status="success",
        kind="web",
        detail="count=1",
    )
    commentary_event = ActivityEvent(
        title="Narrate state",
        status="success",
        kind="narrative",
        detail="ready",
    )
    tool_entry = activity_entry(tool_event)
    web_entry = activity_entry(web_event)
    commentary_entry = activity_entry(commentary_event)
    assert tool_entry is not None
    assert web_entry is not None
    assert commentary_entry is not None
    assert tool_entry.layer == "tool"
    assert web_entry.layer == "web"
    assert commentary_entry.layer == "commentary"


def test_layered_transcript_entries_insert_single_blank_between_commentary_web_and_final() -> None:
    web_entry = activity_entry(
        ActivityEvent(
            title="Searched the web",
            status="success",
            kind="web",
            detail="count=1",
        )
    )

    assert web_entry is not None

    lines = render_transcript_entries(
        [
            commentary_message_entry("Checking official sources."),
            web_entry,
            assistant_message_entry("Top result is ready."),
        ]
    )

    assert lines == [
        "• Checking official sources.",
        "",
        "• Searched the web",
        "  └ 1 result",
        "",
        "• Top result is ready.",
    ]


def test_render_transcript_entries_uses_expanded_lines_when_web_item_is_expanded() -> None:
    entry = TranscriptEntry(
        kind="activity",
        layer="web",
        lines=["• Searched the web", "  └ 2 results", "    ... 1 more result"],
        expanded_lines=["• Searched the web", "  └ 3 results", "    1. A", "    2. B", "    3. C"],
        expanded=True,
    )

    assert render_transcript_entries([entry]) == [
        "• Searched the web",
        "  └ 3 results",
        "    1. A",
        "    2. B",
        "    3. C",
    ]


def test_render_transcript_visual_entries_renders_markdown_without_raw_fences() -> None:
    rendered: RenderedTranscript = render_transcript_visual_entries(
        [assistant_message_entry("读取结果如下：\n\n```python\nprint('hi')\n```")],
        width=48,
    )

    assert rendered.lines
    assert all("```" not in line for line in rendered.lines)
    assert any("print('hi')" in line for line in rendered.lines)
    assert len(rendered.line_styles) == len(rendered.lines)


def test_render_transcript_visual_entries_uses_reference_plain_markdown_layout() -> None:
    rendered: RenderedTranscript = render_transcript_visual_entries(
        [assistant_message_entry("# Title\n\n- one\n- two\n\n```python\nprint('hi')\n```")],
        width=48,
    )

    assert rendered.lines == [
        "• # Title",
        "  ",
        "  - one",
        "  - two",
        "  ",
        "  print('hi')",
    ]
    assert all("```" not in line for line in rendered.lines)
    assert all(not any(ch in line for ch in "┏┗┃━") for line in rendered.lines)


def test_render_transcript_visual_entries_trim_leading_markdown_blank_lines() -> None:
    rendered: RenderedTranscript = render_transcript_visual_entries(
        [assistant_message_entry("\n\nplain")],
        width=32,
    )

    assert rendered.lines == ["• plain"]


def test_layered_transcript_entries_insert_single_blank_between_commentary_tool_and_final() -> None:
    tool_entry = activity_entry(
        ActivityEvent(
            title="select_conversation",
            status="running",
            kind="tool",
        )
    )

    assert tool_entry is not None

    lines = render_transcript_entries(
        [
            commentary_message_entry("Inspecting current workspace."),
            tool_entry,
            assistant_message_entry("Current directory contents are ready."),
        ]
    )

    assert lines == [
        "• Inspecting current workspace.",
        "",
        "• Running select_conversation",
        "",
        "• Current directory contents are ready.",
    ]


def test_same_layer_tool_entries_stay_grouped_without_extra_blank_lines() -> None:
    running_entry = activity_entry(
        ActivityEvent(
            title="select_conversation",
            status="running",
            kind="tool",
        )
    )
    completed_entry = activity_entry(
        ActivityEvent(
            title="Selected Enterprise WeChat automation validation",
            status="success",
            kind="tool",
            detail="current Enterprise WeChat automation validation",
        )
    )

    assert running_entry is not None
    assert completed_entry is not None

    lines = render_transcript_entries([running_entry, completed_entry])

    assert lines == [
        "• Running select_conversation",
        "• Selected Enterprise WeChat automation validation",
        "  └ current Enterprise WeChat automation validation",
    ]


def test_explicit_blank_entry_and_layer_transition_do_not_duplicate_spacing() -> None:
    lines = render_transcript_entries(
        [
            commentary_message_entry("Inspecting current workspace."),
            blank_entry(),
            assistant_message_entry("Current directory contents are ready."),
        ]
    )

    assert lines == [
        "• Inspecting current workspace.",
        "",
        "• Current directory contents are ready.",
    ]

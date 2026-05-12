from __future__ import annotations

from cli.agent_cli.models import ActivityEvent, ToolEvent, activity_code, activity_dedupe_key
from cli.agent_cli.runtime_core.event_rendering import activity_events_for_tool_event
from cli.agent_cli.ui.transcript_formatting import (
    format_file_activity_lines,
    format_patch_activity_lines,
    format_web_activity_lines,
)
from cli.agent_cli.ui.transcript_history import activity_entry

def test_activity_event_round_trips_code_and_params() -> None:
    event = ActivityEvent(
        title="Read file",
        status="success",
        detail="path=README.md",
        kind="tool",
        code="file.read",
        params={"path": "README.md", "file_path": "README.md"},
    )

    restored = ActivityEvent.from_dict(event.to_dict())

    assert restored.code == "file.read"
    assert restored.params == {"path": "README.md", "file_path": "README.md"}

def test_activity_code_falls_back_from_legacy_title_patterns() -> None:
    event = ActivityEvent(
        title="Running list_dir",
        status="running",
        detail="dir_path=.",
        kind="tool",
    )

    assert activity_code(event) == "dir.list"

def test_tool_event_conversion_populates_structured_activity_fields() -> None:
    activity = activity_events_for_tool_event(
        ToolEvent(
            name="read_file",
            ok=True,
            summary="",
            payload={"file_path": "README.md", "line_count": 12},
        )
    )[0]

    assert activity.code == "file.read"
    assert activity.params["file_path"] == "README.md"

def test_activity_entry_prefers_code_over_title_for_file_rendering() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="读取文件",
            status="success",
            detail="path=README.md",
            kind="tool",
            code="file.read",
            params={"path": "README.md", "file_path": "README.md"},
        )
    )

    assert entry is not None
    assert entry.lines == [
        "• Explored",
        "  └ Read README.md",
    ]

def test_activity_dedupe_key_ignores_localized_title_when_code_and_params_match() -> None:
    english = ActivityEvent(
        title="Read file",
        status="success",
        detail="path=README.md",
        kind="tool",
        code="file.read",
        params={"path": "README.md", "file_path": "README.md"},
    )
    localized = ActivityEvent(
        title="读取文件",
        status="success",
        detail="path=README.md",
        kind="tool",
        code="file.read",
        params={"path": "README.md", "file_path": "README.md"},
    )

    assert activity_dedupe_key(english) == activity_dedupe_key(localized)

def test_file_activity_formatting_prefers_params_when_detail_is_not_structured() -> None:
    lines = format_file_activity_lines(
        ActivityEvent(
            title="读取文件",
            status="success",
            detail="detalle no estructurado",
            kind="tool",
            code="file.read",
            params={"path": "README.md", "file_path": "README.md"},
        )
    )

    assert lines == [
        "• 读取文件",
        "  └ README.md",
    ]

def test_patch_activity_formatting_prefers_params_when_detail_is_localized() -> None:
    lines = format_patch_activity_lines(
        ActivityEvent(
            title="请求补丁审批",
            status="success",
            detail="demande de validation",
            kind="tool",
            code="approval.request.patch",
            params={"approval_id": "approval_123", "file_count": 2},
        )
    )

    assert lines == [
        "• 请求补丁审批",
        "  └ approval_123 (2 files)",
    ]

def test_web_activity_formatting_prefers_params_when_detail_has_no_query_markup() -> None:
    lines = format_web_activity_lines(
        ActivityEvent(
            title="Recherche Web",
            status="success",
            detail="resume localise",
            kind="web",
            code="web.search",
            params={"query": "pytest interrupt", "count": 3},
        )
    )

    assert lines == [
        "• Recherche Web",
        "  └ pytest interrupt",
    ]

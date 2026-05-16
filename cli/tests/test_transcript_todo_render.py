from __future__ import annotations

from cli.agent_cli.app import AgentCliApp
from cli.agent_cli.models import ActivityEvent
from cli.agent_cli.runtime import AgentCliRuntime
from cli.agent_cli.ui.transcript_history import activity_entry, render_transcript_visual_entries


def test_plan_activity_uses_todo_list_render_mode() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Updated Plan",
            status="info",
            kind="plan",
            detail="1. inspect provider routing\n2. keep regression coverage stable",
        )
    )

    assert entry is not None
    assert entry.layer == "commentary"
    assert entry.render_mode == "todo_list"
    assert entry.structured is not None
    assert entry.structured["type"] == "tool"
    assert entry.structured["name"] == "todo_list"
    assert entry.structured["metadata"]["source"] == "plan_activity"
    assert entry.lines == [
        "• Todo List",
        "  └ inspect provider routing",
        "    keep regression coverage stable",
    ]


def test_todo_list_visual_render_keeps_checkbox_alignment_after_wrap() -> None:
    app = AgentCliApp(runtime=AgentCliRuntime())
    entry = app._turn_event_entry(
        {
            "type": "item.updated",
            "item": {
                "id": "item_plan_wrap",
                "type": "todo_list",
                "items": [
                    {"text": "inspect provider native web search routing", "completed": False},
                    {"text": "keep regression coverage stable", "completed": True},
                ],
            },
        }
    )

    assert entry is not None
    assert entry.structured is not None
    assert entry.structured["type"] == "tool"
    assert entry.structured["name"] == "todo_list"
    assert entry.structured["input"]["items"][0] == {
        "text": "inspect provider native web search routing",
        "completed": False,
    }
    rendered = render_transcript_visual_entries([entry], width=26)

    assert rendered.lines == [
        "□ Todo List",
        "  └ □ inspect provider",
        "      native web search",
        "      routing",
        "    ✔ keep regression",
        "      coverage stable",
    ]


def test_empty_plan_visual_render_keeps_no_steps_semantics() -> None:
    entry = activity_entry(
        ActivityEvent(
            title="Updated Plan",
            status="info",
            kind="plan",
            detail="",
        )
    )

    assert entry is not None
    assert entry.render_mode == "todo_list"
    rendered = render_transcript_visual_entries([entry], width=18)

    assert rendered.lines == [
        "□ Todo List",
        "  └ (no steps",
        "    provided)",
    ]

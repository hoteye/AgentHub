from __future__ import annotations

from cli.agent_cli.runtime_services.delegated_agent_workflow_render_runtime import delegated_workflow_text


def test_delegated_workflow_text_renders_live_snapshot_runtime_summary() -> None:
    payload = {
        "agent_id": "ag_001",
        "role": "teammate",
        "status": "running",
        "workflow_state": "running",
        "live_current_step_id": "step_3",
        "live_current_step_status": "running",
        "live_current_step_title": "refactor parser",
        "live_queued_input_count": 2,
        "live_has_active_input": True,
        "live_last_tool_event_count": 5,
        "live_last_item_event_count": 3,
        "live_last_turn_event_count": 8,
        "live_snapshot_exported_at": "2026-04-06T10:00:00Z",
        "step_count": 4,
        "checkpoint_count": 6,
    }

    text = delegated_workflow_text(payload)

    assert "current_step=step_3 | running | refactor parser" in text
    assert "queued_input_count=2" in text
    assert "has_active_input=true" in text
    assert "last_event_count=tool:5 item:3 turn:8" in text
    assert "snapshot_exported_at=2026-04-06T10:00:00Z" in text


def test_delegated_workflow_text_queued_count_falls_back_to_pending_input_count() -> None:
    payload = {
        "agent_id": "ag_002",
        "role": "subagent",
        "status": "queued",
        "workflow_state": "queued",
        "pending_input_count": 1,
        "step_count": 0,
        "checkpoint_count": 0,
    }

    text = delegated_workflow_text(payload)

    assert "queued_input_count=1" in text

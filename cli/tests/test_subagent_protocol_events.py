from __future__ import annotations

from cli.agent_cli.runtime_delegation import events
from cli.agent_cli.runtime_delegation.models import SubagentTaskRecord, SubagentTaskStatus
from cli.agent_cli.runtime_delegation.protocol import status_from_event_payload, status_from_event_type


def _record() -> SubagentTaskRecord:
    return SubagentTaskRecord.create(
        agent_id="ag_03",
        run_id="run_03",
        parent_run_id="parent_03",
        role="subagent",
        inherited_context={"thread_id": "th_03"},
        timeout=300,
        now_iso="2026-04-07T00:00:00+00:00",
    )


def test_standard_subagent_events_emit_expected_type_and_status_projection() -> None:
    record = _record()
    event_items = [
        events.subagent_queued(record, emitted_at="2026-04-07T00:00:00+00:00"),
        events.subagent_started(record, emitted_at="2026-04-07T00:00:01+00:00"),
        events.subagent_running(record, emitted_at="2026-04-07T00:00:02+00:00"),
        events.subagent_completed(record, emitted_at="2026-04-07T00:00:03+00:00"),
        events.subagent_failed(record, error="boom", emitted_at="2026-04-07T00:00:04+00:00"),
        events.subagent_timed_out(record, emitted_at="2026-04-07T00:00:05+00:00"),
        events.subagent_adopted(record, emitted_at="2026-04-07T00:00:06+00:00"),
    ]

    expected = [
        SubagentTaskStatus.QUEUED,
        SubagentTaskStatus.STARTED,
        SubagentTaskStatus.RUNNING,
        SubagentTaskStatus.COMPLETED,
        SubagentTaskStatus.FAILED,
        SubagentTaskStatus.TIMED_OUT,
        SubagentTaskStatus.ADOPTED,
    ]

    for event, status in zip(event_items, expected):
        assert status_from_event_type(event.event_type) is status
        assert status_from_event_payload(event.payload) is status
        assert event.payload["agent_id"] == "ag_03"
        assert event.payload["run_id"] == "run_03"
        assert event.payload["parent_run_id"] == "parent_03"
        assert event.payload["updated_at"] == event.emitted_at

    assert event_items[0].payload["terminal"] is False
    assert event_items[0].payload["terminal_state"] == ""
    assert event_items[3].payload["terminal"] is True
    assert event_items[3].payload["terminal_state"] == "completed"
    assert event_items[6].payload["terminal_state"] == "adopted"
    assert event_items[6].payload["adopted"] is True


def test_failed_and_timeout_events_include_error_metadata() -> None:
    record = _record()
    failed = events.subagent_failed(record, error="network error")
    timed_out = events.subagent_timed_out(record, timeout_reason="deadline")

    assert failed.payload["status"] == "failed"
    assert failed.payload["error"] == "network error"
    assert timed_out.payload["status"] == "timed_out"
    assert timed_out.payload["timeout_reason"] == "deadline"


def test_status_from_event_payload_prefers_event_type_over_conflicting_status() -> None:
    record = _record()
    event = events.subagent_failed(record, error="fatal")
    conflicting_payload = dict(event.payload)
    conflicting_payload["event_type"] = event.event_type
    conflicting_payload["status"] = "completed"

    assert status_from_event_payload(conflicting_payload) is SubagentTaskStatus.FAILED

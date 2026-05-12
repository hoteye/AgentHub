from __future__ import annotations

from cli.agent_cli.runtime_delegation.models import (
    SubagentTaskRecord,
    SubagentTaskStatus,
    is_terminal_subagent_task_status,
)


def test_subagent_task_record_create_defaults_and_required_fields() -> None:
    record = SubagentTaskRecord.create(
        agent_id="ag_01",
        run_id="run_01",
        parent_run_id="parent_01",
        role="reviewer",
        inherited_context={"thread_id": "th_01"},
        timeout=120,
        now_iso="2026-04-07T00:00:00+00:00",
    )

    assert record.agent_id == "ag_01"
    assert record.run_id == "run_01"
    assert record.parent_run_id == "parent_01"
    assert record.role == "reviewer"
    assert record.status is SubagentTaskStatus.QUEUED
    assert record.inherited_context == {"thread_id": "th_01"}
    assert record.timeout == 120
    assert record.created_at == "2026-04-07T00:00:00+00:00"
    assert record.updated_at == "2026-04-07T00:00:00+00:00"


def test_subagent_task_record_with_status_updates_only_status_and_timestamp() -> None:
    record = SubagentTaskRecord.create(
        agent_id="ag_02",
        run_id="run_02",
        inherited_context={"a": 1},
        now_iso="2026-04-07T00:00:00+00:00",
    )
    updated = record.with_status(SubagentTaskStatus.RUNNING, now_iso="2026-04-07T00:01:00+00:00")

    assert updated.status is SubagentTaskStatus.RUNNING
    assert updated.updated_at == "2026-04-07T00:01:00+00:00"
    assert updated.created_at == record.created_at
    assert updated.agent_id == record.agent_id
    assert updated.run_id == record.run_id
    assert updated.inherited_context == record.inherited_context


def test_subagent_task_status_terminal_semantics_include_adopted() -> None:
    assert is_terminal_subagent_task_status(SubagentTaskStatus.QUEUED) is False
    assert is_terminal_subagent_task_status(SubagentTaskStatus.RUNNING) is False
    assert is_terminal_subagent_task_status(SubagentTaskStatus.COMPLETED) is True
    assert is_terminal_subagent_task_status(SubagentTaskStatus.FAILED) is True
    assert is_terminal_subagent_task_status(SubagentTaskStatus.TIMED_OUT) is True
    assert is_terminal_subagent_task_status(SubagentTaskStatus.ADOPTED) is True

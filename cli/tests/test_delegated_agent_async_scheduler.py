from __future__ import annotations

import threading
from types import SimpleNamespace

from cli.agent_cli.runtime_services import delegated_agent_workflow_payload_runtime
from cli.agent_cli.runtime_services import delegated_agent_workflow_runtime


def _session(
    agent_id: str,
    *,
    status: str = "queued",
    parallel_group: str = "",
    task_shape: str = "read_only",
    delegation_mode: str = "background",
    role: str = "subagent",
    wait_required: bool | None = False,
    background_priority: str = "",
    active_input: dict[str, object] | None = None,
    queued_inputs: list[dict[str, object]] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        agent_id=agent_id,
        status=status,
        parallel_group=parallel_group,
        task_shape=task_shape,
        delegation_mode=delegation_mode,
        role=role,
        wait_required=wait_required,
        background_priority=background_priority,
        active_input=active_input,
        queued_inputs=list(queued_inputs or []),
        condition=threading.Condition(),
    )


def _runtime(*sessions: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(_delegated_agents={session.agent_id: session for session in sessions})


def _decision(
    runtime: SimpleNamespace,
    session: SimpleNamespace,
    *,
    max_active: int = 4,
    read_only_max_active: int = 3,
    long_running_max_active: int = 2,
) -> dict[str, object]:
    return delegated_agent_workflow_runtime.delegated_scheduler_decision(
        runtime,
        session,
        max_active=max_active,
        read_only_max_active=read_only_max_active,
        long_running_max_active=long_running_max_active,
        delegated_parallel_group_fn=delegated_agent_workflow_runtime.delegated_parallel_group,
        delegated_parallel_limit_fn=delegated_agent_workflow_runtime.delegated_parallel_limit,
        delegated_session_is_active_fn=delegated_agent_workflow_runtime.delegated_session_is_active,
    )


def test_read_only_parallel_slot_allows_concurrent_children() -> None:
    running = _session("agent_running", status="running", parallel_group="read_only")
    queued = _session(
        "agent_queued",
        status="queued",
        task_shape="read_only",
        queued_inputs=[{"message": "read second"}],
    )
    runtime = _runtime(running, queued)

    decision = _decision(runtime, queued)

    assert decision["allowed"] is True
    assert decision["reason"] == ""
    assert decision["parallel_group"] == "read_only"
    assert decision["parallel_limit"] == 3
    assert decision["active_total"] == 1
    assert decision["group_active"] == 1


def test_read_only_parallel_slot_limit_handles_group_case_variants() -> None:
    running = _session("agent_running", status="running", parallel_group="read_only")
    queued = _session(
        "agent_queued",
        status="queued",
        parallel_group="READ_ONLY",
        queued_inputs=[{"message": "read blocked"}],
    )
    runtime = _runtime(running, queued)

    decision = _decision(runtime, queued, read_only_max_active=1)

    assert decision["allowed"] is False
    assert decision["reason"] == "read_only_parallel_limit_reached"
    assert decision["parallel_group"] == "read_only"
    assert decision["parallel_limit"] == 1
    assert decision["group_active"] == 1


def test_workspace_write_children_are_serialized() -> None:
    running = _session("agent_running", status="running", parallel_group="read_only")
    queued_writer = _session(
        "agent_writer",
        status="queued",
        parallel_group="SERIAL",
        task_shape="workspace_mutating",
        queued_inputs=[{"message": "write second"}],
    )
    runtime = _runtime(running, queued_writer)

    decision = _decision(runtime, queued_writer)

    assert decision["allowed"] is False
    assert decision["reason"] == "serialized_by_active_child"
    assert decision["parallel_group"] == "serial"
    assert decision["parallel_limit"] == 1
    assert decision["active_total"] == 1


def test_low_priority_background_yields_to_normal_background_pending_work() -> None:
    normal_pending = _session(
        "agent_normal",
        status="queued",
        parallel_group="read_only",
        role="subagent",
        delegation_mode="background",
        wait_required=False,
        queued_inputs=[{"message": "high priority background verify"}],
    )
    low_pending = _session(
        "agent_low",
        status="queued",
        parallel_group="read_only",
        role="teammate",
        delegation_mode="background",
        wait_required=False,
        queued_inputs=[{"message": "low priority teammate summary"}],
    )
    runtime = _runtime(normal_pending, low_pending)

    decision = _decision(runtime, low_pending)

    assert decision["allowed"] is False
    assert decision["reason"] == "deferred_by_higher_priority_background_child"
    assert decision["background_priority"] == "low"
    assert decision["active_total"] == 0


def test_parallel_context_normalizes_parallel_group_before_limit() -> None:
    session = _session("agent_payload", parallel_group="SERIAL", task_shape="read_only")

    group, limit = delegated_agent_workflow_payload_runtime.delegated_parallel_context(
        session,
        max_active=4,
        read_only_max_active=3,
        long_running_max_active=2,
        delegated_parallel_group_fn=delegated_agent_workflow_runtime.delegated_parallel_group,
        delegated_parallel_limit_fn=delegated_agent_workflow_runtime.delegated_parallel_limit,
    )

    assert group == "serial"
    assert limit == 1

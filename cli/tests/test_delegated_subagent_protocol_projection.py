from __future__ import annotations

from types import SimpleNamespace

from cli.agent_cli.runtime_services import delegated_agent_background_payload_runtime
from cli.agent_cli.runtime_services import delegated_agent_session_payload_runtime
from cli.agent_cli.runtime_services import delegated_agent_workflow_render_runtime


class _Session:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _Runtime:
    def __init__(self) -> None:
        self._queued = []

    def _delegated_agent_id(self) -> str:
        return "agent_x"

    def _delegated_background_priority(self, **kwargs):
        del kwargs
        return "normal"

    def _delegated_parallel_group(self, *_args, **_kwargs):
        return "read_only"

    def _delegated_planner_input_items(self):
        return []

    def _planner_history(self):
        return []

    def _planner_history_with_context_updates(self, *, planner_history):
        return planner_history

    def _queue_delegated_step(self, _session, *, user_text, source):
        self._queued.append((user_text, source))
        return "step_1"

    def _delegated_queue_item(self, message, *, step_id=""):
        return {"message": str(message), "step_id": str(step_id)}

    def _refresh_delegated_current_step_id(self, _session):
        return None


def test_build_session_preserves_optional_protocol_ids_from_metadata_context() -> None:
    runtime = _Runtime()
    resolution = SimpleNamespace(config=SimpleNamespace(), timeout=30, source="route")

    session = delegated_agent_session_payload_runtime.build_session(
        runtime=runtime,
        session_class=_Session,
        task_text="run checks",
        role="subagent",
        resolution=resolution,
        metadata={
            "context": {
                "run_id": "run_ctx_1",
                "parent_run_id": "run_parent_1",
                "thread_id": "thread_1",
            }
        },
        normalize_spawn_agent_metadata_fn=lambda metadata, **_: dict(metadata or {}),
    )

    assert session.protocol_run_id == "run_ctx_1"
    assert session.protocol_parent_run_id == "run_parent_1"
    assert session.protocol_thread_id == "thread_1"
    assert session.resume_source == "spawn_agent"


def test_build_delegated_agent_payload_exposes_subagent_protocol_summary() -> None:
    session = _Session(
        agent_id="agent_a",
        role="subagent",
        status="queued",
        protocol_run_id="run_a",
        protocol_parent_run_id="run_parent_a",
        protocol_thread_id="thread_a",
        source="route",
        timeout=60,
        created_at="2026-04-07T00:00:00+00:00",
        updated_at="2026-04-07T00:00:10+00:00",
        turn_count=1,
        queued_inputs=[],
        active_input=None,
        close_requested=False,
        closed=False,
        adopted=False,
        last_input_text="",
        last_tool_events=[],
        last_item_events=[],
        last_turn_events=[],
        assistant_text="",
        terminal_reason="",
        delegation_reason="",
        delegation_mode="background",
        wait_required=False,
        task_shape="read_only",
        background_priority="normal",
        scheduler_reason="",
        adopted_at="",
        error="",
    )
    config = SimpleNamespace(
        provider_name="openai",
        base_url="https://example.test",
        model_key="gpt_54",
        planner_kind="openai_responses",
        wire_api="responses",
        model="gpt-5.4",
        reasoning_effort="medium",
    )

    payload = delegated_agent_workflow_render_runtime.build_delegated_agent_payload(
        session,
        config=config,
        parallel_group="read_only",
        parallel_limit=2,
        result_ready=False,
        wall_time_ms=1000,
        current_step_wall_time_ms=None,
        timeout_metadata={},
        last_wait_metadata={},
        completion_policy="silent",
        completion_state="pending",
        result_state="pending",
        result_state_metrics={},
        terminal_state="",
        result_contract={},
        progress_payload={},
    )

    assert payload["run_id"] == "run_a"
    assert payload["parent_run_id"] == "run_parent_a"
    assert payload["thread_id"] == "thread_a"
    assert payload["child_identity"] == {
        "agent_id": "agent_a",
        "run_id": "run_a",
        "parent_run_id": "run_parent_a",
        "thread_id": "thread_a",
    }
    assert payload["resume_source"] == "spawn_agent"
    assert payload["subagent_protocol"]["event_type"] == "subagent.queued"
    assert payload["subagent_protocol"]["status"] == "queued"
    assert payload["subagent_protocol"]["terminal"] is False
    assert payload["subagent_protocol"]["terminal_state"] == ""
    assert payload["subagent_protocol"]["task"]["run_id"] == "run_a"
    assert payload["subagent_protocol_event_type"] == "subagent.queued"
    assert payload["subagent_protocol_status"] == "queued"
    assert payload["subagent_protocol_terminal"] is False
    assert payload["subagent_protocol_adopted"] is False
    assert payload["live_snapshot_version"] == 1
    assert payload["live_run_id"] == "run_a"
    assert payload["live_parent_run_id"] == "run_parent_a"
    assert payload["live_thread_id"] == "thread_a"
    assert payload["live_queued_input_count"] == 0
    assert payload["live_has_active_input"] is False
    assert payload["live_last_tool_event_count"] == 0
    assert payload["live_last_item_event_count"] == 0
    assert payload["live_last_turn_event_count"] == 0
    assert payload["live_snapshot_exported_at"] == "2026-04-07T00:00:10+00:00"


def test_background_payload_sync_keeps_subagent_protocol_projection() -> None:
    payload = {
        "subagent_protocol": {
            "event_type": "subagent.running",
            "status": "running",
            "terminal_state": "",
            "terminal": False,
            "adopted": False,
            "task": {"run_id": "run_b"},
        },
        "run_id": "run_b",
        "parent_run_id": "run_parent_b",
        "thread_id": "thread_b",
        "child_identity": {
            "agent_id": "agent_b",
            "run_id": "run_b",
            "parent_run_id": "run_parent_b",
            "thread_id": "thread_b",
        },
        "resume_source": "send_input",
        "updated_at": "2026-04-07T10:00:00Z",
        "pending_input_count": 2,
        "active_input_text": "work item",
        "tool_event_count": 4,
        "command_policies": [
            {
                "command": "python -V",
                "effective_command": "python3 -V",
                "status": "ok",
                "policy_rewrite": True,
            }
        ],
        "command_policy_denied_count": 0,
        "command_policy_rewrite_count": 1,
        "command_policy_checked_count": 0,
        "command_policy_surface": "denied:0,rewrite:1,checked:0",
    }
    progress_payload = {
        "step_count": 1,
        "checkpoint_count": 1,
        "workflow_state": "running",
        "recovery_action_count": 0,
        "current_step_id": "step_b",
        "current_step_status": "running",
        "current_step_title": "run patch",
    }
    snapshot = delegated_agent_background_payload_runtime.sync_snapshot_payload(
        runtime=SimpleNamespace(_delegated_goal_text=lambda _session: "goal"),
        session=SimpleNamespace(),
        payload=payload,
        progress_payload=progress_payload,
        task_id="bg_1",
        notification_state="pending",
    )
    artifact = delegated_agent_background_payload_runtime.sync_result_artifact(
        session=SimpleNamespace(agent_id="agent_b", role="teammate"),
        payload=payload,
        progress_payload=progress_payload,
        snapshot_path="/tmp/snapshot.json",
        notification_state="pending",
        text="",
        error="",
        preview_text_fn=lambda value, **_: str(value),
    )

    assert snapshot["subagent_protocol"]["event_type"] == "subagent.running"
    assert snapshot["run_id"] == "run_b"
    assert snapshot["parent_run_id"] == "run_parent_b"
    assert snapshot["thread_id"] == "thread_b"
    assert snapshot["child_identity"] == {
        "agent_id": "agent_b",
        "run_id": "run_b",
        "parent_run_id": "run_parent_b",
        "thread_id": "thread_b",
    }
    assert snapshot["resume_source"] == "send_input"
    assert snapshot["live_current_step_id"] == "step_b"
    assert snapshot["live_current_step_status"] == "running"
    assert snapshot["live_current_step_title"] == "run patch"
    assert snapshot["live_snapshot_version"] == 1
    assert snapshot["live_run_id"] == "run_b"
    assert snapshot["live_parent_run_id"] == "run_parent_b"
    assert snapshot["live_thread_id"] == "thread_b"
    assert snapshot["live_queued_input_count"] == 2
    assert snapshot["live_has_active_input"] is True
    assert snapshot["live_last_tool_event_count"] == 4
    assert snapshot["live_snapshot_exported_at"] == "2026-04-07T10:00:00Z"
    assert snapshot["subagent_protocol_event_type"] == "subagent.running"
    assert snapshot["subagent_protocol_status"] == "running"
    assert snapshot["subagent_protocol_terminal"] is False
    assert snapshot["command_policies_count"] == 1
    assert snapshot["command_policy_rewrite_count"] == 1
    assert snapshot["command_policy_surface"] == "denied:0,rewrite:1,checked:0"
    assert artifact["subagent_protocol_event_type"] == "subagent.running"
    assert artifact["subagent_protocol_status"] == "running"
    assert artifact["subagent_protocol_terminal_state"] == ""
    assert artifact["subagent_protocol_adopted"] is False
    assert artifact["run_id"] == "run_b"
    assert artifact["child_identity"] == {
        "agent_id": "agent_b",
        "run_id": "run_b",
        "parent_run_id": "run_parent_b",
        "thread_id": "thread_b",
    }
    assert artifact["resume_source"] == "send_input"
    assert artifact["live_snapshot_version"] == 1
    assert artifact["live_run_id"] == "run_b"
    assert artifact["live_parent_run_id"] == "run_parent_b"
    assert artifact["live_thread_id"] == "thread_b"
    assert artifact["live_current_step_id"] == "step_b"
    assert artifact["live_current_step_status"] == "running"
    assert artifact["live_current_step_title"] == "run patch"
    assert artifact["live_queued_input_count"] == 2
    assert artifact["live_has_active_input"] is True
    assert artifact["command_policies_count"] == 1
    assert artifact["command_policy_rewrite_count"] == 1
    assert artifact["command_policy_surface"] == "denied:0,rewrite:1,checked:0"


def test_build_delegated_agent_payload_marks_adopted_as_terminal_subagent_state() -> None:
    session = _Session(
        agent_id="agent_adopted",
        role="teammate",
        status="completed",
        protocol_run_id="run_adopted",
        protocol_parent_run_id="run_parent_adopted",
        protocol_thread_id="thread_adopted",
        source="route",
        timeout=60,
        created_at="2026-04-07T00:00:00+00:00",
        updated_at="2026-04-07T00:00:10+00:00",
        turn_count=1,
        queued_inputs=[],
        active_input=None,
        close_requested=False,
        closed=False,
        adopted=True,
        last_input_text="",
        last_tool_events=[],
        last_item_events=[],
        last_turn_events=[],
        assistant_text="done",
        terminal_reason="completed",
        delegation_reason="",
        delegation_mode="background",
        wait_required=False,
        task_shape="read_only",
        background_priority="low",
        scheduler_reason="",
        adopted_at="2026-04-07T00:00:09+00:00",
        error="",
    )
    config = SimpleNamespace(
        provider_name="openai",
        base_url="https://example.test",
        model_key="gpt_54",
        planner_kind="openai_responses",
        wire_api="responses",
        model="gpt-5.4",
        reasoning_effort="medium",
    )

    payload = delegated_agent_workflow_render_runtime.build_delegated_agent_payload(
        session,
        config=config,
        parallel_group="read_only",
        parallel_limit=2,
        result_ready=True,
        wall_time_ms=1000,
        current_step_wall_time_ms=None,
        timeout_metadata={},
        last_wait_metadata={},
        completion_policy="suggest_adopt",
        completion_state="pending",
        result_state="pending",
        result_state_metrics={},
        terminal_state="completed",
        result_contract={},
        progress_payload={},
    )

    assert payload["subagent_protocol"]["event_type"] == "subagent.adopted"
    assert payload["subagent_protocol"]["status"] == "adopted"
    assert payload["subagent_protocol"]["terminal"] is True
    assert payload["subagent_protocol"]["terminal_state"] == "adopted"
    assert payload["subagent_protocol"]["adopted"] is True
    assert payload["child_identity"] == {
        "agent_id": "agent_adopted",
        "run_id": "run_adopted",
        "parent_run_id": "run_parent_adopted",
        "thread_id": "thread_adopted",
    }
    assert payload["resume_source"] == "spawn_agent"
    assert payload["subagent_protocol_terminal"] is True
    assert payload["subagent_protocol_terminal_state"] == "adopted"
    assert payload["subagent_protocol_adopted"] is True
    assert payload["live_snapshot_version"] == 1
    assert payload["live_run_id"] == "run_adopted"
    assert payload["live_parent_run_id"] == "run_parent_adopted"
    assert payload["live_thread_id"] == "thread_adopted"


def test_build_delegated_agent_payload_projects_command_policy_summary() -> None:
    session = _Session(
        agent_id="agent_policy",
        role="teammate",
        status="running",
        protocol_run_id="run_policy",
        protocol_parent_run_id="run_parent_policy",
        protocol_thread_id="thread_policy",
        source="route",
        timeout=30,
        created_at="2026-04-07T00:00:00+00:00",
        updated_at="2026-04-07T00:00:05+00:00",
        turn_count=1,
        queued_inputs=[],
        active_input=None,
        close_requested=False,
        closed=False,
        adopted=False,
        last_input_text="",
        last_tool_events=[
            SimpleNamespace(
                name="exec_command",
                payload={
                    "command": "python -V",
                    "effective_command": "python3 -V",
                    "status": "ok",
                    "command_policy": {"allowed": True},
                },
            ),
            SimpleNamespace(
                name="exec_command",
                payload={
                    "command": "rm -rf /tmp/x",
                    "effective_command": "",
                    "status": "policy_denied",
                    "command_policy": {"allowed": False, "error_code": "policy_denied"},
                },
            ),
        ],
        last_item_events=[],
        last_turn_events=[],
        assistant_text="",
        terminal_reason="",
        delegation_reason="",
        delegation_mode="background",
        wait_required=False,
        task_shape="read_only",
        background_priority="low",
        scheduler_reason="",
        adopted_at="",
        error="",
    )
    config = SimpleNamespace(
        provider_name="openai",
        base_url="https://example.test",
        model_key="gpt_54",
        planner_kind="openai_responses",
        wire_api="responses",
        model="gpt-5.4",
        reasoning_effort="medium",
    )

    payload = delegated_agent_workflow_render_runtime.build_delegated_agent_payload(
        session,
        config=config,
        parallel_group="read_only",
        parallel_limit=2,
        result_ready=False,
        wall_time_ms=200,
        current_step_wall_time_ms=None,
        timeout_metadata={},
        last_wait_metadata={},
        completion_policy="silent",
        completion_state="pending",
        result_state="pending",
        result_state_metrics={},
        terminal_state="",
        result_contract={},
        progress_payload={},
    )

    assert payload["command_policies_count"] == 2
    assert payload["command_policy_denied_count"] == 1
    assert payload["command_policy_rewrite_count"] == 1
    assert payload["command_policy_checked_count"] == 0
    assert payload["command_policy_surface"] == "denied:1,rewrite:1,checked:0"

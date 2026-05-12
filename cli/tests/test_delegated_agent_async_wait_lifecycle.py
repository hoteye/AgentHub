from __future__ import annotations

import threading
from types import SimpleNamespace

from cli.agent_cli.runtime_services import delegated_agent_adoption_runtime
from cli.agent_cli.runtime_services import delegated_agent_result_contract_runtime
from cli.agent_cli.runtime_services.delegated_agent_workflow_render_runtime import (
    build_delegated_agent_payload,
)


def _session(
    *,
    status: str,
    wait_required: bool | None,
    adopted: bool = False,
    assistant_text: str = "",
    error: str = "",
    active_input: dict[str, str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        agent_id="ag_async_1",
        role="teammate",
        status=status,
        terminal_reason="",
        source="delegation",
        timeout=30,
        created_at="2026-04-06T00:00:00+00:00",
        updated_at="2026-04-06T00:00:00+00:00",
        turn_count=1,
        queued_inputs=[],
        active_input=active_input,
        close_requested=False,
        closed=False,
        adopted=adopted,
        adopted_at="2026-04-06T00:00:00+00:00" if adopted else "",
        last_input_text="delegate task",
        assistant_text=assistant_text,
        error=error,
        last_tool_events=[],
        wait_required=wait_required,
        delegation_reason="verify_side_task",
        delegation_mode="background",
        task_shape="read_only",
        background_priority="normal",
        scheduler_reason="",
        current_step_id="step_1",
        condition=threading.Condition(),
        last_wait_reason="",
        last_wait_decision="",
        last_wait_at="",
        last_wait_blocked_ms=None,
        last_wait_timed_out=False,
    )


class _RuntimeStub:
    def __init__(
        self,
        session: SimpleNamespace,
        *,
        completion_policy: str,
        extra_sessions: list[SimpleNamespace] | None = None,
    ) -> None:
        self._session_value = session
        self._completion_policy = completion_policy
        self.mark_adopted_calls = 0
        self.checkpoints: list[dict[str, str]] = []
        self._delegated_agents_lock = threading.Lock()
        self._delegated_agents = {session.agent_id: session}
        for extra in list(extra_sessions or []):
            self._delegated_agents[extra.agent_id] = extra

    def _delegated_session(self, agent_id: str) -> SimpleNamespace:
        session = self._delegated_agents.get(agent_id)
        if session is None:
            raise ValueError(f"unknown delegated agent: {agent_id}")
        return session

    @staticmethod
    def _delegated_result_ready(session: SimpleNamespace) -> bool:
        return str(session.status or "").strip().lower() in {"completed", "failed", "closed"}

    @staticmethod
    def _delegated_result_adoptable(session: SimpleNamespace) -> bool:
        return delegated_agent_adoption_runtime.delegated_result_adoptable(session)

    def _mark_delegated_result_adopted(self, session: SimpleNamespace) -> None:
        self.mark_adopted_calls += 1
        delegated_agent_adoption_runtime.mark_delegated_result_adopted(
            self,
            session,
            now_iso_fn=lambda: "2026-04-06T00:10:00+00:00",
        )

    def _delegated_agent_payload(self, session: SimpleNamespace) -> dict[str, object]:
        completion_state = "pending"
        result_state = "pending"
        status = str(session.status or "").strip().lower() or "queued"
        return build_delegated_agent_payload(
            session,
            config=SimpleNamespace(
                provider_name="glm",
                base_url="https://glm.example/v1",
                model_key="glm_5",
                planner_kind="openai_chat",
                wire_api="openai_chat",
                model="glm-5",
                reasoning_effort="medium",
            ),
            parallel_group="read_only",
            parallel_limit=2,
            result_ready=status in {"completed", "failed", "closed"},
            wall_time_ms=None,
            current_step_wall_time_ms=None,
            timeout_metadata={},
            last_wait_metadata={},
            completion_policy=self._completion_policy,
            completion_state=completion_state,
            result_state=result_state,
            result_state_metrics={},
            terminal_state="",
            result_contract={
                "status": status,
                "artifact": {"kind": "pending"},
                "confidence": "pending",
                "completion_policy": self._completion_policy,
                "completion_state": completion_state,
                "next_action": "continue_main_thread_or_wait",
            },
            progress_payload={"step_count": 1, "checkpoint_count": len(self.checkpoints)},
        )

    @staticmethod
    def _sync_delegated_background_task(session: SimpleNamespace) -> None:
        del session

    @staticmethod
    def _delegated_agent_summary_text(session: SimpleNamespace) -> str:
        return str(session.assistant_text or "delegated summary")

    def _record_delegated_checkpoint(self, session: SimpleNamespace, **kwargs: str) -> None:
        del session
        self.checkpoints.append(dict(kwargs))


def test_wait_agent_completed_turn_promotes_terminal_and_adopts() -> None:
    session = _session(
        status="running",
        wait_required=True,
        adopted=False,
        assistant_text="done from delegated turn",
        active_input=None,
    )
    runtime = _RuntimeStub(session, completion_policy="must_join")

    result = delegated_agent_adoption_runtime.wait_agent_result(
        runtime,
        "ag_async_1",
        timeout_ms=50,
        reason="wait_for_child_result",
    )
    payload = result.tool_events[0].payload

    assert result.tool_events[0].summary == "wait_agent completed"
    assert payload["status"] == "completed"
    assert payload["wait_decision"] == "blocking_join"
    assert payload["wait_timed_out"] is False
    assert payload["adopted"] is True
    assert payload["completion_state"] == "adopted"
    assert payload["result_state"] == "adopted"
    assert payload["result_contract"]["status"] == "completed"
    assert payload["result_contract"]["next_action"] == "already_adopted"
    assert session.status == "completed"
    assert runtime.mark_adopted_calls == 1


def test_wait_agent_timeout_keeps_pending_snapshot_contract() -> None:
    session = _session(
        status="running",
        wait_required=False,
        adopted=False,
        assistant_text="",
        active_input={"message": "still running"},
    )
    runtime = _RuntimeStub(session, completion_policy="suggest_adopt")

    result = delegated_agent_adoption_runtime.wait_agent_result(
        runtime,
        "ag_async_1",
        timeout_ms=40,
        reason="wait_for_child_result",
    )
    payload = result.tool_events[0].payload

    assert result.tool_events[0].summary == "wait_agent timed out"
    assert payload["status"] == "running"
    assert payload["completion_state"] == "pending"
    assert payload["result_state"] == "pending"
    assert payload["wait_timed_out"] is True
    assert payload["adopted"] is False
    assert payload["result_contract"]["status"] == "running"
    assert payload["result_contract"]["artifact"]["kind"] == "pending"
    assert payload["result_contract"]["confidence"] == "pending"
    assert payload["result_contract"]["next_action"] == "continue_main_thread_or_wait"


def test_codex_wait_ids_returns_codex_style_completed_and_shutdown_statuses() -> None:
    completed = _session(
        status="completed",
        wait_required=True,
        assistant_text="done from delegated turn",
    )
    closed = _session(
        status="closed",
        wait_required=False,
        assistant_text="",
    )
    closed.agent_id = "ag_async_2"
    closed.terminal_reason = "close_requested"
    runtime = _RuntimeStub(
        completed,
        completion_policy="must_join",
        extra_sessions=[closed],
    )

    result = delegated_agent_adoption_runtime.wait_agents_result(
        runtime,
        ["ag_async_1", "ag_async_2"],
        timeout_ms=10_000,
        codex_style=True,
        wait_agent_result_fn=delegated_agent_adoption_runtime.wait_agent_result,
    )
    payload = result.tool_events[0].payload

    assert result.tool_events[0].name == "wait"
    assert result.tool_events[0].summary == "wait completed"
    assert payload["status"] == {
        "ag_async_1": {"completed": "done from delegated turn"},
        "ag_async_2": "shutdown",
    }
    assert payload["timed_out"] is False


def test_codex_wait_ids_times_out_with_empty_status_map(monkeypatch) -> None:
    monkeypatch.setattr(delegated_agent_adoption_runtime, "MIN_WAIT_TIMEOUT_MS", 1)
    monkeypatch.setattr(delegated_agent_adoption_runtime, "DEFAULT_WAIT_TIMEOUT_MS", 1)
    running = _session(
        status="running",
        wait_required=True,
        active_input={"message": "still running"},
    )
    runtime = _RuntimeStub(running, completion_policy="must_join")

    result = delegated_agent_adoption_runtime.wait_agents_result(
        runtime,
        ["ag_async_1"],
        timeout_ms=1,
        codex_style=True,
        wait_agent_result_fn=delegated_agent_adoption_runtime.wait_agent_result,
    )
    payload = result.tool_events[0].payload

    assert result.tool_events[0].name == "wait"
    assert result.tool_events[0].summary == "wait timed out"
    assert payload["status"] == {}
    assert payload["timed_out"] is True


def test_codex_wait_ids_returns_not_found_without_error() -> None:
    session = _session(
        status="running",
        wait_required=True,
        active_input={"message": "still running"},
    )
    runtime = _RuntimeStub(session, completion_policy="must_join")

    result = delegated_agent_adoption_runtime.wait_agents_result(
        runtime,
        ["missing_agent"],
        timeout_ms=10_000,
        codex_style=True,
        wait_agent_result_fn=delegated_agent_adoption_runtime.wait_agent_result,
    )
    payload = result.tool_events[0].payload

    assert result.tool_events[0].name == "wait"
    assert payload["status"] == {"missing_agent": "not_found"}
    assert payload["timed_out"] is False


def test_completion_state_progresses_awaiting_join_ready_to_adopt_and_adopted() -> None:
    session = _session(
        status="completed",
        wait_required=True,
        adopted=False,
        assistant_text="child result ready",
    )
    must_join_payload = build_delegated_agent_payload(
        session,
        config=SimpleNamespace(),
        parallel_group="read_only",
        parallel_limit=2,
        result_ready=True,
        wall_time_ms=None,
        current_step_wall_time_ms=None,
        timeout_metadata={},
        last_wait_metadata={},
        completion_policy="must_join",
        completion_state="pending",
        result_state="pending",
        result_state_metrics={},
        terminal_state="completed",
        result_contract={
            "status": "running",
            "artifact": {"kind": "pending"},
            "completion_policy": "must_join",
            "completion_state": "pending",
            "next_action": "continue_main_thread_or_wait",
            "confidence": "pending",
        },
        progress_payload={},
    )

    session.wait_required = False
    ready_payload = build_delegated_agent_payload(
        session,
        config=SimpleNamespace(),
        parallel_group="read_only",
        parallel_limit=2,
        result_ready=True,
        wall_time_ms=None,
        current_step_wall_time_ms=None,
        timeout_metadata={},
        last_wait_metadata={},
        completion_policy="suggest_adopt",
        completion_state="pending",
        result_state="pending",
        result_state_metrics={},
        terminal_state="completed",
        result_contract={
            "status": "running",
            "artifact": {"kind": "pending"},
            "completion_policy": "suggest_adopt",
            "completion_state": "pending",
            "next_action": "continue_main_thread_or_wait",
            "confidence": "pending",
        },
        progress_payload={},
    )

    session.adopted = True
    adopted_payload = build_delegated_agent_payload(
        session,
        config=SimpleNamespace(),
        parallel_group="read_only",
        parallel_limit=2,
        result_ready=True,
        wall_time_ms=None,
        current_step_wall_time_ms=None,
        timeout_metadata={},
        last_wait_metadata={},
        completion_policy="suggest_adopt",
        completion_state="pending",
        result_state="pending",
        result_state_metrics={},
        terminal_state="completed",
        result_contract={
            "status": "running",
            "artifact": {"kind": "pending"},
            "completion_policy": "suggest_adopt",
            "completion_state": "pending",
            "next_action": "continue_main_thread_or_wait",
            "confidence": "pending",
        },
        progress_payload={},
    )

    assert must_join_payload["completion_state"] == "awaiting_join"
    assert must_join_payload["result_state"] == "pending_review"
    assert must_join_payload["result_contract"]["status"] == "completed"
    assert must_join_payload["result_contract"]["next_action"] == "wait_agent_to_adopt"
    assert must_join_payload["adoption_expectation"] == "wait_agent_to_adopt"

    assert ready_payload["completion_state"] == "ready_to_adopt"
    assert ready_payload["result_state"] == "pending_review"
    assert ready_payload["result_contract"]["status"] == "completed"
    assert ready_payload["result_contract"]["next_action"] == "review_or_adopt_teammate_result"
    assert ready_payload["adoption_expectation"] == "review_or_adopt_teammate_result"

    assert adopted_payload["completion_state"] == "adopted"
    assert adopted_payload["result_state"] == "adopted"
    assert adopted_payload["result_contract"]["status"] == "completed"
    assert adopted_payload["result_contract"]["next_action"] == "already_adopted"
    assert adopted_payload["adoption_expectation"] == "already_adopted"


def test_result_contract_treats_closed_state_as_control_plane_without_stale_result_artifact() -> None:
    contract = delegated_agent_result_contract_runtime.delegated_result_contract_payload(
        SimpleNamespace(cwd="/tmp"),
        goal="delegate cleanup",
        status="closed",
        assistant_text="stale delegated text",
        error="",
        adopted=False,
        touched_sources=[],
        role="subagent",
        delegation_mode="background",
        wait_required=False,
        delegated_completion_policy_fn=lambda **_: "silent",
        delegated_completion_state_fn=lambda **_: "closed",
    )

    assert contract["status"] == "closed"
    assert contract["artifact"] == {"kind": "empty"}
    assert contract["confidence"] == "low"
    assert contract["summary"] == "delegated task closed before producing a result"
    assert contract["next_action"] == "resume_agent_to_continue"
